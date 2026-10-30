"""Normalize key type / curve strings from UI and API payloads."""
from __future__ import annotations

import re

from cryptography.exceptions import UnsupportedAlgorithm

import fips_mode
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
    '(aliases: secp256r1/prime256v1, secp384r1, secp521r1) '
    'or, outside FIPS mode, Brainpool EC-BP256, EC-BP384 or EC-BP512 (brainpoolP256r1/P384r1/P512r1)'
)


def _ec_alias_key(token: str) -> str:
    """Collapse whitespace, hyphens and underscores for alias lookup."""
    return re.sub(r'[\s_-]+', '', token.lower())


# Lookup keys are pre-collapsed with _ec_alias_key (no spaces/hyphens/underscores).
_EC_COLLAPSED_ALIASES: dict[str, str] = {
    _ec_alias_key(k): v for k, v in _EC_ALIASES.items()
}


def _fips_checked(trust_store_id: str) -> str:
    """*trust_store_id*, or FipsRestricted when FIPS mode excludes its curve."""
    alg = key_algorithms.get(trust_store_id)
    if alg is not None and not alg.fips_approved:
        fips_mode.refuse(f'{alg.display} keys')
    return trust_store_id


def normalize_ec_curve(value: str) -> str:
    """Map UI / OpenSSL curve names to TrustStore KEY_TYPES EC identifiers."""
    return _fips_checked(_lookup_ec_curve(value))


def _lookup_ec_curve(value: str) -> str:
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


# Families a request names alone, with the parameter in key_size ('ml-dsa' + '65')
_REQUEST_FAMILIES = {'rsa': 'RSA', 'ec': 'EC', 'ecdsa': 'EC', 'mldsa': 'ML-DSA'}


def _request_family(key_type) -> str | None:
    token = str(key_type or 'rsa').strip()
    family = _REQUEST_FAMILIES.get(_ec_alias_key(token))
    if family is None:
        alg = key_algorithms.get(token)
        family = alg.family if alg else None
    return family


def _registry_key_type(raw_type: str, raw_size) -> str | None:
    """KEY_TYPES id of a key outside RSA and EC, named by its label ('ML-DSA-65') or
    by family and parameter ('ml-dsa' + '65'); None when *raw_type* names no such key."""
    alg = key_algorithms.get(raw_type)
    size = str(raw_size or '').strip()
    if alg is None:
        family = _REQUEST_FAMILIES.get(_ec_alias_key(raw_type))
        if family in (None, 'RSA', 'EC'):
            return None
        choices = [a.param for a in key_algorithms.algorithms(family)]
        if not choices:
            raise ValueError(f'{family} keys are not available on this build: they need OpenSSL 3.5 or later')
        alg = key_algorithms.get(f'{family}-{size}') if size.isdigit() else key_algorithms.get(size)
        if alg is None or alg.family != family:
            raise ValueError(f'{family} key size must be one of {", ".join(choices)}')
    if alg.family in ('RSA', 'EC') or alg.trust_store_id is None:
        return None
    # A full label wins over a numeric default size, never over another key named by level or label
    other = key_algorithms.get(f'{alg.family}-{size}') if size.isdigit() else key_algorithms.get(size)
    if other is not None and other is not alg:
        raise ValueError(f'key type {alg.label} and key size {size} name different keys')
    return alg.trust_store_id


