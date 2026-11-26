"""The account menu's session facts and the manual lock.

``GET /api/v2/auth/verify`` tells a reloaded page how the session was opened (each
sign-in path keeps its method in the session), the provider's display name, the
account's second factors and when the session ends. ``POST /api/v2/auth/lock`` locks
the session as the inactivity lock does: session and CSRF token required, audited, and
the cookie refused as locked afterwards on every node of a shared store.
"""
import json
import uuid
from datetime import datetime, timedelta

import pyotp
import pytest

from models import AuditLog, SSOProvider, SystemConfig, User, UserSSOIdentity, db
from tests.test_factor_change_sessions import (  # noqa: F401 (fixtures)
    _drop_session_table_from_metadata, nodes)
from tests.test_failed_login_count import _signs_in_by_certificate, _signs_in_by_passkey
from utils.datetime_utils import utc_now

PASSWORD = 'L0ck-And-Inf0-Pass!'
AUTH_REQUIRED = 'urn:ucm:problem:authentication-required'
SESSION_LOCKED = 'urn:ucm:problem:session-locked'


def _post(c, url, body=None, headers=None):
    return c.post(url, data=json.dumps(body or {}), content_type='application/json',
                  headers=headers or {})


def _verify(c):
    r = c.get('/api/v2/auth/verify')
    assert r.status_code == 200, r.data
    return r.get_json()['data']


def _signed_in(c):
    return c.get('/api/v2/account/profile').status_code == 200


@pytest.fixture
def make_user(app):
    created = []

    def _make(application=None, totp=False, full_name='Lock Probe'):
        with (application or app).app_context():
            user = User(username=f'lock-{uuid.uuid4().hex[:8]}', full_name=full_name,
                        email=f'{uuid.uuid4().hex[:8]}@example.test', role='operator')
            user.set_password(PASSWORD)
            if totp:
                user.totp_secret = pyotp.random_base32()
                user.totp_confirmed = True
            db.session.add(user)
            db.session.commit()
            created.append(((application or app), user.id))
            info = {'id': user.id, 'username': user.username, 'secret': user.totp_secret}
            db.session.remove()
            return info

    yield _make

    from models.second_factor_failure import SecondFactorFailure
    for application, uid in created:
        with application.app_context():
            SecondFactorFailure.query.filter_by(target=str(uid)).delete()
            row = db.session.get(User, uid)
            if row:
                db.session.delete(row)
            db.session.commit()
            db.session.remove()


def _password_session(application, user):
    c = application.test_client()
    r = _post(c, '/api/v2/auth/login/password', {'username': user['username'], 'password': PASSWORD})
    assert r.status_code == 200, r.data
    if (r.get_json().get('data') or {}).get('requires_2fa'):
        r = _post(c, '/api/v2/auth/login/2fa', {'code': pyotp.TOTP(user['secret']).now()})
        assert r.status_code == 200, r.data
    return c


@pytest.fixture
def ldap_provider(app):
    with app.app_context():
        provider = SSOProvider(
            name=f'lock-ldap-{uuid.uuid4().hex[:6]}', display_name='Corporate Directory',
            provider_type='ldap', enabled=True, ldap_server='ldap.example.test', ldap_port=389,
            ldap_base_dn='dc=example,dc=test', ldap_user_filter='(uid={username})',
            ldap_username_attr='uid', ldap_email_attr='mail', ldap_fullname_attr='cn')
        db.session.add(provider)
        db.session.commit()
        provider_id = provider.id
    yield provider_id
    with app.app_context():
        from models.sso import SSOSession
        from models.user import UserSession
        ids = [i.user_id for i in UserSSOIdentity.query.filter_by(provider_id=provider_id)]
        SSOSession.query.filter_by(provider_id=provider_id).delete()
        UserSSOIdentity.query.filter_by(provider_id=provider_id).delete()
        UserSession.query.filter(UserSession.user_id.in_(ids)).delete(synchronize_session=False)
        User.query.filter(User.id.in_(ids)).delete(synchronize_session=False)
        db.session.delete(db.session.get(SSOProvider, provider_id))
        db.session.commit()


