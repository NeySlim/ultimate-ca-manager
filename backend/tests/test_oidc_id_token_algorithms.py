"""ID token signature algorithms: the JWS algorithms OIDC IdPs sign with, and the refusals
of RFC 8725 §3.1 and §3.2 (none, HMAC, key type or curve the header does not name)."""

import base64
import hashlib
import hmac
import json
import time
from types import SimpleNamespace

import pytest
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec, ed448, ed25519, padding, rsa
from cryptography.hazmat.primitives.asymmetric.utils import decode_dss_signature
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat

ISSUER = 'https://idp.example/realms/ucm'
JWKS_URI = 'https://idp.example/realms/ucm/jwks'
_HASHES = {'256': hashes.SHA256, '384': hashes.SHA384, '512': hashes.SHA512}
_CURVES = {'P-256': ec.SECP256R1, 'P-384': ec.SECP384R1, 'P-521': ec.SECP521R1}
_ES_CURVE = {'ES256': 'P-256', 'ES384': 'P-384', 'ES512': 'P-521'}
_KEYS = {}


def _b64(data):
    return base64.urlsafe_b64encode(data).rstrip(b'=').decode('ascii')


def _int_b64(value, size=None):
    size = size or (value.bit_length() + 7) // 8
    return _b64(value.to_bytes(size, 'big'))


def _rsa_key(bits=2048):
    if ('RSA', bits) not in _KEYS:
        _KEYS[('RSA', bits)] = rsa.generate_private_key(public_exponent=65537, key_size=bits)
    return _KEYS[('RSA', bits)]


def _key_for(alg, crv=None):
    if alg.startswith(('RS', 'PS')):
        return _rsa_key()
    if alg.startswith('ES'):
        crv = crv or _ES_CURVE[alg]
        if crv not in _KEYS:
            _KEYS[crv] = ec.generate_private_key(_CURVES[crv]())
        return _KEYS[crv]
    crv = crv or 'Ed25519'
    if crv not in _KEYS:
        maker = ed25519.Ed25519PrivateKey if crv == 'Ed25519' else ed448.Ed448PrivateKey
        _KEYS[crv] = maker.generate()
    return _KEYS[crv]


def _jwk(key, kid='k1', **extra):
    public = key.public_key()
    if isinstance(public, rsa.RSAPublicKey):
        n = public.public_numbers()
        jwk = {'kty': 'RSA', 'n': _int_b64(n.n), 'e': _int_b64(n.e)}
    elif isinstance(public, ec.EllipticCurvePublicKey):
        n = public.public_numbers()
        crv = {v.name: k for k, v in _CURVES.items()}[public.curve.name]
        size = (public.curve.key_size + 7) // 8
        jwk = {'kty': 'EC', 'crv': crv, 'x': _int_b64(n.x, size), 'y': _int_b64(n.y, size)}
    else:
        crv = 'Ed25519' if isinstance(public, ed25519.Ed25519PublicKey) else 'Ed448'
        jwk = {'kty': 'OKP', 'crv': crv,
               'x': _b64(public.public_bytes(Encoding.Raw, PublicFormat.Raw))}
    jwk.update(kid=kid, **extra)
    return {k: v for k, v in jwk.items() if v is not None}


def _sign(key, alg, signing_input):
    if alg.startswith('RS'):
        return key.sign(signing_input, padding.PKCS1v15(), _HASHES[alg[2:]]())
    if alg.startswith('PS'):
        digest = _HASHES[alg[2:]]
        return key.sign(signing_input, padding.PSS(padding.MGF1(digest()), digest.digest_size),
                        digest())
    if alg.startswith('ES'):
        r, s = decode_dss_signature(key.sign(signing_input, ec.ECDSA(_HASHES[alg[2:]]())))
        size = (key.curve.key_size + 7) // 8
        return r.to_bytes(size, 'big') + s.to_bytes(size, 'big')
    if alg.startswith('HS'):
        return hmac.new(key, signing_input, getattr(hashlib, f'sha{alg[2:]}')).digest()
    return key.sign(signing_input)


