"""OIDC ID token verification using provider discovery and JWKS."""

import base64
import binascii
import hmac
import json
import logging
import math
import numbers
import re
import threading
import time

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec, ed448, ed25519, padding, rsa
from cryptography.hazmat.primitives.asymmetric.utils import encode_dss_signature

import fips_mode
from utils.key_algorithms import fips_rsa_bits_approved
from utils.ssrf_protection import safe_request_get, validate_url_not_cloud_metadata

logger = logging.getLogger(__name__)

# RFC 7518 §3.1 and RFC 8037: (kty, curve for EC, hash). Never none nor HS*: a shared
# secret would make the client secret a signing key (RFC 8725 §3.1).
_ALGORITHMS = {
    'RS256': ('RSA', None, hashes.SHA256), 'RS384': ('RSA', None, hashes.SHA384),
    'RS512': ('RSA', None, hashes.SHA512), 'PS256': ('RSA', None, hashes.SHA256),
    'PS384': ('RSA', None, hashes.SHA384), 'PS512': ('RSA', None, hashes.SHA512),
    'ES256': ('EC', 'P-256', hashes.SHA256), 'ES384': ('EC', 'P-384', hashes.SHA384),
    'ES512': ('EC', 'P-521', hashes.SHA512), 'EdDSA': ('OKP', None, None),
}
_ALLOWED_ALGORITHMS = frozenset(_ALGORITHMS)
_EC_CURVES = {'P-256': (ec.SECP256R1, 32), 'P-384': (ec.SECP384R1, 48), 'P-521': (ec.SECP521R1, 66)}
_OKP_CURVES = {'Ed25519': ed25519.Ed25519PublicKey, 'Ed448': ed448.Ed448PublicKey}
# RFC 7518 §3.3: "A key of size 2048 bits or larger MUST be used with these algorithms."
_MIN_RSA_BITS = 2048
_SHOWN_ALGORITHM = re.compile(r'[A-Za-z0-9+._-]{1,32}')
_CACHE_TTL_SECONDS = 3600
# A cached document is read again ahead of its TTL at most once per window: a burst of forged
# tokens costs one outbound request, not one per attempt
_REFRESH_INTERVAL_SECONDS = 60
_CLOCK_SKEW_SECONDS = 60
_MAX_DOCUMENT_BYTES = 1024 * 1024
_cache = {}
_refreshed = {}  # cache key -> time.monotonic() of its last early reading
_cache_lock = threading.Lock()


class OIDCValidationError(ValueError):
    """An ID token or provider metadata failed OIDC validation."""


def clear_oidc_cache():
    """Clear cached discovery documents and JWKS (used on config changes/tests)."""
    with _cache_lock:
        _cache.clear()
        _refreshed.clear()


def _b64url_decode(value):
    if not isinstance(value, str) or not value:
        raise OIDCValidationError('invalid base64url value')
    try:
        return base64.urlsafe_b64decode(value + ('=' * (-len(value) % 4)))
    except (ValueError, binascii.Error) as exc:
        raise OIDCValidationError('invalid base64url value') from exc


def _decode_json_segment(value, label):
    try:
        decoded = json.loads(_b64url_decode(value))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise OIDCValidationError(f'invalid ID token {label}') from exc
    if not isinstance(decoded, dict):
        raise OIDCValidationError(f'invalid ID token {label}')
    return decoded


def _parse_token(id_token):
    if not isinstance(id_token, str):
        raise OIDCValidationError('missing ID token')
    parts = id_token.split('.')
    if len(parts) != 3 or not all(parts):
        raise OIDCValidationError('malformed ID token')
    header = _decode_json_segment(parts[0], 'header')
    claims = _decode_json_segment(parts[1], 'claims')
    signature = _b64url_decode(parts[2])
    return header, claims, signature, f'{parts[0]}.{parts[1]}'.encode('ascii')


def decode_id_token_unverified(id_token):
    """Decode claims only for the explicit verification-disabled compatibility mode."""
    _header, claims, _signature, _signing_input = _parse_token(id_token)
    return claims


def _cache_get(key):
    now = time.monotonic()
    with _cache_lock:
        entry = _cache.get(key)
        if entry and entry[0] > now:
            return entry[1]
        _cache.pop(key, None)
    return None


def _cache_put(key, value):
    with _cache_lock:
        _cache[key] = (time.monotonic() + _CACHE_TTL_SECONDS, value)


def _may_refresh(key):
    """Whether ``key`` may be read again ahead of its TTL now; counts the reading."""
    now = time.monotonic()
    with _cache_lock:
        last = _refreshed.get(key)
        if last is not None and now - last < _REFRESH_INTERVAL_SECONDS:
            return False
        _refreshed[key] = now
        return True


