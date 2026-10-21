"""Which CAs may sign RSA-PSS.

PSS needs an RSA key, and for an HSM key a provider that signs PSS; the
choice is refused up front rather than at the first certificate.
"""
import base64
from typing import Optional, Tuple

from cryptography import x509
from cryptography.hazmat.primitives.asymmetric import rsa

from utils.signing_hash import SIGNATURE_SCHEMES


def normalize_signature_scheme(value) -> Tuple[Optional[str], Optional[str]]:
    """(scheme, error) for a request value; None or '' is PKCS#1 v1.5 (at creation)."""
    if value is None or value == '':
        return 'pkcs1v15', None
    if not isinstance(value, str) or value.strip().lower() not in SIGNATURE_SCHEMES:
        return None, f"signatureScheme must be one of {list(SIGNATURE_SCHEMES)}"
    return value.strip().lower(), None


def pss_refusal(is_rsa: bool, hsm_provider_type: Optional[str] = None) -> Optional[str]:
    """Why a CA with this key cannot sign RSA-PSS, or None."""
    if not is_rsa:
        return 'RSA-PSS needs an RSA key'
    if hsm_provider_type is not None:
        from services.hsm import HsmService
        if not HsmService.signs_pss(hsm_provider_type):
            return f"HSM provider type '{hsm_provider_type}' does not sign RSA-PSS"
    return None


def ca_public_key(ca):
    """The CA's public key: certificate, else pending CSR, else HSM key."""
    if ca.crt:
        return x509.load_pem_x509_certificate(base64.b64decode(ca.crt)).public_key()
    if ca.csr:
        return x509.load_pem_x509_csr(base64.b64decode(ca.csr)).public_key()
    if ca.hsm_key_id:
        from services.hsm.hsm_private_key import load_hsm_private_key
        return load_hsm_private_key(ca.hsm_key_id).public_key()
    return None


def ca_pss_refusal(ca) -> Optional[str]:
    """Why this existing CA cannot sign RSA-PSS, or None."""
    provider_type = None
    if ca.hsm_key_id:
        provider = ca.hsm_key.provider if ca.hsm_key else None
        provider_type = provider.type if provider else 'unknown'
    return pss_refusal(isinstance(ca_public_key(ca), rsa.RSAPublicKey), provider_type)