def _claims(**overrides):
    now = int(time.time())
    values = {'iss': ISSUER, 'aud': 'ucm-client', 'sub': 'user-123', 'exp': now + 300,
              'iat': now, 'nonce': 'session-nonce'}
    values.update(overrides)
    return values


def _token(key, alg, kid='k1', signature=None):
    header = _b64(json.dumps({'alg': alg, 'kid': kid}).encode())
    payload = _b64(json.dumps(_claims()).encode())
    signing_input = f'{header}.{payload}'.encode('ascii')
    if signature is None:
        signature = _sign(key, alg, signing_input)
    return f'{header}.{payload}.{_b64(signature)}'


class _Response:
    def __init__(self, data):
        self._data = data
        self.ok = True
        self.content = json.dumps(data).encode()

    def json(self):
        return self._data


def _provider(**overrides):
    values = {'id': 9, 'name': 'OIDC', 'oauth2_issuer': ISSUER,
              'oauth2_client_id': 'ucm-client', 'oauth2_jwks_uri': JWKS_URI}
    values.update(overrides)
    return SimpleNamespace(**values)


@pytest.fixture(autouse=True)
def _fresh_cache():
    from services.oidc_id_token import clear_oidc_cache
    clear_oidc_cache()
    yield
    clear_oidc_cache()


@pytest.fixture
def idp(monkeypatch):
    """Serves ``state['keys']`` as the JWKS and ``state['discovery']`` as the discovery document."""
    state = {'keys': [], 'discovery': {}, 'fetched': []}

    def fetch(url, **_kwargs):
        state['fetched'].append(url)
        if url.endswith('/.well-known/openid-configuration'):
            return _Response(dict({'issuer': ISSUER, 'jwks_uri': JWKS_URI}, **state['discovery']))
        return _Response({'keys': state['keys']})

    monkeypatch.setattr('services.oidc_id_token.safe_request_get', fetch)
    return state


def _verify(token, **provider):
    from services.oidc_id_token import verify_id_token
    return verify_id_token(token, _provider(**provider), 'session-nonce', verify=True)


ACCEPTED = ['RS256', 'RS384', 'RS512', 'PS256', 'PS384', 'PS512',
            'ES256', 'ES384', 'ES512', 'EdDSA']


@pytest.mark.parametrize('alg', ACCEPTED)
@pytest.mark.parametrize('jwk_alg', [True, False], ids=['key-alg', 'no-key-alg'])
def test_each_listed_algorithm_verifies(idp, alg, jwk_alg):
    key = _key_for(alg)
    idp['keys'] = [_jwk(key, alg=alg if jwk_alg else None, use='sig')]
    assert _verify(_token(key, alg))['sub'] == 'user-123'


def test_eddsa_with_ed448_verifies(idp):
    key = _key_for('EdDSA', 'Ed448')
    idp['keys'] = [_jwk(key, alg='EdDSA')]
    assert _verify(_token(key, 'EdDSA'))['sub'] == 'user-123'


def test_a_forged_signature_is_refused_for_each_algorithm(idp):
    from services.oidc_id_token import OIDCValidationError, clear_oidc_cache
    for alg in ACCEPTED:
        clear_oidc_cache()
        key = _key_for(alg)
        idp['keys'] = [_jwk(key)]
        good = _token(key, alg)
        header, payload, sig = good.split('.')
        other = _b64(json.dumps(_claims(sub='admin')).encode())
        with pytest.raises(OIDCValidationError, match='signature is invalid'):
            _verify(f'{header}.{other}.{sig}')


def test_none_is_refused_and_named(idp):
    from services.oidc_id_token import OIDCValidationError
    idp['keys'] = [_jwk(_rsa_key())]
    with pytest.raises(OIDCValidationError, match='unsupported ID token signing algorithm none'):
        _verify(_token(None, 'none', signature=b'x'))
    assert idp['fetched'] == []


