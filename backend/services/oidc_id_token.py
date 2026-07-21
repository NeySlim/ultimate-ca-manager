"""OIDC ID token verification using provider discovery and JWKS."""

import base64
import binascii
import hmac
import json
import logging
import math
import numbers
import threading
import time

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec, padding, rsa
from cryptography.hazmat.primitives.asymmetric.utils import encode_dss_signature

from utils.ssrf_protection import safe_request_get, validate_url_not_cloud_metadata

logger = logging.getLogger(__name__)

_ALLOWED_ALGORITHMS = frozenset({'RS256', 'ES256'})
_CACHE_TTL_SECONDS = 3600
_CLOCK_SKEW_SECONDS = 60
_MAX_DOCUMENT_BYTES = 1024 * 1024
_cache = {}
_cache_lock = threading.Lock()


class OIDCValidationError(ValueError):
    """An ID token or provider metadata failed OIDC validation."""


def clear_oidc_cache():
    """Clear cached discovery documents and JWKS (used on config changes/tests)."""
    with _cache_lock:
        _cache.clear()


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


def _get_discovery(provider, issuer, verify):
    discovery_url = f"{issuer.rstrip('/')}/.well-known/openid-configuration"
    key = _provider_cache_key(provider, 'discovery', discovery_url)
    cached = _cache_get(key)
    if cached is not None:
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
    if force_refresh:
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
    try:
        if algorithm == 'RS256':
            if jwk.get('kty') != 'RSA':
                raise OIDCValidationError('JWKS key type does not match algorithm')
            return rsa.RSAPublicNumbers(
                _jwk_int(jwk, 'e'),
                _jwk_int(jwk, 'n'),
            ).public_key()

        if jwk.get('kty') != 'EC' or jwk.get('crv') != 'P-256':
            raise OIDCValidationError('JWKS key type does not match algorithm')
        return ec.EllipticCurvePublicNumbers(
            _jwk_int(jwk, 'x'),
            _jwk_int(jwk, 'y'),
            ec.SECP256R1(),
        ).public_key()
    except OIDCValidationError:
        raise
    except (TypeError, ValueError) as exc:
        raise OIDCValidationError('malformed JWKS signing key') from exc


def _verify_signature(jwk, algorithm, signing_input, signature):
    key = _public_key_from_jwk(jwk, algorithm)
    if algorithm == 'RS256':
        key.verify(signature, signing_input, padding.PKCS1v15(), hashes.SHA256())
        return
    if len(signature) != 64:
        raise InvalidSignature
    r = int.from_bytes(signature[:32], 'big')
    s = int.from_bytes(signature[32:], 'big')
    key.verify(encode_dss_signature(r, s), signing_input, ec.ECDSA(hashes.SHA256()))


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
    if len(audiences) > 1 and claims.get('azp') != client_id:
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
    if not expected_nonce or not isinstance(nonce, str) or not hmac.compare_digest(
            nonce, expected_nonce):
        raise OIDCValidationError('ID token nonce mismatch')
    if not isinstance(claims.get('sub'), str) or not claims['sub']:
        raise OIDCValidationError('ID token is missing subject')


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

    issuer = getattr(provider, 'oauth2_issuer', None)
    client_id = getattr(provider, 'oauth2_client_id', None)
    if not isinstance(issuer, str) or not issuer:
        raise OIDCValidationError('OIDC issuer is not configured')
    if not isinstance(client_id, str) or not client_id:
        raise OIDCValidationError('OIDC client ID is not configured')
    try:
        validate_url_not_cloud_metadata(issuer)
    except ValueError as exc:
        raise OIDCValidationError('OIDC issuer is forbidden') from exc

    header, claims, signature, signing_input = _parse_token(id_token)
    algorithm = header.get('alg')
    kid = header.get('kid')
    if algorithm not in _ALLOWED_ALGORITHMS:
        raise OIDCValidationError('unsupported ID token signing algorithm')
    if not isinstance(kid, str) or not kid:
        raise OIDCValidationError('ID token is missing key ID')

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
