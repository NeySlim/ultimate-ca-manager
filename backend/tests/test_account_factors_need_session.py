"""Routes that change how an account signs in refuse API keys.

A `read:certificates` key reached them through a bare `@require_auth()`: it could
re-key TOTP, change the email a password reset goes to, or enrol an mTLS
certificate or a passkey, and so take over its owner's account.
"""
import json

import pytest

from tests.conftest import assert_success

FACTOR_ROUTES = [
    ('post', '/api/v2/account/password', {'current_password': 'x', 'new_password': 'Xx1!xxxxxxxxxxx'}),
    ('patch', '/api/v2/account/profile', {'email': 'attacker@example.com'}),
    ('post', '/api/v2/account/2fa/enable', {}),
    ('post', '/api/v2/account/2fa/confirm', {'code': '000000'}),
    ('post', '/api/v2/account/2fa/disable', {'code': '000000'}),
    ('put', '/api/v2/account/2fa/webauthn', {'enabled': False}),
    ('get', '/api/v2/account/2fa/recovery-codes', None),
    ('post', '/api/v2/account/2fa/recovery-codes/regenerate', {'code': '000000'}),
    ('delete', '/api/v2/account/sessions/999999', None),
    ('post', '/api/v2/account/sessions/revoke-all', {}),
    ('post', '/api/v2/webauthn/register/options', {}),
    ('post', '/api/v2/webauthn/register/verify', {}),
    ('delete', '/api/v2/webauthn/credentials/999999', None),
    ('post', '/api/v2/webauthn/credentials/999999/toggle', {}),
    ('post', '/api/v2/mtls/certificates', {}),
    ('post', '/api/v2/mtls/enroll', {}),
    ('post', '/api/v2/mtls/enroll-import', {}),
    ('post', '/api/v2/mtls/assign', {}),
    ('delete', '/api/v2/mtls/certificates/999999', None),
    ('get', '/api/v2/mtls/certificates/999999/download', None),
]


@pytest.fixture(scope='module')
def wildcard_key(auth_client):
    r = auth_client.post('/api/v2/account/apikeys',
                         data=json.dumps({'name': 'factors', 'permissions': ['*']}),
                         content_type='application/json')
    key = assert_success(r, 201)
    yield key['key']
    auth_client.delete(f"/api/v2/account/apikeys/{key['id']}")


@pytest.mark.parametrize('method, path, body', FACTOR_ROUTES)
def test_api_key_is_refused(app, wildcard_key, method, path, body):
    """Even a `*` key: managing sign-in factors is for the account holder, in a session."""
    kwargs = {'headers': {'X-API-Key': wildcard_key}}
    if body is not None:
        kwargs.update(data=json.dumps(body), content_type='application/json')
    r = getattr(app.test_client(), method)(path, **kwargs)
    assert r.status_code == 403, (path, r.status_code, r.data)


def test_session_still_reaches_the_password_route(auth_client):
    r = auth_client.post('/api/v2/account/password',
                         data=json.dumps({'current_password': 'wrong', 'new_password': 'Xx1!xxxxxxxxxxx'}),
                         content_type='application/json')
    assert r.status_code != 403, r.data


def test_api_key_still_reads_the_profile(app, wildcard_key):
    r = app.test_client().get('/api/v2/account/profile', headers={'X-API-Key': wildcard_key})
    assert r.status_code == 200, r.data


def test_enable_does_not_replace_a_confirmed_secret(app, auth_client):
    """A stolen session must not re-key TOTP: disabling first asks for a code."""
    from models import db, User
    auth_client.post('/api/v2/users', data=json.dumps({
        'username': 'totp_rekey', 'password': 'TotpRekey123!xx', 'email': 'totp_rekey@test.local',
        'role': 'viewer'}), content_type='application/json')
    client = app.test_client()
    r = client.post('/api/v2/auth/login', content_type='application/json',
                    data=json.dumps({'username': 'totp_rekey', 'password': 'TotpRekey123!xx'}))
    assert r.status_code == 200, r.data
    with app.app_context():
        user = User.query.filter_by(username='totp_rekey').first()
        user.totp_secret, user.totp_confirmed = 'JBSWY3DPEHPK3PXP', True
        db.session.commit()
    csrf = json.loads(r.data)['data'].get('csrf_token')
    r = client.post('/api/v2/account/2fa/enable', headers={'X-CSRF-Token': csrf} if csrf else {})
    assert r.status_code == 409, r.data
    with app.app_context():
        assert User.query.filter_by(username='totp_rekey').first().totp_secret == 'JBSWY3DPEHPK3PXP'


def _admin_id(auth_client):
    return json.loads(auth_client.get('/api/v2/account/profile').data)['data']['id']


SELF_ADMIN_ROUTES = [
    ('put', '/api/v2/users/{id}', {'email': 'attacker@example.com'}),
    ('post', '/api/v2/users/{id}/reset-password', {}),
    ('post', '/api/v2/users/{id}/reset-2fa', {}),
    ('post', '/api/v2/users/{id}/link-sso', {'provider_id': 1, 'external_id': 'attacker'}),
    ('post', '/api/v2/users/{id}/unlink-sso', {}),
    ('delete', '/api/v2/users/{id}/webauthn/999999', None),
    ('patch', '/api/v2/users/{id}/webauthn/999999', {'enabled': False}),
]


@pytest.mark.parametrize('method, path, body', SELF_ADMIN_ROUTES)
def test_api_key_cannot_reach_its_owner_through_the_admin_routes(app, auth_client, wildcard_key, method, path, body):
    """The admin routes on one's own id would undo the session-only rule."""
    kwargs = {'headers': {'X-API-Key': wildcard_key}}
    if body is not None:
        kwargs.update(data=json.dumps(body), content_type='application/json')
    r = getattr(app.test_client(), method)(path.format(id=_admin_id(auth_client)), **kwargs)
    assert r.status_code == 403, (path, r.status_code, r.data)


def test_api_key_still_administers_other_users(app, auth_client, wildcard_key):
    r = auth_client.post('/api/v2/users', data=json.dumps({
        'username': 'key_admin_target', 'password': 'KeyTarget123!xx', 'email': 'kt@test.local',
        'role': 'viewer'}), content_type='application/json')
    target = json.loads(r.data)['data']['id'] if r.status_code in (200, 201) else None
    if target is None:
        from models import User
        with app.app_context():
            target = User.query.filter_by(username='key_admin_target').first().id
    r = app.test_client().put(f'/api/v2/users/{target}', headers={'X-API-Key': wildcard_key},
                              data=json.dumps({'email': 'kt2@test.local'}), content_type='application/json')
    assert r.status_code == 200, r.data