@pytest.mark.parametrize('alg', ['HS256', 'HS384', 'HS512'])
def test_hmac_signed_with_the_client_secret_is_refused(idp, alg):
    """A shared secret would make the client secret a signing key (RFC 8725 §3.1)."""
    from services.oidc_id_token import OIDCValidationError
    secret = b'client-secret-example'
    idp['keys'] = [{'kty': 'oct', 'kid': 'k1', 'k': _b64(secret)}]
    idp['discovery'] = {'id_token_signing_alg_values_supported': [alg, 'RS256']}
    with pytest.raises(OIDCValidationError, match=f'unsupported ID token signing algorithm {alg}'):
        _verify(_token(secret, alg), oauth2_jwks_uri=None)


def test_an_unprintable_algorithm_is_shown_escaped(idp):
    from services.oidc_id_token import OIDCValidationError
    with pytest.raises(OIDCValidationError) as caught:
        _verify(_token(None, 'RS256\nforged line', signature=b'x'))
    assert '\n' not in str(caught.value)


@pytest.mark.parametrize('header_alg,key_alg', [
    ('ES256', 'RS256'), ('RS256', 'ES256'), ('PS256', 'ES256'),
    ('EdDSA', 'RS256'), ('ES256', 'EdDSA'), ('RS256', 'EdDSA'),
])
def test_a_key_of_another_type_never_verifies(idp, header_alg, key_alg):
    from services.oidc_id_token import OIDCValidationError
    key = _key_for(key_alg)
    idp['keys'] = [_jwk(key)]
    token = _token(_key_for(header_alg), header_alg)
    with pytest.raises(OIDCValidationError, match='key type does not match'):
        _verify(token)


@pytest.mark.parametrize('header_alg,crv', [('ES256', 'P-384'), ('ES384', 'P-521'),
                                            ('ES512', 'P-256')])
def test_a_curve_the_algorithm_does_not_name_is_refused(idp, header_alg, crv):
    """ES256 is ECDSA over P-256 only (RFC 7518 §3.4), even signed by the key's own curve."""
    from services.oidc_id_token import OIDCValidationError
    key = _key_for('ES256', crv)
    idp['keys'] = [_jwk(key)]
    with pytest.raises(OIDCValidationError, match='key type does not match'):
        _verify(_token(key, header_alg))


def test_a_key_alg_other_than_the_header_is_refused(idp):
    from services.oidc_id_token import OIDCValidationError
    key = _rsa_key()
    idp['keys'] = [_jwk(key, alg='RS256')]
    with pytest.raises(OIDCValidationError, match='signing key'):
        _verify(_token(key, 'PS256'))


def test_pss_takes_a_salt_as_long_as_the_hash(idp):
    """RFC 7518 §3.5: "The size of the salt value is the same size as the hash function output"."""
    from services.oidc_id_token import OIDCValidationError
    key = _rsa_key()
    idp['keys'] = [_jwk(key)]
    header = _b64(json.dumps({'alg': 'PS256', 'kid': 'k1'}).encode())
    payload = _b64(json.dumps(_claims()).encode())
    signing_input = f'{header}.{payload}'.encode('ascii')
    unsalted = key.sign(signing_input, padding.PSS(padding.MGF1(hashes.SHA256()), 0),
                        hashes.SHA256())
    with pytest.raises(OIDCValidationError, match='signature is invalid'):
        _verify(f'{header}.{payload}.{_b64(unsalted)}')


def test_an_encryption_key_never_verifies(idp):
    from services.oidc_id_token import OIDCValidationError
    key = _rsa_key()
    idp['keys'] = [_jwk(key, use='enc')]
    with pytest.raises(OIDCValidationError, match='signing key'):
        _verify(_token(key, 'RS256'))


def test_an_algorithm_the_discovery_does_not_list_is_refused(idp):
    from services.oidc_id_token import OIDCValidationError
    key = _rsa_key()
    idp['keys'] = [_jwk(key)]
    idp['discovery'] = {'id_token_signing_alg_values_supported': ['RS256']}
    assert _verify(_token(key, 'RS256'), oauth2_jwks_uri=None)['sub'] == 'user-123'
    with pytest.raises(OIDCValidationError, match='PS256 is not listed'):
        _verify(_token(key, 'PS256'), oauth2_jwks_uri=None)


