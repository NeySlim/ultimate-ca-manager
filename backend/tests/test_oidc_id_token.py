"""OIDC ID token verification regression tests."""

import base64
import json
import time
from types import SimpleNamespace

import pytest
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec, padding, rsa
from cryptography.hazmat.primitives.asymmetric.utils import decode_dss_signature


def _b64(data):
    return base64.urlsafe_b64encode(data).rstrip(b'=').decode('ascii')


def _int_b64(value):
    return _b64(value.to_bytes((value.bit_length() + 7) // 8, 'big'))


def _rsa_jwk(key, kid='rsa-key'):
    numbers = key.public_key().public_numbers()
    return {
        'kty': 'RSA', 'kid': kid, 'use': 'sig', 'alg': 'RS256',
        'n': _int_b64(numbers.n), 'e': _int_b64(numbers.e),
    }


def _ec_jwk(key, kid='ec-key'):
    numbers = key.public_key().public_numbers()
    return {
        'kty': 'EC', 'kid': kid, 'use': 'sig', 'alg': 'ES256', 'crv': 'P-256',
        'x': _int_b64(numbers.x), 'y': _int_b64(numbers.y),
    }


def _token(key, claims, alg='RS256', kid=None):
    kid = kid or ('rsa-key' if alg == 'RS256' else 'ec-key')
    header = _b64(json.dumps({'alg': alg, 'kid': kid}, separators=(',', ':')).encode())
    payload = _b64(json.dumps(claims, separators=(',', ':')).encode())
    signing_input = f'{header}.{payload}'.encode('ascii')
    if alg == 'RS256':
        signature = key.sign(signing_input, padding.PKCS1v15(), hashes.SHA256())
    else:
        der = key.sign(signing_input, ec.ECDSA(hashes.SHA256()))
        r, s = decode_dss_signature(der)
        signature = r.to_bytes(32, 'big') + s.to_bytes(32, 'big')
    return f'{header}.{payload}.{_b64(signature)}'


def _provider(**overrides):
    values = {
        'id': 7,
        'name': 'OIDC',
        'oauth2_issuer': 'https://idp.example/realms/ucm',
        'oauth2_client_id': 'ucm-client',
        'oauth2_jwks_uri': 'https://idp.example/realms/ucm/jwks',
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def _claims(**overrides):
    now = int(time.time())
    values = {
        'iss': 'https://idp.example/realms/ucm',
        'aud': 'ucm-client',
        'sub': 'user-123',
        'exp': now + 300,
        'iat': now,
        'nbf': now - 5,
        'nonce': 'session-nonce',
    }
    values.update(overrides)
    return values


class _Response:
    def __init__(self, data, status_code=200):
        self._data = data
        self.status_code = status_code
        self.ok = 200 <= status_code < 300
        self.content = json.dumps(data).encode()

    def json(self):
        return self._data


@pytest.fixture(autouse=True)
def clear_oidc_cache():
    from services.oidc_id_token import clear_oidc_cache
    clear_oidc_cache()
    yield
    clear_oidc_cache()


def test_rs256_id_token_is_verified(monkeypatch):
    from services.oidc_id_token import verify_id_token
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    monkeypatch.setattr(
        'services.oidc_id_token.safe_request_get',
        lambda *_args, **_kwargs: _Response({'keys': [_rsa_jwk(key)]}),
    )

    claims = verify_id_token(
        _token(key, _claims()), _provider(), 'session-nonce', verify=True,
    )

    assert claims['sub'] == 'user-123'


def test_es256_id_token_is_verified(monkeypatch):
    from services.oidc_id_token import verify_id_token
    key = ec.generate_private_key(ec.SECP256R1())
    monkeypatch.setattr(
        'services.oidc_id_token.safe_request_get',
        lambda *_args, **_kwargs: _Response({'keys': [_ec_jwk(key)]}),
    )

    claims = verify_id_token(
        _token(key, _claims(), alg='ES256'), _provider(), 'session-nonce', verify=True,
    )

    assert claims['sub'] == 'user-123'


def test_discovery_and_jwks_are_cached(monkeypatch):
    from services.oidc_id_token import verify_id_token
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    calls = []

    def fetch(url, **_kwargs):
        calls.append(url)
        if url.endswith('/.well-known/openid-configuration'):
            return _Response({
                'issuer': 'https://idp.example/realms/ucm',
                'jwks_uri': 'https://idp.example/realms/ucm/jwks',
            })
        return _Response({'keys': [_rsa_jwk(key)]})

    monkeypatch.setattr('services.oidc_id_token.safe_request_get', fetch)
    provider = _provider(oauth2_jwks_uri=None)
    token = _token(key, _claims())

    verify_id_token(token, provider, 'session-nonce', verify=True)
    verify_id_token(token, provider, 'session-nonce', verify=True)

    assert calls == [
        'https://idp.example/realms/ucm/.well-known/openid-configuration',
        'https://idp.example/realms/ucm/jwks',
    ]


def test_bad_signature_forces_one_jwks_refresh_then_rejects(monkeypatch):
    from services.oidc_id_token import OIDCValidationError, verify_id_token
    trusted = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    attacker = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    calls = []

    def fetch(*_args, **_kwargs):
        calls.append(1)
        return _Response({'keys': [_rsa_jwk(trusted)]})

    monkeypatch.setattr('services.oidc_id_token.safe_request_get', fetch)

    with pytest.raises(OIDCValidationError, match='signature'):
        verify_id_token(
            _token(attacker, _claims()), _provider(), 'session-nonce', verify=True,
        )

    assert len(calls) == 2


@pytest.mark.parametrize('claim_updates', [
    {'iss': 'https://attacker.example'},
    {'aud': 'other-client'},
    {'aud': ['ucm-client', 'other-client']},
    {'aud': ['ucm-client', 'other-client'], 'azp': 'other-client'},
    {'exp': int(time.time()) - 120},
    {'iat': int(time.time()) + 3600},
    {'nbf': int(time.time()) + 3600},
    {'exp': float('nan')},
    {'nonce': 'wrong-nonce'},
])
def test_invalid_claims_are_rejected(monkeypatch, claim_updates):
    from services.oidc_id_token import OIDCValidationError, verify_id_token
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    monkeypatch.setattr(
        'services.oidc_id_token.safe_request_get',
        lambda *_args, **_kwargs: _Response({'keys': [_rsa_jwk(key)]}),
    )

    with pytest.raises(OIDCValidationError):
        verify_id_token(
            _token(key, _claims(**claim_updates)),
            _provider(),
            'session-nonce',
            verify=True,
        )


def test_jwks_cloud_metadata_url_is_rejected_before_fetch(monkeypatch):
    from services.oidc_id_token import OIDCValidationError, verify_id_token
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    fetched = []
    monkeypatch.setattr(
        'services.oidc_id_token.safe_request_get',
        lambda *_args, **_kwargs: fetched.append(True),
    )

    with pytest.raises(OIDCValidationError, match='JWKS'):
        verify_id_token(
            _token(key, _claims()),
            _provider(oauth2_jwks_uri='http://169.254.169.254/latest'),
            'session-nonce',
            verify=True,
        )

    assert fetched == []


def test_verification_requires_configured_issuer():
    from services.oidc_id_token import OIDCValidationError, verify_id_token
    with pytest.raises(OIDCValidationError, match='issuer'):
        verify_id_token('not-a-token', _provider(oauth2_issuer=None), 'nonce', verify=True)


def test_oidc_provider_configuration_defaults_to_verification(app):
    from models.sso import SSOProvider

    with app.app_context():
        provider = SSOProvider(
            name='OIDC model',
            provider_type='oauth2',
            oauth2_issuer='https://idp.example/realms/ucm',
            oauth2_jwks_uri='https://idp.example/realms/ucm/jwks',
        )
        data = provider.to_dict()

    assert data['oauth2_issuer'] == 'https://idp.example/realms/ucm'
    assert data['oauth2_jwks_uri'].endswith('/jwks')
    assert data['id_token_verify'] is True


def test_provider_api_persists_explicit_verification_opt_out(app, auth_client):
    from models import db
    from models.sso import SSOProvider, SSOSession

    payload = {
        'name': 'OIDC compatibility',
        'provider_type': 'oauth2',
        'enabled': False,
        'oauth2_client_id': 'legacy-client',
        'oauth2_auth_url': 'https://idp.example/authorize',
        'oauth2_token_url': 'https://idp.example/token',
        'oauth2_userinfo_url': 'https://idp.example/userinfo',
        'oauth2_issuer': 'https://idp.example',
        'oauth2_jwks_uri': 'https://idp.example/jwks',
        'id_token_verify': False,
    }

    try:
        response = auth_client.post('/api/v2/sso/providers', json=payload)
        assert response.status_code == 200
        data = response.get_json()['data']
        assert data['oauth2_issuer'] == payload['oauth2_issuer']
        assert data['oauth2_jwks_uri'] == payload['oauth2_jwks_uri']
        assert data['id_token_verify'] is False
    finally:
        with app.app_context():
            provider = SSOProvider.query.filter_by(name=payload['name']).first()
            if provider:
                SSOSession.query.filter_by(provider_id=provider.id).delete()
                db.session.delete(provider)
                db.session.commit()


def test_callback_rejects_invalid_id_token_and_audits(app, monkeypatch):
    from api.v2.sso import login_routes
    from models import db
    from models.sso import SSOProvider, SSOSession
    from services.oidc_id_token import OIDCValidationError

    with app.app_context():
        existing_states = [
            (item.id, item.enabled)
            for item in SSOProvider.query.filter_by(provider_type='oauth2').all()
        ]
        for provider_id, _enabled in existing_states:
            db.session.get(SSOProvider, provider_id).enabled = False
        provider = SSOProvider(
            name='OIDC callback',
            provider_type='oauth2',
            enabled=True,
            oauth2_client_id='ucm-client',
            oauth2_client_secret='secret',
            oauth2_auth_url='https://idp.example/authorize',
            oauth2_token_url='https://idp.example/token',
            oauth2_userinfo_url='https://idp.example/userinfo',
            oauth2_issuer='https://idp.example',
            id_token_verify=True,
        )
        db.session.add(provider)
        db.session.commit()

    class TokenResponse:
        ok = True
        text = ''

        @staticmethod
        def json():
            return {'access_token': 'access', 'id_token': 'forged.token.value'}

    audit_calls = []
    monkeypatch.setattr(login_routes, 'safe_request_post', lambda *_a, **_kw: TokenResponse())
    monkeypatch.setattr(
        login_routes,
        'verify_id_token',
        lambda *_a, **_kw: (_ for _ in ()).throw(OIDCValidationError('bad signature')),
    )
    monkeypatch.setattr(
        login_routes.AuditService,
        'log_action',
        lambda **kwargs: audit_calls.append(kwargs),
    )

    client = app.test_client()
    with client.session_transaction() as sso_session:
        sso_session['sso_state'] = 'state'
        sso_session['sso_pkce_verifier'] = 'verifier'
        sso_session['sso_nonce'] = 'nonce'

    try:
        response = client.get('/api/v2/sso/callback/oauth2?state=state&code=code')

        assert response.status_code == 302
        assert response.headers['Location'].endswith('/login?error=invalid_credentials')
        assert any(call.get('action') == 'login_failure' for call in audit_calls)
    finally:
        with app.app_context():
            provider = SSOProvider.query.filter_by(name='OIDC callback').first()
            if provider:
                SSOSession.query.filter_by(provider_id=provider.id).delete()
                db.session.delete(provider)
            for provider_id, enabled in existing_states:
                existing = db.session.get(SSOProvider, provider_id)
                if existing:
                    existing.enabled = enabled
            db.session.commit()