def parse_issue_key_type(
    key_type: str | None = None,
    key_size: str | int | None = None,
    *,
    curve: str | None = None,
) -> str:
    """Normalize Issue Certificate ``key_type``/``key_size`` to TrustStore KEY_TYPES id."""
    raw_type = str(key_type or 'rsa').strip()
    raw_size = str(key_size if key_size is not None else '2048').strip()

    if not curve:
        registry_id = _registry_key_type(raw_type, raw_size)
        if registry_id is not None:
            return registry_id

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
    """Default unset ``key_type``/``key_size`` from a template's registry label
    (``"RSA-2048"``, ``"EC-P384"``, ``"ML-DSA-65"``), for the API paths that
    mirror the UI's template prefill.

    ``key_size`` is only inherited when the request's family still matches the
    template's, so an explicit ``key_type=rsa`` never picks up an EC curve (#318).
    A label the registry does not know is passed on for the parser to refuse.
    """
    if not template_key_type:
        return key_type, key_size
    alg = key_algorithms.get(template_key_type)
    if alg is None:
        return key_type or template_key_type, key_size
    if not key_type:
        key_type = alg.family
    # A request that names a full label ('ML-DSA-87') already has its parameter
    if (not key_size and alg.param and key_algorithms.get(key_type) is None
            and _request_family(key_type) == alg.family):
        key_size = alg.param
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
    registry_id = _registry_key_type(raw, None)
    if registry_id is not None:
        return registry_id
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
        or re.search(r'BRAINPOOL|\bBP-?\d{3}', upper)
    ):
        return normalize_ec_curve(raw)

    raise ValueError(f'Unsupported key type: {raw}')


# ---------------------------------------------------------------------------
# Public-key strength policy for protocol enrollment (EST / SCEP)
# ---------------------------------------------------------------------------
# EST (RFC 7030 §3.7) and SCEP (RFC 8894) both defer key-strength policy to the
# local CA. UCM enforces the same floor it applies to UI/API issuance: RSA >=
# 2048, NIST P-256/384/521 and, outside FIPS mode, Brainpool for EC. Other
# curves and short RSA keys are refused so a weak or exotic key is never signed.
MIN_RSA_BITS = 2048
# And a ceiling, which there was none of. Key size is attacker-chosen on every
# enrollment path: signing and later verifying a 65536-bit RSA key costs orders
# of magnitude more than a 4096-bit one, on the CA and on every relying party
# afterwards. 8192 is above anything a real deployment asks for.
MAX_RSA_BITS = 8192
_ALLOWED_EC_CURVES = frozenset(
    c for a in key_algorithms.algorithms('EC') for c in a.curve_names)
_FIPS_EC_CURVES = frozenset(
    c for a in key_algorithms.algorithms('EC') if a.fips_approved for c in a.curve_names)


def validate_enrollment_public_key(public_key) -> str | None:
    """Return an error string if *public_key* is too weak to certify, else None.

    Accepts a cryptography public-key object (from a parsed CSR). Ed25519 /
    Ed448 and, outside FIPS mode, ML-DSA are accepted. Unknown key types are rejected — an
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
            return (f'Unsupported EC curve {public_key.curve.name!r} '
                    f'(allowed: P-256/384/521, Brainpool P256r1/P384r1/P512r1)')
        if fips_mode.enabled() and curve not in _FIPS_EC_CURVES:
            return f'EC curve {public_key.curve.name!r} is not available in FIPS mode'
        return None

    if family in ('ED25519', 'ED448'):
        return None

    if family == 'ML-DSA':
        if fips_mode.enabled():
            return f'{key_algorithms.label_for_public_key(public_key)} keys are not available in FIPS mode'
        return None

    return f'Unsupported public key type: {type(public_key).__name__}'


def unsignable_csr_key(csr) -> str | None:
    """Refusal for a CSR whose key this build cannot load (SLH-DSA), None otherwise.
    Checked before ``is_signature_valid``, which raises on such a key."""
    try:
        csr.public_key()
    except UnsupportedAlgorithm:
        oid = csr.public_key_algorithm_oid
        info = key_algorithms.post_quantum_info(oid)
        return f'{info.label if info else oid.dotted_string} keys are not signable by this instance'
    return None


def validate_enrollment_csr(csr) -> str | None:
    """:func:`validate_enrollment_public_key` for a CSR, whose key this build may
    not load at all (SLH-DSA): such a key is refused, never signed."""
    return unsignable_csr_key(csr) or validate_enrollment_public_key(csr.public_key())
