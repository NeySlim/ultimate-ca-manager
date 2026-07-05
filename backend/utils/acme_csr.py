"""ACME CSR helpers — domain extraction and order matching (RFC 8555 §7.4)."""
from __future__ import annotations

import base64
from typing import List, Tuple

from cryptography import x509
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import serialization


def normalize_pem_csr(csr_pem: str) -> str:
    """Strip whitespace and ensure trailing newline."""
    text = (csr_pem or '').strip()
    if not text:
        raise ValueError('CSR is empty')
    if '-----BEGIN CERTIFICATE REQUEST-----' not in text:
        raise ValueError('Invalid CSR: missing PEM header')
    return text + '\n'


def load_pem_csr(csr_pem: str) -> x509.CertificateSigningRequest:
    """Parse a PEM CSR or raise ValueError."""
    try:
        return x509.load_pem_x509_csr(
            normalize_pem_csr(csr_pem).encode(),
            default_backend(),
        )
    except ValueError:
        raise
    except Exception as exc:
        raise ValueError(f'Invalid CSR: {exc}') from exc


def extract_domains_from_csr(csr: x509.CertificateSigningRequest) -> List[str]:
    """Extract DNS names from CSR subject CN and SAN extension."""
    domains: List[str] = []
    try:
        cn = csr.subject.get_attributes_for_oid(x509.oid.NameOID.COMMON_NAME)[0].value
        domains.append(cn)
    except Exception:
        pass
    try:
        san_ext = csr.extensions.get_extension_for_oid(
            x509.oid.ExtensionOID.SUBJECT_ALTERNATIVE_NAME
        )
        for name in san_ext.value:
            if isinstance(name, x509.DNSName) and name.value not in domains:
                domains.append(name.value)
    except x509.ExtensionNotFound:
        pass
    return domains


def csr_domains_match_order(
    csr: x509.CertificateSigningRequest,
    order_domains: List[str],
) -> Tuple[bool, str]:
    """Return (ok, message). DNS identifiers compared case-insensitively (RFC 4343)."""
    csr_domains = extract_domains_from_csr(csr)
    if not csr_domains:
        return False, 'CSR contains no DNS identifiers'
    csr_norm = {d.lower().rstrip('.') for d in csr_domains}
    order_norm = {d.lower().rstrip('.') for d in order_domains}
    if csr_norm != order_norm:
        return False, (
            f"CSR domains {sorted(csr_norm)} don't match order domains {sorted(order_norm)}"
        )
    return True, 'CSR domains match order'


def csr_to_b64url_der(csr: x509.CertificateSigningRequest) -> str:
    """Encode CSR as base64url DER for ACME finalize payload."""
    csr_der = csr.public_bytes(serialization.Encoding.DER)
    return base64.urlsafe_b64encode(csr_der).rstrip(b'=').decode()


def load_private_key_from_certificate(cert) -> object:
    """Load a cryptography private key from a Certificate model row.

    Works for both storage formats: base64-plain PEM (ACME imports) and
    Fernet-encrypted (CSR/lifecycle, backup restore) — see utils/key_codec.py.
    """
    from utils.key_codec import load_pem_bytes

    if not cert or not cert.prv:
        raise ValueError('Certificate has no stored private key')
    context = f"certificate {getattr(cert, 'id', '?')}"
    pem_bytes = load_pem_bytes(cert.prv, context=context)
    return serialization.load_pem_private_key(
        pem_bytes,
        password=None,
        backend=default_backend(),
    )