def test_the_discovery_list_costs_no_extra_request(idp):
    key = _rsa_key()
    idp['keys'] = [_jwk(key)]
    idp['discovery'] = {'id_token_signing_alg_values_supported': ['RS256', 'PS256']}
    _verify(_token(key, 'PS256'), oauth2_jwks_uri=None)
    _verify(_token(key, 'PS256'), oauth2_jwks_uri=None)
    assert idp['fetched'] == [f'{ISSUER}/.well-known/openid-configuration', JWKS_URI]


def test_a_discovery_list_that_is_not_a_list_is_refused(idp):
    from services.oidc_id_token import OIDCValidationError
    key = _rsa_key()
    idp['keys'] = [_jwk(key)]
    idp['discovery'] = {'id_token_signing_alg_values_supported': 'RS256'}
    with pytest.raises(OIDCValidationError, match='id_token_signing_alg_values_supported'):
        _verify(_token(key, 'RS256'), oauth2_jwks_uri=None)


def test_an_rsa_key_under_2048_bits_is_refused(idp):
    """RFC 7518 §3.3: "A key of size 2048 bits or larger MUST be used"."""
    from services.oidc_id_token import OIDCValidationError
    key = _rsa_key(1024)
    idp['keys'] = [_jwk(key)]
    with pytest.raises(OIDCValidationError, match='2048 bits'):
        _verify(_token(key, 'RS256'))


def _prime(bits):
    import secrets
    while True:
        n = secrets.randbits(bits) | (1 << (bits - 1)) | 1
        if all(pow(a, n - 1, n) == 1 for a in (2, 3, 5, 7, 11, 13, 17, 19, 23, 29, 31, 37)):
            return n


def _odd_rsa_key():
    """An RSA key with an odd modulus size, which OpenSSL never generates."""
    while True:
        p, q, e = _prime(1025), _prime(1025), 65537
        phi = (p - 1) * (q - 1)
        if (p * q).bit_length() % 2 == 1 and phi % e:
            d = pow(e, -1, phi)
            return rsa.RSAPrivateNumbers(
                p, q, d, rsa.rsa_crt_dmp1(d, p), rsa.rsa_crt_dmq1(d, q), rsa.rsa_crt_iqmp(p, q),
                rsa.RSAPublicNumbers(e, p * q)).private_key()


@pytest.fixture
def fips(monkeypatch):
    import fips_mode
    approved = set()
    monkeypatch.setattr(fips_mode, 'enabled', lambda: True)
    monkeypatch.setattr(fips_mode, 'module_approves', lambda alg: str(alg).upper() in approved)
    return approved


def test_fips_mode_refuses_eddsa_the_module_does_not_approve(idp, fips):
    from services.oidc_id_token import OIDCValidationError
    key = _key_for('EdDSA')
    idp['keys'] = [_jwk(key)]
    with pytest.raises(OIDCValidationError, match='Ed25519 .*not available in FIPS mode'):
        _verify(_token(key, 'EdDSA'))
    fips.add('ED25519')
    assert _verify(_token(key, 'EdDSA'))['sub'] == 'user-123'


def test_fips_mode_keeps_the_rsa_rule_of_the_product(idp, fips):
    """FIPS 186-5 §5.1 as ``fips_rsa_bits_approved`` reads it: an even modulus of 2048 bits or more."""
    from services.oidc_id_token import OIDCValidationError
    key = _odd_rsa_key()
    assert key.key_size % 2 == 1
    idp['keys'] = [_jwk(key)]
    with pytest.raises(OIDCValidationError, match='FIPS mode'):
        _verify(_token(key, 'RS256'))
    good, ec_key = _rsa_key(), _key_for('ES384')
    idp['keys'] = [_jwk(good, kid='k2'), _jwk(ec_key, kid='k3')]
    assert _verify(_token(good, 'PS256', kid='k2'))['sub'] == 'user-123'
    assert _verify(_token(ec_key, 'ES384', kid='k3'))['sub'] == 'user-123'