def _ldap_directory(monkeypatch, name):
    import api.v2.sso.ldap_routes as ldap_routes
    monkeypatch.setattr(ldap_routes, '_ldap_authenticate_user', lambda p, u, pw, before_bind=None: ({
        'dn': f'uid={name}', 'uid': name, 'username': name, 'email': f'{name}@example.test',
        'fullname': 'Directory Person', 'groups': []}, None))


# --- Each sign-in path keeps its method; /verify says it after a reload -------------

def test_a_password_sign_in_is_reported_as_password(app, make_user):
    user = make_user()
    data = _verify(_password_session(app, user))
    assert data['auth_method'] == 'password'
    assert data['auth_provider'] is None


def test_a_password_and_totp_sign_in_is_reported_as_password(app, make_user):
    user = make_user(totp=True)
    data = _verify(_password_session(app, user))
    assert data['auth_method'] == 'password'
    assert data['mfa'] == {'enabled': True, 'methods': ['totp']}


def test_a_client_certificate_sign_in_is_reported_as_mtls(app, make_user, monkeypatch):
    user = make_user()
    c = app.test_client()
    assert _signs_in_by_certificate(monkeypatch, user['username'])(c).status_code == 200
    assert _verify(c)['auth_method'] == 'mtls'


def test_a_certificate_auto_login_is_reported_as_certificate(app, make_user, monkeypatch):
    import middleware.mtls_middleware as mtls_middleware
    from services.mtls_auth_service import MTLSAuthService
    from tests.test_session_lifecycle import _cert_login
    user = make_user()
    monkeypatch.setattr(MTLSAuthService, 'is_mtls_enabled', staticmethod(lambda: True))
    monkeypatch.setattr(mtls_middleware, '_extract_certificate', lambda: {'serial': '0a'})
    _cert_login(monkeypatch, app, user['id'])
    data = _verify(app.test_client())
    assert data['authenticated'] is True
    assert data['auth_method'] == 'certificate'


def test_a_security_key_sign_in_is_reported_as_webauthn(app, make_user, monkeypatch):
    user = make_user()
    c = app.test_client()
    assert _signs_in_by_passkey(monkeypatch, user['username'])(c).status_code == 200
    assert _verify(c)['auth_method'] == 'webauthn'


def test_an_ldap_sign_in_is_reported_with_the_directory_name(app, ldap_provider, monkeypatch):
    name = f'lockldap{uuid.uuid4().hex[:6]}'
    _ldap_directory(monkeypatch, name)
    c = app.test_client()
    r = _post(c, '/api/v2/sso/ldap/login', {'username': name, 'password': 'pw',
                                             'provider_id': ldap_provider})
    assert r.status_code == 200, r.data
    data = _verify(c)
    assert (data['auth_method'], data['auth_provider']) == ('ldap', 'Corporate Directory')


def test_an_ldap_sign_in_with_totp_keeps_the_directory_name(app, ldap_provider, monkeypatch):
    name = f'lockldap{uuid.uuid4().hex[:6]}'
    _ldap_directory(monkeypatch, name)
    assert _post(app.test_client(), '/api/v2/sso/ldap/login', {
        'username': name, 'password': 'pw', 'provider_id': ldap_provider}).status_code == 200
    with app.app_context():
        row = User.query.filter_by(username=name).one()
        row.totp_secret = pyotp.random_base32()
        row.totp_confirmed = True
        secret = row.totp_secret
        db.session.commit()
    c = app.test_client()
    r = _post(c, '/api/v2/sso/ldap/login', {'username': name, 'password': 'pw',
                                             'provider_id': ldap_provider})
    assert r.get_json()['data']['requires_2fa'] is True
    assert _post(c, '/api/v2/auth/login/2fa', {'code': pyotp.TOTP(secret).now()}).status_code == 200
    data = _verify(c)
    assert (data['auth_method'], data['auth_provider']) == ('ldap', 'Corporate Directory')


