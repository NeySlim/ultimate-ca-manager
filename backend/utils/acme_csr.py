"""ACME CSR helpers — domain extraction and order matching (RFC 8555 §7.4)."""
from __future__ import annotations

import base64
from typing import List, Tuple

from cryptography import x509
from utils.csr_extensions import csr_extensions
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import serialization


# What certreq.exe and the Windows MMC write instead of the standard label.
# The armor differs; the DER between the lines does not, so the request is
# rewritten to the label `cryptography` accepts rather than refused for its
# spelling.
_MS_BEGIN = '-----BEGIN NEW CERTIFICATE REQUEST-----'
_MS_END = '-----END NEW CERTIFICATE REQUEST-----'
_BEGIN = '-----BEGIN CERTIFICATE REQUEST-----'
_END = '-----END CERTIFICATE REQUEST-----'


def normalize_pem_csr(csr_pem: str) -> str:
    """Strip whitespace, accept the Microsoft armor, ensure trailing newline."""
    text = (csr_pem or '').strip()
    if not text:
        raise ValueError('CSR is empty')
    if _MS_BEGIN in text:
        text = text.replace(_MS_BEGIN, _BEGIN).replace(_MS_END, _END)
    if _BEGIN not in text:
        raise ValueError('Invalid CSR: missing PEM header')
    return text + '\n'


# The finalize payload's `csr` member is base64url DER, straight off the wire
# and unbounded: both finalize routes decoded and parsed it with no size check
# at all, while every other CSR entry point (admin API, EST, the decode tools)
# caps its input. A PKCS#10 request with a 4096-bit key and a long SAN list
# stays well under 4 KB.
MAX_CSR_B64_CHARS = 64 * 1024


def decode_csr_b64(csr_b64: str) -> x509.CertificateSigningRequest:
    """Parse the base64url DER CSR of an ACME finalize payload.

    Raises ValueError when it is missing, over the size cap, not valid
    base64url, or not a CSR.
    """
    if not isinstance(csr_b64, str) or not csr_b64:
        raise ValueError('CSR required')
    if len(csr_b64) > MAX_CSR_B64_CHARS:
        raise ValueError('CSR too large')
    try:
        der = base64.urlsafe_b64decode(csr_b64 + '=' * (-len(csr_b64) % 4))
        return x509.load_der_x509_csr(der, default_backend())
    except ValueError:
        raise
    except Exception as exc:
        raise ValueError(f'Invalid CSR: {exc}') from exc


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
        san_ext = csr_extensions(csr).get_extension_for_oid(
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