def _cache_invalidate(key):
    with _cache_lock:
        _cache.pop(key, None)


def _fetch_json(url, verify, document_name):
    try:
        validate_url_not_cloud_metadata(url)
        response = safe_request_get(
            url,
            timeout=10,
            verify=verify,
            allow_redirects=False,
        )
    except Exception as exc:
        raise OIDCValidationError(f'{document_name} endpoint is not reachable') from exc

    if not getattr(response, 'ok', False):
        raise OIDCValidationError(f'{document_name} endpoint returned an error')
    content = getattr(response, 'content', b'')
    if len(content) > _MAX_DOCUMENT_BYTES:
        raise OIDCValidationError(f'{document_name} document is too large')
    try:
        data = response.json()
    except (TypeError, ValueError, json.JSONDecodeError) as exc:
        raise OIDCValidationError(f'{document_name} document is invalid') from exc
    if not isinstance(data, dict):
        raise OIDCValidationError(f'{document_name} document is invalid')
    return data


def _provider_cache_key(provider, kind, url):
    return (getattr(provider, 'id', None), kind, url)


def _get_discovery(provider, issuer, verify, force_refresh=False):
    """The discovery document; ``force_refresh`` reads it again (kept cached until that succeeds)."""
    discovery_url = f"{issuer.rstrip('/')}/.well-known/openid-configuration"
    key = _provider_cache_key(provider, 'discovery', discovery_url)
    cached = _cache_get(key)
    if cached is not None and not (force_refresh and _may_refresh(key)):
        return cached

    document = _fetch_json(discovery_url, verify, 'OIDC discovery')
    if document.get('issuer') != issuer:
        raise OIDCValidationError('OIDC discovery issuer mismatch')
    jwks_uri = document.get('jwks_uri')
    if not isinstance(jwks_uri, str) or not jwks_uri:
        raise OIDCValidationError('OIDC discovery has no JWKS URI')
    try:
        validate_url_not_cloud_metadata(jwks_uri)
    except ValueError as exc:
        raise OIDCValidationError('OIDC discovery returned a forbidden JWKS URI') from exc
    _cache_put(key, document)
    return document


def _get_jwks(provider, issuer, verify, force_refresh=False):
    jwks_uri = getattr(provider, 'oauth2_jwks_uri', None)
    if not jwks_uri:
        jwks_uri = _get_discovery(provider, issuer, verify)['jwks_uri']

    key = _provider_cache_key(provider, 'jwks', jwks_uri)
    if force_refresh and _may_refresh(key):
        _cache_invalidate(key)
    else:
        cached = _cache_get(key)
        if cached is not None:
            return cached

    document = _fetch_json(jwks_uri, verify, 'JWKS')
    keys = document.get('keys')
    if not isinstance(keys, list):
        raise OIDCValidationError('JWKS document has no keys')
    _cache_put(key, document)
    return document


def _select_jwk(document, kid, algorithm):
    matches = []
    for jwk in document.get('keys', []):
        if not isinstance(jwk, dict) or jwk.get('kid') != kid:
            continue
        if jwk.get('use') not in (None, 'sig'):
            continue
        if jwk.get('alg') not in (None, algorithm):
            continue
        if 'verify' not in jwk.get('key_ops', ['verify']):
            continue
        matches.append(jwk)
    if len(matches) != 1:
        raise OIDCValidationError('no unique matching JWKS signing key')
    return matches[0]


def _jwk_int(jwk, field):
    try:
        raw = _b64url_decode(jwk[field])
    except (KeyError, OIDCValidationError) as exc:
        raise OIDCValidationError('malformed JWKS signing key') from exc
    if not raw:
        raise OIDCValidationError('malformed JWKS signing key')
    return int.from_bytes(raw, 'big')


