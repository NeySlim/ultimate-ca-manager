"""Spike: verify the RFC 8945 server-side ordering approach with dnspython 2.8 public API."""
import base64
import struct
import time

import dns.message
import dns.name
import dns.rcode
import dns.rdataclass
import dns.rdatatype
import dns.rdtypes.ANY.TSIG
import dns.rrset
import dns.tsig
import dns.tsigkeyring
import dns.update
import dns.wire

KEYNAME = dns.name.from_text("k1.example.")
SECRET = base64.b64encode(b"\x01" * 32).decode()
KEY = dns.tsig.Key(KEYNAME, SECRET, dns.tsig.HMAC_SHA256)


def tsig_start_offset(wire: bytes) -> int:
    """Offset of the last RR in the additional section (public dns.wire.Parser)."""
    p = dns.wire.Parser(wire)
    _id, _flags, qd, an, ns, ar = struct.unpack("!HHHHHH", p.get_bytes(12))
    for _ in range(qd):
        p.get_name()
        p.get_bytes(4)
    last = None
    for _ in range(an + ns + ar):
        last = p.current
        p.get_name()
        _t, _c, _ttl, rdlen = struct.unpack("!HHIH", p.get_bytes(10))
        p.get_bytes(rdlen)
    return last


def server_verify(wire: bytes, now: int):
    msg = dns.message.from_wire(wire, keyring=False)
    assert msg.had_tsig
    rd = msg.tsig[0]
    owner = msg.tsig.name
    # 1 key check
    if owner != KEY.name or rd.algorithm != KEY.algorithm:
        return "BADKEY", msg
    start = tsig_start_offset(wire)
    # 2 MAC check: time check neutralised by now=time_signed
    try:
        dns.tsig.validate(wire, KEY, owner, rd, rd.time_signed, b"", start)
    except dns.tsig.BadSignature:
        return "BADSIG", msg
    # 3 time
    if abs(now - rd.time_signed) > rd.fudge:
        return "BADTIME", msg
    return "OK", msg


def make_update():
    u = dns.update.UpdateMessage("example.com.", keyring={KEYNAME: KEY}, keyname=KEYNAME,
                                 keyalgorithm=dns.tsig.HMAC_SHA256)
    u.add("_acme-challenge.host.example.com.", 60, "TXT", '"abc"')
    return u


def badtime_response(req_msg, req_wire, now):
    rd = req_msg.tsig[0]
    resp = dns.message.make_response(req_msg)  # keyring False -> not signed by dnspython
    resp.set_rcode(dns.rcode.NOTAUTH)
    body = resp.to_wire()
    other = struct.pack("!HI", (now >> 32) & 0xFFFF, now & 0xFFFFFFFF)
    trd = dns.rdtypes.ANY.TSIG.TSIG(dns.rdataclass.ANY, dns.rdatatype.TSIG, rd.algorithm,
                                    rd.time_signed, rd.fudge, b"", req_msg.id,
                                    dns.rcode.BADTIME, other)
    signed, _ = dns.tsig.sign(body, KEY, trd, rd.time_signed, rd.mac)
    rrset = dns.rrset.from_rdata(KEYNAME, 0, signed)
    import io
    f = io.BytesIO()
    n = rrset.to_wire(f)
    arcount = struct.unpack("!H", body[10:12])[0] + n
    return body[:10] + struct.pack("!H", arcount) + body[12:] + f.getvalue()


def unsigned_error(req_msg, err):
    rd = req_msg.tsig[0]
    resp = dns.message.make_response(req_msg)
    resp.set_rcode(dns.rcode.NOTAUTH)
    trd = dns.rdtypes.ANY.TSIG.TSIG(dns.rdataclass.ANY, dns.rdatatype.TSIG, rd.algorithm,
                                    rd.time_signed, rd.fudge, b"", req_msg.id, err, b"")
    resp.tsig = dns.rrset.from_rdata(req_msg.tsig.name, 0, trd)
    resp.want_tsig_sign = False
    return resp.to_wire()


if __name__ == "__main__":
    now = int(time.time())
    u = make_update()
    wire = u.to_wire()
    print("good:", server_verify(wire, now)[0])
    # flip MAC byte
    bad = bytearray(wire); bad[-10] ^= 1
    print("bad mac:", server_verify(bytes(bad), now)[0])
    # bad mac + bad time -> must be BADSIG
    print("bad mac + bad time:", server_verify(bytes(bad), now + 10_000)[0])
    # good mac + bad time
    st, m = server_verify(wire, now + 10_000)
    print("bad time:", st)
    r = badtime_response(m, wire, now + 10_000)
    # client side: dnspython should raise PeerBadTime after verifying the MAC
    try:
        dns.message.from_wire(r, keyring={KEYNAME: KEY}, request_mac=u.mac)
        print("client parsed BADTIME without error?!")
    except dns.tsig.PeerBadTime:
        print("client: PeerBadTime (MAC verified first? see dnspython order)")
    # verify that the MAC of the BADTIME response is genuinely valid
    rm = dns.message.from_wire(r, keyring=False)
    rd = rm.tsig[0]
    start = tsig_start_offset(r)
    rd0 = rd.replace(error=0)
    try:
        # validate() raises PeerBadTime on error!=0 before MAC; recompute manually
        new_wire = r[0:10] + struct.pack("!H", struct.unpack("!H", r[10:12])[0] - 1) + r[12:start]
        signed, _ = dns.tsig.sign(new_wire, KEY, rd.replace(mac=b""), rd.time_signed, u.mac)
        print("BADTIME MAC matches:", signed.mac == rd.mac, "time_signed==client:", rd.time_signed == u.tsig[0].time_signed,
              "other len:", len(rd.other))
    except Exception as e:
        print("err", e)
    ue = unsigned_error(m, dns.rcode.BADSIG)
    um = dns.message.from_wire(ue, keyring=False)
    print("unsigned BADSIG: rcode", dns.rcode.to_text(um.rcode()), "mac len", len(um.tsig[0].mac),
          "error", dns.rcode.to_text(um.tsig[0].error))
