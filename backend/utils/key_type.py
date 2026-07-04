"""Normalize key type / curve strings from UI and API payloads."""
from __future__ import annotations

import re

RSA_SIZES = frozenset({'2048', '3072', '4096'})

# Canonical TrustStoreService KEY_TYPES names for EC curves.
_EC_ALIASES: dict[str, str] = {
    'p-256': 'prime256v1',
    'p256': 'prime256v1',
    'nistp-256': 'prime256v1',
    'nistp256': 'prime256v1',
    'secp256r1': 'prime256v1',
    'prime256v1': 'prime256v1',
    'ec-p256': 'prime256v1',
    'ecdsa-p256': 'prime256v1',
    'p-384': 'secp384r1',
    'p384': 'secp384r1',
    'nistp-384': 'secp384r1',
    'nistp384': 'secp384r1',
    'secp384r1': 'secp384r1',
    'ec-p384': 'secp384r1',
    'ecdsa-p384': 'secp384r1',
    'p-521': 'secp521r1',
    'p521': 'secp521r1',
    'nistp-521': 'secp521r1',
    'nistp521': 'secp521r1',
    'secp521r1': 'secp521r1',
    'ec-p521': 'secp521r1',
    'ecdsa-p521': 'secp521r1',
}

_EC_ERROR_HINT = (
    'EC curve must be P-256, P-384, or P-521 '
    '(aliases: secp256r1/prime256v1, secp384r1, secp521r1)'
)


def _ec_alias_key(token: str) -> str:
    """Collapse whitespace/hyphens for alias lookup."""
    return re.sub(r'[\s_]+', '', token.lower())


def normalize_ec_curve(value: str) -> str:
    """Map UI / OpenSSL curve names to TrustStore KEY_TYPES EC identifiers."""
    raw = (value or '').strip()
    if not raw:
        raise ValueError(_EC_ERROR_HINT)

    lowered = raw.lower()
    lowered = re.sub(r'^(ecdsa|ec)\s*', '', lowered)
    lowered = re.sub(r'^nist\s+', '', lowered)

    key = _ec_alias_key(lowered)
    if key in _EC_ALIASES:
        return _EC_ALIASES[key]

    raise ValueError(_EC_ERROR_HINT)


def parse_csr_key_type(key_algo_full: str) -> str:
    """Parse frontend key_type (e.g. ``RSA 2048``, ``EC P-256``) for CSR generation."""
    raw = (key_algo_full or 'RSA 2048').strip()
    upper = raw.upper()

    if upper.startswith('RSA') or re.fullmatch(r'\d{4}', raw):
        size = re.sub(r'^RSA\s*', '', raw, flags=re.IGNORECASE).strip() or '2048'
        if size not in RSA_SIZES:
            raise ValueError('RSA key size must be 2048, 3072, or 4096')
        return size

    if (
        'EC' in upper
        or 'ECDSA' in upper
        or 'SECP' in upper
        or 'PRIME' in upper
        or re.search(r'P-\d{3}', upper)
    ):
        return normalize_ec_curve(raw)

    raise ValueError(f'Unsupported key type: {raw}')
