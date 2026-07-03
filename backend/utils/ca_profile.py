"""
CA certificate profile helpers (RFC 5280 §4.2.1.3, §4.2.1.12).

Defaults follow common PKI practice (e.g. Let's Encrypt Root-YR / issuing CA):
  - Root CA: keyCertSign + cRLSign (no digitalSignature)
  - Subordinate CA: digitalSignature + keyCertSign + cRLSign + optional serverAuth EKU
"""
from typing import List, Optional, Tuple

from cryptography import x509

from utils.eku_validation import normalize_extra_ekus, to_object_identifiers

# Short names accepted in API/UI (aligned with cert_extensions.py labels)
KU_NAME_TO_ATTR = {
    'digitalSignature': 'digital_signature',
    'keyEncipherment': 'key_encipherment',
    'contentCommitment': 'content_commitment',
    'nonRepudiation': 'content_commitment',
    'dataEncipherment': 'data_encipherment',
    'keyAgreement': 'key_agreement',
    'keyCertSign': 'key_cert_sign',
    'cRLSign': 'crl_sign',
    'encipherOnly': 'encipher_only',
    'decipherOnly': 'decipher_only',
}

# RFC 5280 — sensible KU bits for CA certificates (reject leaf-only flags)
ALLOWED_CA_KEY_USAGE = frozenset({'digitalSignature', 'keyCertSign', 'cRLSign'})

# RFC 5280 §4.2.1.3 — root / offline CA profile (LE ISRG Root X2 style)
DEFAULT_ROOT_KEY_USAGE = ['keyCertSign', 'cRLSign']

# Subordinate issuing CA (LE E7 / YE1 style KU + typical EKU)
DEFAULT_INTERMEDIATE_KEY_USAGE = ['digitalSignature', 'keyCertSign', 'cRLSign']
DEFAULT_INTERMEDIATE_EKU = ['serverAuth']

ALLOWED_DIGESTS = frozenset({'sha256', 'sha384', 'sha512'})


def default_digest_for_key_type(key_type: str) -> str:
    """
    Map key type to a matching signature hash (NIST SP 800-57 alignment for EC).
    RSA defaults to SHA-256 unless the caller overrides.
    """
    if key_type == 'secp384r1':
        return 'sha384'
    if key_type == 'secp521r1':
        return 'sha512'
    return 'sha256'


def resolve_digest(digest: Optional[str], key_type: str) -> Tuple[str, Optional[str]]:
    """
    Resolve digest from API input ('auto', explicit, or None).
    Returns (digest, error_message).
    """
    if digest is None or digest == '' or digest == 'auto':
        return default_digest_for_key_type(key_type), None
    normalized = digest.lower().strip()
    if normalized not in ALLOWED_DIGESTS:
        return '', f'digest must be one of auto, {", ".join(sorted(ALLOWED_DIGESTS))}'
    return normalized, None


def default_key_usage_for_ca(is_root: bool) -> List[str]:
    """RFC-aligned default Key Usage for root vs subordinate CA."""
    if is_root:
        return list(DEFAULT_ROOT_KEY_USAGE)
    return list(DEFAULT_INTERMEDIATE_KEY_USAGE)


def default_eku_for_ca(is_root: bool) -> List[str]:
    """Default Extended Key Usage (empty for roots; serverAuth for issuing CAs)."""
    if is_root:
        return []
    return list(DEFAULT_INTERMEDIATE_EKU)


def validate_ca_key_usage(usages) -> Optional[str]:
    """
    Validate Key Usage list for CA creation.
    RFC 5280 §4.2.1.3: CA certs MUST assert keyCertSign when KeyUsage is present.
    """
    if usages is None:
        return None
    if not isinstance(usages, list):
        return 'keyUsage must be an array'
    if not usages:
        return 'keyUsage must not be empty'
    normalized = []
    for item in usages:
        if not isinstance(item, str) or not item.strip():
            return 'each keyUsage entry must be a non-empty string'
        name = item.strip()
        if name not in KU_NAME_TO_ATTR:
            return f'unknown keyUsage: {name}'
        if name not in ALLOWED_CA_KEY_USAGE:
            return (
                f'keyUsage {name} is not allowed on CA certificates; '
                f'allowed: {", ".join(sorted(ALLOWED_CA_KEY_USAGE))}'
            )
        if name not in normalized:
            normalized.append(name)
    if 'keyCertSign' not in normalized:
        return 'CA certificates MUST include keyCertSign (RFC 5280 §4.2.1.3)'
    if 'cRLSign' not in normalized:
        return 'CA certificates SHOULD include cRLSign (RFC 5280 §4.2.1.3)'
    return None


def build_key_usage_kwargs(usage_names: List[str]) -> dict:
    """Build x509.KeyUsage keyword arguments from short names."""
    kwargs = {attr: False for attr in KU_NAME_TO_ATTR.values()}
    for name in usage_names:
        kwargs[KU_NAME_TO_ATTR[name]] = True
    return kwargs


def build_key_usage_extension(usage_names: List[str]) -> x509.KeyUsage:
    return x509.KeyUsage(**build_key_usage_kwargs(usage_names))


def normalize_ca_eku(eku_items, is_root: bool) -> Tuple[Optional[List[str]], Optional[str]]:
    """
    Normalize EKU for CA creation.
    None input → (None, None) so upstream applies RFC defaults.
    Empty list → ([], None) for no EKU extension.
    """
    if eku_items is None:
        return None, None
    if not isinstance(eku_items, list):
        return [], 'extendedKeyUsage must be an array'
    if not eku_items:
        return [], None
    if is_root:
        return [], 'Extended Key Usage is not recommended on root CA certificates'
    oids, err = normalize_extra_ekus(eku_items)
    if err:
        return [], err
    return oids, None


def build_extended_key_usage_extension(eku_names: List[str]) -> Optional[x509.ExtendedKeyUsage]:
    if not eku_names:
        return None
    oids, err = normalize_extra_ekus(eku_names)
    if err:
        raise ValueError(err)
    return x509.ExtendedKeyUsage(to_object_identifiers(oids))
