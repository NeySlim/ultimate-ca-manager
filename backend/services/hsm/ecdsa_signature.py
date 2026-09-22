"""ECDSA signature normalisation for HSM providers (#366).

X.509 carries an ECDSA signature as the DER ``SEQUENCE { r INTEGER, s INTEGER }``
of RFC 5480; PKCS#11 and Azure Key Vault return the raw ``r || s`` concatenation
instead, which embedded as is makes every CSR, certificate and CRL unverifiable.
"""
from typing import Optional

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.asymmetric.utils import (
    decode_dss_signature, encode_dss_signature,
)

_COORDINATE_BYTES = {'EC-P256': 32, 'EC-P384': 48, 'EC-P521': 66}


def coordinate_bytes(key_algorithm: Optional[str], public_key_pem: Optional[str] = None) -> Optional[int]:
    """Byte length of one ECDSA coordinate for the key, ``None`` for a non-EC key.

    The public key wins over the algorithm label, which a key sync may guess.
    """
    if public_key_pem:
        try:
            public_key = serialization.load_pem_public_key(public_key_pem.encode())
        except (ValueError, TypeError):
            public_key = None
        if public_key is not None:
            if isinstance(public_key, ec.EllipticCurvePublicKey):
                return (public_key.curve.key_size + 7) // 8
            return None
    return _COORDINATE_BYTES.get(key_algorithm)


def _is_der(signature: bytes) -> bool:
    try:
        r, s = decode_dss_signature(signature)
    except (ValueError, TypeError):
        return False
    return encode_dss_signature(r, s) == signature


def ecdsa_to_der(signature: bytes, coordinate_size: Optional[int]) -> bytes:
    """Raw ``r || s`` of exactly two coordinates -> DER; anything else is returned as is.

    A DER signature is never exactly two coordinates long in practice, and one
    that is gets recognised by round-tripping through the DER codec.
    """
    if not coordinate_size or len(signature) != 2 * coordinate_size or _is_der(signature):
        return signature
    r = int.from_bytes(signature[:coordinate_size], 'big')
    s = int.from_bytes(signature[coordinate_size:], 'big')
    return encode_dss_signature(r, s)
