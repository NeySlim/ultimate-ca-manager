"""SHA-256 of a SubjectPublicKeyInfo: names a key whatever certificate holds it."""
import base64
import hashlib
import logging
from typing import Optional

from cryptography import x509
from cryptography.hazmat.primitives import serialization

logger = logging.getLogger(__name__)


def public_key_sha256(public_key) -> str:
    der = public_key.public_bytes(serialization.Encoding.DER,
                                  serialization.PublicFormat.SubjectPublicKeyInfo)
    return hashlib.sha256(der).hexdigest()


def certificate_key_sha256(crt_b64) -> Optional[str]:
    """Digest of the key of a stored certificate (``Certificate.crt``), None when it cannot
    be read here (no certificate, an algorithm or a FIPS provider that refuses it)."""
    if not crt_b64:
        return None
    try:
        raw = base64.b64decode(crt_b64)
        if raw.lstrip().startswith(b'-----BEGIN'):
            cert = x509.load_pem_x509_certificate(raw)
        else:
            cert = x509.load_der_x509_certificate(raw)
        return public_key_sha256(cert.public_key())
    except Exception as exc:
        logger.debug("Key digest of a certificate not computed: %s", exc)
        return None
