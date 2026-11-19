"""The CRL issuer RFC 5280 §5.2.3 numbers CRLs for: a CA name and its key."""
import base64
import hashlib
from typing import Optional

from cryptography import x509


def _spki_der(cert: x509.Certificate) -> bytes:
    # Read from the certificate itself: a key type this build cannot load still has its bytes
    from asn1crypto import x509 as asn1_x509
    tbs = asn1_x509.TbsCertificate.load(cert.tbs_certificate_bytes)
    return tbs['subject_public_key_info'].dump()


def crl_issuer_key(cert: x509.Certificate) -> str:
    """SHA-256 of the subject DER followed by the SubjectPublicKeyInfo DER, in hex."""
    return hashlib.sha256(cert.subject.public_bytes() + _spki_der(cert)).hexdigest()


def crl_issuer_key_of_stored(crt) -> Optional[str]:
    """The same for a stored ``CA.crt`` (base64 of PEM or DER); None when unreadable."""
    if not crt:
        return None
    try:
        raw = base64.b64decode(crt)
        cert = (x509.load_pem_x509_certificate(raw) if raw.lstrip().startswith(b'-----BEGIN')
                else x509.load_der_x509_certificate(raw))
        return crl_issuer_key(cert)
    except Exception:
        return None
