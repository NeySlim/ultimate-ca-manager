"""Keytabs and Negotiate tokens built in the test: MIT keytab bytes, SPNEGO NegTokenInit, AP-REQ.

Never a real key: the key bytes are a counter, the tickets carry no valid encryption.
"""
import base64
import struct

AES256 = 18
AES128 = 17


def _counted(value):
    data = value.encode() if isinstance(value, str) else value
    return struct.pack('>H', len(data)) + data


def entry(principal, kvno=2, enctype=AES256, name_type=1, timestamp=0):
    """One format 0x0502 entry (without its size) for ``a/b@REALM``."""
    name, _, realm = principal.rpartition('@')
    components = name.split('/')
    key = bytes(range(32 if enctype == AES256 else 16))
    return (struct.pack('>H', len(components)) + _counted(realm)
            + b''.join(_counted(c) for c in components)
            + struct.pack('>IIBH', name_type, timestamp, kvno & 0xff, enctype)
            + _counted(key) + struct.pack('>I', kvno))


def keytab(*entries):
    """A format 0x0502 keytab: each item a principal, or (principal, kvno) or (principal, kvno, enctype)."""
    out = b'\x05\x02'
    for item in entries:
        raw = entry(item) if isinstance(item, str) else entry(*item)
        out += struct.pack('>i', len(raw)) + raw
    return out


def _der(tag, content):
    n = len(content)
    if n < 0x80:
        length = bytes([n])
    else:
        body = n.to_bytes((n.bit_length() + 7) // 8, 'big')
        length = bytes([0x80 | len(body)]) + body
    return bytes([tag]) + length + content


def _oid(dotted):
    parts = [int(p) for p in dotted.split('.')]
    out = bytes([40 * parts[0] + parts[1]])
    for value in parts[2:]:
        chunk = [value & 0x7f]
        value >>= 7
        while value:
            chunk.insert(0, 0x80 | (value & 0x7f))
            value >>= 7
        out += bytes(chunk)
    return _der(0x06, out)


KRB5_OID = '1.2.840.113554.1.2.2'
MS_KRB5_OID = '1.2.840.48018.1.2.2'
SPNEGO_OID = '1.3.6.1.5.5.2'


def ap_req(realm, service='HTTP', host='ucm.example.test'):
    """An AP-REQ whose ticket names ``service/host@realm``; its encrypted parts are filler."""
    sname = _der(0x30, _der(0xa0, _der(0x02, b'\x02'))
                 + _der(0xa1, _der(0x30, _der(0x1b, service.encode()) + _der(0x1b, host.encode()))))
    enc = _der(0x30, _der(0xa0, _der(0x02, bytes([AES256]))) + _der(0xa2, _der(0x04, b'\x00' * 48)))
    ticket = _der(0x61, _der(0x30, _der(0xa0, _der(0x02, b'\x05')) + _der(0xa1, _der(0x1b, realm.encode()))
                              + _der(0xa2, sname) + _der(0xa3, enc)))
    body = (_der(0xa0, _der(0x02, b'\x05')) + _der(0xa1, _der(0x02, b'\x0e'))
            + _der(0xa2, _der(0x03, b'\x00\x00\x00\x00\x00')) + _der(0xa3, ticket) + _der(0xa4, enc))
    return _der(0x6e, _der(0x30, body))


def negotiate_header(realm, **kwargs):
    """``Negotiate <b64>`` of a NegTokenInit offering MS-KRB5 then KRB5, with an AP-REQ for *realm*."""
    krb5_token = _der(0x60, _oid(KRB5_OID) + b'\x01\x00' + ap_req(realm, **kwargs))
    init = _der(0x30, _der(0xa0, _der(0x30, _oid(MS_KRB5_OID) + _oid(KRB5_OID)))
                + _der(0xa2, _der(0x04, krb5_token)))
    token = _der(0x60, _oid(SPNEGO_OID) + _der(0xa0, init))
    return 'Negotiate ' + base64.b64encode(token).decode('ascii')
