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

_COORDINATE_BYTES = {'EC-P256': 32, 'EC-P384': 48, 'EC-P521': 66,
                      'EC-BP256': 32, 'EC-BP384': 48, 'EC-BP512': 64}


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


def ecdsa_to_der(signature: bytes, coordinate_size: Optional[int],
                 signature_format: str) -> bytes:
    """Decode the provider's declared format, never guess from ambiguous signature bytes."""
    if not coordinate_size:
        return signature
    if signature_format == 'der':
        # The parser's own text never reaches the user: it describes ASN.1 internals
        try:
            r, s = decode_dss_signature(signature)
        except ValueError:
            raise ValueError('Invalid DER HSM ECDSA signature') from None
        return encode_dss_signature(r, s)
    if signature_format != 'raw':
        raise ValueError('Unknown HSM ECDSA signature format')
    if len(signature) != 2 * coordinate_size:
        raise ValueError('Invalid raw HSM ECDSA signature length')
    r = int.from_bytes(signature[:coordinate_size], 'big')
    s = int.from_bytes(signature[coordinate_size:], 'big')
    return encode_dss_signature(r, s)
