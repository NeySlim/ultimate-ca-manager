"""Normalize key type / curve strings from UI and API payloads."""
from __future__ import annotations

import re

from utils import key_algorithms

RSA_SIZES = frozenset(a.trust_store_id for a in key_algorithms.algorithms('RSA'))

# Spellings of each registered curve, mapped to its TrustStoreService KEY_TYPES id.
_EC_ALIASES: dict[str, str] = {
    name: alg.trust_store_id
    for alg in key_algorithms.algorithms('EC')
    for name in (alg.label, *alg.curve_names, *alg.aliases)
}

_EC_ERROR_HINT = (
    'EC curve must be P-256, P-384, or P-521 '
    '(aliases: secp256r1/prime256v1, secp384r1, secp521r1)'
)


def _ec_alias_key(token: str) -> str:
    """Collapse whitespace, hyphens and underscores for alias lookup."""
    return re.sub(r'[\s_-]+', '', token.lower())


# Lookup keys are pre-collapsed with _ec_alias_key (no spaces/hyphens/underscores).
_EC_COLLAPSED_ALIASES: dict[str, str] = {
    _ec_alias_key(k): v for k, v in _EC_ALIASES.items()
}


def normalize_ec_curve(value: str) -> str:
    """Map UI / OpenSSL curve names to TrustStore KEY_TYPES EC identifiers."""
    raw = (value or '').strip()
    if not raw:
        raise ValueError(_EC_ERROR_HINT)

    key = _ec_alias_key(raw)
    if key in _EC_COLLAPSED_ALIASES:
        return _EC_COLLAPSED_ALIASES[key]

    # Prefix-stripped forms: 'EC P-256', 'ECDSA-P384', 'NIST P-521', ...
    stripped = re.sub(r'^(ecdsa|ec|nist)[\s_-]*', '', raw.lower())
    key = _ec_alias_key(stripped)
    if key in _EC_COLLAPSED_ALIASES:
        return _EC_COLLAPSED_ALIASES[key]

    raise ValueError(_EC_ERROR_HINT)


def parse_issue_key_type(
    key_type: str | None = None,
    key_size: str | int | None = None,
    *,
    curve: str | None = None,
) -> str:
    """Normalize Issue Certificate ``key_type``/``key_size`` to TrustStore KEY_TYPES id."""
    raw_type = str(key_type or 'rsa').strip()
    raw_size = str(key_size if key_size is not None else '2048').strip()

    if ' ' in raw_type and not curve:
        return parse_csr_key_type(raw_type)

    kt = raw_type.lower()
    if kt in ('ec', 'ecdsa'):
        if curve:
            return normalize_ec_curve(curve)
        if raw_size.isdigit() and int(raw_size) in (256, 384, 521):
            return normalize_ec_curve(f'P-{raw_size}')
        return normalize_ec_curve(raw_size)

    if kt == 'rsa':
        size = re.sub(r'^rsa\s*', '', raw_size, flags=re.IGNORECASE).strip() or raw_size
        if size not in RSA_SIZES:
            raise ValueError('RSA key size must be 2048, 3072, or 4096')
        return size

    raise ValueError(f'Unsupported key type: {raw_type}')


def fill_key_params_from_template(key_type, key_size, template_key_type):
    """Default unset ``key_type``/``key_size`` from a template's ``"RSA-2048"`` /
    ``"EC-P384"`` string, for the API paths that mirror the UI's template prefill.

    ``key_size`` is only inherited when the request's algorithm still matches the
    template's, so an explicit ``key_type=rsa`` never picks up an EC curve (#318).
    Returns the (possibly filled) ``(key_type, key_size)`` pair unchanged in type.
    """
    if not template_key_type:
        return key_type, key_size
    tpl_algo, _, tpl_size = template_key_type.partition('-')
    if not key_type:
        key_type = tpl_algo
    if not key_size and tpl_size:
        tpl_is_ec = tpl_algo.strip().lower() in ('ec', 'ecdsa')
        req_is_ec = str(key_type or 'rsa').strip().lower() in ('ec', 'ecdsa')
        if tpl_is_ec == req_is_ec:
            key_size = tpl_size
    return key_type, key_size


def issue_key_type_from_template(template_key_type) -> str | None:
    """A template's ``"RSA-2048"`` / ``"EC-P384"`` as a KEY_TYPES id.

    Templates are stored in their own vocabulary -- `api/v2/templates`
    validates against `RSA-2048` / `EC-P256` -- while key generation speaks
    the TrustStore one, `2048` / `prime256v1`. The HTTP issuance path
    translates with `fill_key_params_from_template` before calling the
    service; the service's own template handling assigned `template.key_type`
    straight through, so issuing against a template from any caller that did
    not pre-translate died on `Unsupported key type: RSA-2048`.
    """
    if not template_key_type:
        return None
    algo, size = fill_key_params_from_template(None, None, template_key_type)
    return parse_issue_key_type(algo, size)


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


# ---------------------------------------------------------------------------
# Public-key strength policy for protocol enrollment (EST / SCEP)
# ---------------------------------------------------------------------------
# EST (RFC 7030 §3.7) and SCEP (RFC 8894) both defer key-strength policy to the
# local CA. UCM enforces the same floor it applies to UI/API issuance: RSA >=
# 2048 and NIST P-256/384/521 for EC. Legacy/edge curves and short RSA keys are
# refused so a weak (e.g. 512-bit) or exotic key never gets a CA signature.
MIN_RSA_BITS = 2048
# And a ceiling, which there was none of. Key size is attacker-chosen on every
# enrollment path: signing and later verifying a 65536-bit RSA key costs orders
# of magnitude more than a 4096-bit one, on the CA and on every relying party
# afterwards. 8192 is above anything a real deployment asks for.
MAX_RSA_BITS = 8192
_ALLOWED_EC_CURVES = frozenset(
    c for a in key_algorithms.algorithms('EC') for c in a.curve_names)


def validate_enrollment_public_key(public_key) -> str | None:
    """Return an error string if *public_key* is too weak to certify, else None.

    Accepts a cryptography public-key object (from a parsed CSR). Ed25519 /
    Ed448 are accepted (fixed, strong). Unknown key types are rejected — an
    enrollment endpoint should not sign a key it cannot assess.
    """
    family = key_algorithms.family_for_public_key(public_key)

    if family == 'RSA':
        bits = public_key.key_size
        if bits < MIN_RSA_BITS:
            return f'RSA key too small ({bits} bits); minimum is {MIN_RSA_BITS}'
        if bits > MAX_RSA_BITS:
            return f'RSA key too large ({bits} bits); maximum is {MAX_RSA_BITS}'
        return None

    if family == 'EC':
        curve = public_key.curve.name.lower()
        if curve not in _ALLOWED_EC_CURVES:
            return f'Unsupported EC curve {public_key.curve.name!r} (allowed: P-256/384/521)'
        return None

    if family in ('ED25519', 'ED448'):
        return None

    return f'Unsupported public key type: {type(public_key).__name__}'