def _public_key_from_jwk(jwk, algorithm):
    """The key ``jwk`` holds, once its type and curve are the ones ``algorithm`` names:
    a key never verifies a token announced for another type (RFC 8725 §3.1)."""
    kty, curve, _hash = _ALGORITHMS[algorithm]
    key_kty, key_crv = jwk.get('kty'), jwk.get('crv')
    if key_kty != kty or (curve is not None and key_crv != curve):
        raise OIDCValidationError('JWKS key type does not match algorithm')
    try:
        if key_kty == 'RSA':
            key = rsa.RSAPublicNumbers(_jwk_int(jwk, 'e'), _jwk_int(jwk, 'n')).public_key()
            if key.key_size < _MIN_RSA_BITS:
                raise OIDCValidationError(f'JWKS RSA key is shorter than {_MIN_RSA_BITS} bits')
            if fips_mode.enabled() and not fips_rsa_bits_approved(key.key_size):
                raise OIDCValidationError(
                    f'RSA key of {key.key_size} bits not available in FIPS mode')
            return key
        if key_kty == 'EC' and key_crv in _EC_CURVES:
            return ec.EllipticCurvePublicNumbers(
                _jwk_int(jwk, 'x'), _jwk_int(jwk, 'y'), _EC_CURVES[key_crv][0]()).public_key()
        if key_kty == 'OKP' and key_crv in _OKP_CURVES:
            # The rule of every EdDSA key in FIPS mode: allowed when the loaded module approves it
            fips_mode.refuse_unless_approved(key_crv.upper(), f'{key_crv} ID token signatures')
            try:
                point = _b64url_decode(jwk.get('x'))
            except OIDCValidationError as exc:
                raise OIDCValidationError('malformed JWKS signing key') from exc
            return _OKP_CURVES[key_crv].from_public_bytes(point)
        raise OIDCValidationError('JWKS key type does not match algorithm')
    except fips_mode.FipsRestricted as exc:
        raise OIDCValidationError(str(exc)) from exc
    except OIDCValidationError:
        raise
    except (TypeError, ValueError, KeyError) as exc:
        raise OIDCValidationError('malformed JWKS signing key') from exc


def _verify_signature(jwk, algorithm, signing_input, signature):
    key = _public_key_from_jwk(jwk, algorithm)
    _kty, _curve, hash_class = _ALGORITHMS[algorithm]
    if algorithm.startswith('RS'):
        key.verify(signature, signing_input, padding.PKCS1v15(), hash_class())
    elif algorithm.startswith('PS'):
        # RFC 7518 §3.5: MGF1 with the same hash, salt as long as the hash output
        key.verify(signature, signing_input,
                   padding.PSS(padding.MGF1(hash_class()), hash_class.digest_size), hash_class())
    elif algorithm.startswith('ES'):
        # RFC 7518 §3.4: R || S, each as long as the order of the key's curve
        size = _EC_CURVES[jwk['crv']][1]
        if len(signature) != 2 * size:
            raise InvalidSignature
        r = int.from_bytes(signature[:size], 'big')
        s = int.from_bytes(signature[size:], 'big')
        key.verify(encode_dss_signature(r, s), signing_input, ec.ECDSA(hash_class()))
    else:
        key.verify(signature, signing_input)


def _shown(algorithm):
    """``algorithm`` as a refusal names it: a JWS name as is, anything else escaped and cut."""
    if isinstance(algorithm, str) and _SHOWN_ALGORITHM.fullmatch(algorithm):
        return algorithm
    return json.dumps(algorithm, ensure_ascii=True)[:40]


def _check_discovery_algorithm(provider, issuer, verify, algorithm):
    """OIDC Discovery: the header algorithm is one the provider says it signs ID tokens with.

    Read only where the discovery document is loaded anyway (no JWKS URI configured). The
    caller has already refused an algorithm outside the product's list, whatever this one says."""
    if getattr(provider, 'oauth2_jwks_uri', None):
        return
    # An algorithm the provider added since the cached reading: read once more (_may_refresh)
    for force_refresh in (False, True):
        supported = _get_discovery(provider, issuer, verify, force_refresh=force_refresh).get(
            'id_token_signing_alg_values_supported')
        if supported is None:
            return
        if not isinstance(supported, list):
            raise OIDCValidationError(
                'OIDC discovery has an invalid id_token_signing_alg_values_supported')
        if algorithm in supported:
            return
    raise OIDCValidationError(f'ID token signing algorithm {algorithm} is not listed '
                              'in the provider discovery document')


def _numeric_date(claims, name, required=False):
    value = claims.get(name)
    if value is None:
        if required:
            raise OIDCValidationError(f'ID token is missing {name}')
        return None
    if isinstance(value, bool) or not isinstance(value, numbers.Real):
        raise OIDCValidationError(f'ID token has invalid {name}')
    value = float(value)
    if not math.isfinite(value):
        raise OIDCValidationError(f'ID token has invalid {name}')
    return value