@pytest.mark.parametrize('provider_type', ['oauth2', 'saml'])
def test_an_sso_sign_in_keeps_the_method_and_the_provider_name(app, provider_type):
    """OIDC and SAML share the session's last steps; the display name, never the id, is kept."""
    from flask import session
    from api.v2.sso.login_routes import SignInIdentity, _open_sso_session
    name = f'locksso{uuid.uuid4().hex[:6]}'
    with app.app_context():
        provider = SSOProvider(name=f'lock-{provider_type}-{uuid.uuid4().hex[:6]}',
                               display_name='Company SSO', provider_type=provider_type,
                               enabled=True, auto_create_users=True, default_role='viewer')
        db.session.add(provider)
        db.session.commit()
        provider_id = provider.id
    try:
        with app.test_request_context('/api/v2/sso/callback/' + provider_type):
            from auth.session_epoch import note_request_epoch
            note_request_epoch()
            provider = db.session.get(SSOProvider, provider_id)
            identity = SignInIdentity(name, f'{name}@example.test', 'Sso Person', {'groups': []},
                                      None, session_id=f'sid-{name}')
            r = _open_sso_session(provider, identity, '/login/sso-complete', lambda code: f'/login?error={code}')
            assert r.status_code == 302 and 'error' not in r.headers['Location'], r.headers
            assert (session['auth_method'], session['auth_provider']) == ('sso', 'Company SSO')
    finally:
        with app.app_context():
            from models.sso import SSOSession
            ids = [i.user_id for i in UserSSOIdentity.query.filter_by(provider_id=provider_id)]
            SSOSession.query.filter_by(provider_id=provider_id).delete()
            UserSSOIdentity.query.filter_by(provider_id=provider_id).delete()
            User.query.filter(User.id.in_(ids)).delete(synchronize_session=False)
            db.session.delete(db.session.get(SSOProvider, provider_id))
            db.session.commit()


def test_verify_reads_an_sso_session_back(app, make_user):
    from tests.session_support import pose_signed_in
    user = make_user()
    c = app.test_client()
    with app.app_context(), c.session_transaction() as sess:
        pose_signed_in(sess, db.session.get(User, user['id']))
        sess.update(auth_method='sso', auth_provider='Company SSO')
    data = _verify(c)
    assert (data['auth_method'], data['auth_provider']) == ('sso', 'Company SSO')


# --- What /verify reports of the account and the session ----------------------------

def test_verify_reports_the_full_name_mfa_and_the_session_deadlines(app, make_user):
    user = make_user(full_name='Ada Lovelace')
    with app.app_context():
        for key, value in (('session_timeout', '900'), ('session_max_lifetime', '7200')):
            row = SystemConfig.query.filter_by(key=key).first()
            if row is None:
                db.session.add(SystemConfig(key=key, value=value))
            else:
                row.value = value
        db.session.commit()
    try:
        before = utc_now()
        c = _password_session(app, user)
        after = utc_now()
        data = _verify(c)
    finally:
        with app.app_context():
            SystemConfig.query.filter(SystemConfig.key.in_(
                ['session_timeout', 'session_max_lifetime'])).delete(synchronize_session=False)
            db.session.commit()
    assert data['user']['full_name'] == 'Ada Lovelace'
    assert data['mfa'] == {'enabled': False, 'methods': []}
    assert data['session']['idle_timeout_s'] == 900
    expires = data['session']['expires_at']
    assert expires.endswith('Z')
    expires = datetime.fromisoformat(expires[:-1])
    assert before + timedelta(seconds=7200) - timedelta(seconds=1) <= expires
    assert expires <= after + timedelta(seconds=7200) + timedelta(seconds=1)


def test_verify_tells_no_provider_internal_and_no_secret(app, ldap_provider, monkeypatch):
    name = f'lockldap{uuid.uuid4().hex[:6]}'
    _ldap_directory(monkeypatch, name)
    c = app.test_client()
    assert _post(c, '/api/v2/sso/ldap/login', {'username': name, 'password': 'pw',
                                                'provider_id': ldap_provider}).status_code == 200
    data = _verify(c)
    flat = json.dumps(data)
    for leaked in ('provider_id', 'sso_provider', 'totp_secret', 'cert_serial', 'ldap.example.test'):
        assert leaked not in flat, leaked


def test_an_api_key_verify_keeps_its_own_method(app, auth_client):
    from tests.conftest import assert_success
    key = assert_success(auth_client.post('/api/v2/account/apikeys', data=json.dumps(
        {'password': 'changeme123', 'name': 'verify-method', 'permissions': ['read:certificates']}),
        content_type='application/json'), 201)
    try:
        data = app.test_client().get('/api/v2/auth/verify',
                                     headers={'X-API-Key': key['key']}).get_json()['data']
        assert data['auth_method'] == 'api_key'
    finally:
        auth_client.delete(f"/api/v2/account/apikeys/{key['id']}")