@pytest.mark.parametrize('alg', [['RS256'], {'alg': 'RS256'}, 256, None])
def test_an_algorithm_that_is_not_text_is_refused_as_unsupported(idp, alg):
    from services.oidc_id_token import OIDCValidationError
    idp['keys'] = [_jwk(_rsa_key())]
    with pytest.raises(OIDCValidationError, match='unsupported ID token signing algorithm'):
        _verify(_token(None, alg, signature=b'x'))
    assert idp['fetched'] == []


@pytest.mark.parametrize('x', [None, '', '***'])
def test_an_okp_key_without_its_point_is_a_malformed_signing_key(idp, x):
    """Named like an RSA or EC key that lacks a member, so the JWKS is read anew once."""
    from services.oidc_id_token import OIDCValidationError
    key = _key_for('EdDSA')
    jwk = _jwk(key)
    if x is None:
        jwk.pop('x')
    else:
        jwk['x'] = x
    idp['keys'] = [jwk]
    with pytest.raises(OIDCValidationError, match='malformed JWKS signing key'):
        _verify(_token(key, 'EdDSA'))


DISCOVERY_URL = f'{ISSUER}/.well-known/openid-configuration'


def test_an_algorithm_the_idp_adds_is_accepted_after_one_rereading(idp):
    key = _rsa_key()
    idp['keys'] = [_jwk(key)]
    idp['discovery'] = {'id_token_signing_alg_values_supported': ['RS256']}
    _verify(_token(key, 'RS256'), oauth2_jwks_uri=None)
    idp['discovery'] = {'id_token_signing_alg_values_supported': ['RS256', 'PS256']}
    assert _verify(_token(key, 'PS256'), oauth2_jwks_uri=None)['sub'] == 'user-123'
    assert idp['fetched'] == [DISCOVERY_URL, JWKS_URI, DISCOVERY_URL]


def test_a_burst_of_unlisted_tokens_rereads_the_discovery_once(idp, monkeypatch):
    import services.oidc_id_token as oidc
    key = _rsa_key()
    idp['keys'] = [_jwk(key)]
    idp['discovery'] = {'id_token_signing_alg_values_supported': ['RS256']}
    for _attempt in range(5):
        with pytest.raises(oidc.OIDCValidationError, match='PS256 is not listed'):
            _verify(_token(key, 'PS256'), oauth2_jwks_uri=None)
    assert idp['fetched'] == [DISCOVERY_URL, DISCOVERY_URL]
    # Once the window has passed, the next refusal reads it again
    monkeypatch.setattr(oidc, '_REFRESH_INTERVAL_SECONDS', 0)
    with pytest.raises(oidc.OIDCValidationError, match='PS256 is not listed'):
        _verify(_token(key, 'PS256'), oauth2_jwks_uri=None)
    assert idp['fetched'] == [DISCOVERY_URL] * 3


@pytest.mark.parametrize('alg', ['none', 'HS256', 'RS1'])
def test_an_algorithm_outside_the_product_list_stays_refused_whatever_the_idp_lists(idp, alg):
    from services.oidc_id_token import OIDCValidationError
    idp['keys'] = [_jwk(_rsa_key())]
    idp['discovery'] = {'id_token_signing_alg_values_supported': ['RS256', alg]}
    for _attempt in range(3):
        with pytest.raises(OIDCValidationError, match=f'unsupported ID token signing algorithm {alg}'):
            _verify(_token(None, alg, signature=b'x'), oauth2_jwks_uri=None)
    assert idp['fetched'] == []


def test_a_burst_of_forged_signatures_refreshes_the_jwks_once(idp):
    from services.oidc_id_token import OIDCValidationError
    key = _rsa_key()
    idp['keys'] = [_jwk(key)]
    header, _payload, sig = _token(key, 'RS256').split('.')
    forged = f"{header}.{_b64(json.dumps(_claims(sub='admin')).encode())}.{sig}"
    for _attempt in range(5):
        with pytest.raises(OIDCValidationError, match='signature is invalid'):
            _verify(forged)
    assert idp['fetched'] == [JWKS_URI, JWKS_URI]
