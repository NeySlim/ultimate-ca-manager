"""Reading certificates whose algorithms pyca cannot load (SM2, GOST, FRP256v1, SLH-DSA).

Such a certificate is displayed by its OID and, when UCM knows it, a name.
Nothing here issues, signs or verifies anything.
"""
import logging

import asn1crypto.csr
import asn1crypto.x509
from asn1crypto import core, parser
from cryptography import x509
from cryptography.exceptions import UnsupportedAlgorithm
from cryptography.hazmat.primitives import serialization

from utils import key_algorithms

logger = logging.getLogger(__name__)

EC_PUBLIC_KEY_OID = '1.2.840.10045.2.1'

# (name, key size in bits)
_CURVES = {
    '1.2.156.10197.1.301': ('SM2', 256),
    '1.2.250.1.223.101.256.1': ('FRP256v1', 256),
}
_KEY_ALGORITHMS = {
    '1.2.643.7.1.1.1.1': ('GOST2012-256', 256),
    '1.2.643.7.1.1.1.2': ('GOST2012-512', 512),
    '1.2.643.2.2.19': ('GOST2001', 256),
}
_SIGNATURES = {
    '1.2.156.10197.1.501': 'SM2-with-SM3',
}


def signature_name(dotted):
    """Known name of a signature algorithm OID pyca does not name, else None."""
    pq = key_algorithms.post_quantum_info(dotted) if dotted else None
    return _SIGNATURES.get(dotted) or (pq.label if pq else None)


def _spki(obj):
    """The asn1crypto SubjectPublicKeyInfo of a certificate or CSR."""
    der = obj.public_bytes(serialization.Encoding.DER)
    if isinstance(obj, x509.Certificate):
        return asn1crypto.x509.Certificate.load(der)['tbs_certificate']['subject_public_key_info']
    return asn1crypto.csr.CertificationRequest.load(der)['certification_request_info']['subject_pk_info']


def spki_der(obj):
    """DER SubjectPublicKeyInfo of a certificate or CSR, whatever its key type."""
    return _spki(obj).dump()


def _children(der):
    """The (tag, content) of each element inside the DER constructed value *der*."""
    out = []
    _, _, _, header, content, trailer = parser.parse(der)
    body = content
    pos = 0
    while pos < len(body):
        _, _, tag, hdr, cont, trl = parser.parse(body[pos:])
        out.append((tag, cont))
        pos += len(hdr) + len(cont) + len(trl)
    return out


def _oid_text(content):
    return core.ObjectIdentifier.load(b'\x06' + _der_length(len(content)) + content).dotted


def _der_length(n):
    if n < 0x80:
        return bytes([n])
    raw = n.to_bytes((n.bit_length() + 7) // 8, 'big')
    return bytes([0x80 | len(raw)]) + raw


def describe_public_key(obj):
    """Description of a key pyca cannot load, None when pyca can load it.

    {'oid', 'name', 'label', 'key_size'}: oid is the algorithm OID (the
    curve OID for an EC key), label the name or the dotted OID.
    """
    try:
        obj.public_key()
        return None
    except (UnsupportedAlgorithm, ValueError):
        pass
    try:
        spki = _children(spki_der(obj))
        algorithm_parts = _children(b'\x30' + _der_length(len(spki[0][1])) + spki[0][1])
        algorithm = _oid_text(algorithm_parts[0][1])
        oid, name, size = algorithm, None, 0
        if algorithm == EC_PUBLIC_KEY_OID:
            if len(algorithm_parts) > 1 and algorithm_parts[1][0] == 6:
                oid = _oid_text(algorithm_parts[1][1])
                name, size = _CURVES.get(oid, (None, 0))
                point = spki[1][1][1:]  # drop the BIT STRING unused-bits byte
                if not size and len(point) > 1 and point[0] == 4:
                    size = (len(point) - 1) // 2 * 8
        else:
            name, size = _KEY_ALGORITHMS.get(algorithm, (None, 0))
        pq = None if name else key_algorithms.post_quantum_info(algorithm)
        if pq:  # SLH-DSA, or ML-DSA on a build without it: a post-quantum key has no size
            name, size = pq.label, None
        return {'oid': oid, 'name': name, 'label': name or oid, 'key_size': size,
                'security_level': pq.security_level if pq else None, 'post_quantum': bool(pq)}
    except Exception as e:
        logger.debug("Cannot describe public key: %s", e)
        return {'oid': None, 'name': None, 'label': 'unknown', 'key_size': 0,
                'security_level': None, 'post_quantum': False}


def key_type_label(obj):
    """'SM2 256' (name or OID, then size) for a foreign key, None for a key pyca loads."""
    info = describe_public_key(obj)
    if info is None:
        return None
    return f"{info['label']} {info['key_size']}" if info['key_size'] else info['label']


def signature_label(oid):
    """Name of a signature algorithm OID: pyca's name, else ours, else the dotted OID."""
    if oid._name != 'Unknown OID':
        return oid._name
    return signature_name(oid.dotted_string) or oid.dotted_string