def _validate_claims(claims, issuer, client_id, expected_nonce):
    now = time.time()
    if claims.get('iss') != issuer:
        raise OIDCValidationError('ID token issuer mismatch')

    audience = claims.get('aud')
    audiences = [audience] if isinstance(audience, str) else audience
    if not isinstance(audiences, list) or not audiences or not all(
            isinstance(item, str) and item for item in audiences):
        raise OIDCValidationError('ID token has invalid audience')
    if client_id not in audiences:
        raise OIDCValidationError('ID token audience mismatch')
    # OIDC Core §3.1.3.7 steps 4-5: azp required with several audiences, and
    # whenever present it must be this client.
    azp = claims.get('azp')
    if (len(audiences) > 1 or azp is not None) and azp != client_id:
        raise OIDCValidationError('ID token authorized party mismatch')

    expires_at = _numeric_date(claims, 'exp', required=True)
    issued_at = _numeric_date(claims, 'iat', required=True)
    not_before = _numeric_date(claims, 'nbf')
    if now > expires_at + _CLOCK_SKEW_SECONDS:
        raise OIDCValidationError('ID token has expired')
    if issued_at > now + _CLOCK_SKEW_SECONDS:
        raise OIDCValidationError('ID token issued-at time is in the future')
    if not_before is not None and not_before > now + _CLOCK_SKEW_SECONDS:
        raise OIDCValidationError('ID token is not yet valid')

    nonce = claims.get('nonce')
    if not expected_nonce:
        raise OIDCValidationError('no session nonce')
    if not isinstance(nonce, str) or not hmac.compare_digest(
            nonce, expected_nonce):
        raise OIDCValidationError('ID token nonce mismatch')
    if not isinstance(claims.get('sub'), str) or not claims['sub']:
        raise OIDCValidationError('ID token is missing subject')


def _configured_issuer_and_client_id(provider):
    """Both non-empty strings, else nothing to match iss and aud against (step 2-3)."""
    issuer = getattr(provider, 'oauth2_issuer', None)
    client_id = getattr(provider, 'oauth2_client_id', None)
    if not isinstance(issuer, str) or not issuer:
        raise OIDCValidationError('OIDC issuer is not configured')
    if not isinstance(client_id, str) or not client_id:
        raise OIDCValidationError('OIDC client ID is not configured')
    return issuer, client_id


def unverified_claims_error(claims, provider, expected_nonce):
    """Why a token whose signature is not verified (compatibility mode) fails another check, or None.

    OIDC Core §3.1.3.7 steps 2-5 and 9-11 (iss, aud, azp, exp, iat, nonce) still
    apply; step 6 lets TLS stand in for the signature only.
    """
    try:
        issuer, client_id = _configured_issuer_and_client_id(provider)
        _validate_claims(claims or {}, issuer, client_id, expected_nonce)
    except OIDCValidationError as exc:
        return str(exc)
    return None


def unverified_claims_are_valid(claims, provider, expected_nonce):
    """True when a token read in compatibility mode passes every check but the signature."""
    return unverified_claims_error(claims, provider, expected_nonce) is None


def verify_id_token(id_token, provider, expected_nonce, verify=True, ssl_verify=True):
    """Verify an OIDC ID token and return its trusted claims.

    Verification is fail-closed by default. ``verify=False`` is only for the
    provider's explicit compatibility setting; nonce binding is still checked.
    """
    if not verify:
        claims = decode_id_token_unverified(id_token)
        nonce = claims.get('nonce')
        if expected_nonce and (
                not isinstance(nonce, str)
                or not hmac.compare_digest(nonce, expected_nonce)):
            raise OIDCValidationError('ID token nonce mismatch')
        return claims

    issuer, client_id = _configured_issuer_and_client_id(provider)
    try:
        validate_url_not_cloud_metadata(issuer)
    except ValueError as exc:
        raise OIDCValidationError('OIDC issuer is forbidden') from exc

    header, claims, signature, signing_input = _parse_token(id_token)
    algorithm = header.get('alg')
    kid = header.get('kid')
    if not isinstance(algorithm, str) or algorithm not in _ALLOWED_ALGORITHMS:
        raise OIDCValidationError(f'unsupported ID token signing algorithm {_shown(algorithm)}')
    if not isinstance(kid, str) or not kid:
        raise OIDCValidationError('ID token is missing key ID')
    _check_discovery_algorithm(provider, issuer, ssl_verify, algorithm)

    for force_refresh in (False, True):
        try:
            jwks = _get_jwks(provider, issuer, ssl_verify, force_refresh=force_refresh)
            jwk = _select_jwk(jwks, kid, algorithm)
            _verify_signature(jwk, algorithm, signing_input, signature)
            break
        except InvalidSignature:
            if force_refresh:
                raise OIDCValidationError('ID token signature is invalid')
        except OIDCValidationError as exc:
            if force_refresh or 'signing key' not in str(exc):
                raise
    else:  # pragma: no cover - loop always breaks or raises
        raise OIDCValidationError('ID token signature is invalid')

    _validate_claims(claims, issuer, client_id, expected_nonce)
    return claims