# --- POST /api/v2/auth/lock ----------------------------------------------------------

@pytest.fixture
def csrf_on(monkeypatch):
    from security.csrf import CSRFProtection
    monkeypatch.setattr(CSRFProtection, 'is_enabled', classmethod(lambda cls: True))


def _csrf(c):
    return {'X-CSRF-Token': _verify(c)['csrf_token']}


def test_locking_needs_a_session(app):
    r = _post(app.test_client(), '/api/v2/auth/lock')
    assert r.status_code == 401


def test_locking_refuses_an_api_key(app, auth_client):
    from tests.conftest import assert_success
    key = assert_success(auth_client.post('/api/v2/account/apikeys', data=json.dumps(
        {'password': 'changeme123', 'name': 'lock', 'permissions': ['*']}), content_type='application/json'), 201)
    try:
        r = _post(app.test_client(), '/api/v2/auth/lock', headers={'X-API-Key': key['key']})
        assert r.status_code == 403
    finally:
        auth_client.delete(f"/api/v2/account/apikeys/{key['id']}")


def test_locking_needs_the_csrf_token(app, make_user, csrf_on):
    user = make_user()
    c = _password_session(app, user)
    assert _post(c, '/api/v2/auth/lock').status_code == 403
    assert _signed_in(c)
    assert _post(c, '/api/v2/auth/lock', headers={'X-CSRF-Token': 'forged'}).status_code == 403
    assert _signed_in(c)
    assert _post(c, '/api/v2/auth/lock', headers=_csrf(c)).status_code == 200
    assert not _signed_in(c)


@pytest.mark.parametrize('reason, said', [('manual', 'manual'), ('idle', 'inactivity'),
                                          (None, 'manual'), ('<script>', 'manual')])
def test_locking_is_audited_with_its_reason(app, make_user, reason, said):
    user = make_user()
    c = _password_session(app, user)
    r = _post(c, '/api/v2/auth/lock', {'reason': reason} if reason else {})
    assert r.status_code == 200, r.data
    with app.app_context():
        row = (AuditLog.query.filter_by(action='session_locked', username=user['username'])
               .order_by(AuditLog.id.desc()).first())
        assert row is not None
        assert row.success
        assert f'({said})' in row.details
        assert '<script>' not in row.details


def test_a_locked_session_is_refused_with_its_own_problem_type(app, make_user):
    """The cookie held before the lock opens nothing: a 401 that says locked, not signed out."""
    user = make_user()
    c = _password_session(app, user)
    held = c.get_cookie('session').value
    assert _post(c, '/api/v2/auth/lock').status_code == 200
    replay = app.test_client()
    replay.set_cookie('session', held)
    for client in (c, replay):
        r = client.get('/api/v2/account/profile')
        assert r.status_code == 401
        assert r.get_json()['type'] == SESSION_LOCKED
        assert _verify(client)['authenticated'] is False


@pytest.mark.parametrize('held', ['password-change', '2fa-enrolment'])
def test_the_lock_reaches_a_session_held_to_a_first_step(app, make_user, held):
    """A forced password change or 2FA enrolment leaves sign-out open; the lock too."""
    from auth.twofa_enforcement import ENROLL_SESSION_KEY
    user = make_user()
    if held == 'password-change':
        with app.app_context():
            db.session.get(User, user['id']).force_password_change = True
            db.session.commit()
    c = _password_session(app, user)
    if held == '2fa-enrolment':
        with c.session_transaction() as sess:
            sess[ENROLL_SESSION_KEY] = True
    assert c.get('/api/v2/account/profile').status_code == 403
    assert _post(c, '/api/v2/auth/lock').status_code == 200
    assert c.get('/api/v2/account/profile').status_code == 401


def test_a_session_locked_on_one_node_is_refused_on_the_other(nodes, make_user):
    """HA: the shared store holds the lock on every node."""
    first, second = nodes
    user = make_user(first)
    c = _password_session(first, user)
    held = c.get_cookie('session').value
    other = second.test_client()
    other.set_cookie('session', held)
    assert _signed_in(other)
    assert _post(c, '/api/v2/auth/lock').status_code == 200
    r = other.get('/api/v2/account/profile')
    assert r.status_code == 401
    assert r.get_json()['type'] == SESSION_LOCKED
