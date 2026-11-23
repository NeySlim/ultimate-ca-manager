"""A locked session stays locked until its own account unlocks it.

``POST /api/v2/auth/lock`` keeps the session and marks it locked, in the session data, so a
shared store holds the lock on every node. While locked: every route that needs a session
answers 401 ``urn:ucm:problem:session-locked``; a client certificate, an SSO return or any
sign-in door never reopens or replaces it. ``/api/v2/auth/unlock/*`` lifts it with a factor of
the same account (password, then its second factor as at sign-in; client certificate;
passkey), each attempt audited and counted as the sign-in counts it.
"""
import json
import threading
import time
import uuid
from contextlib import contextmanager
from types import SimpleNamespace

import pyotp
import pytest

from models import AuditLog, User, db
from utils.datetime_utils import utc_now
from tests.test_factor_change_sessions import (  # noqa: F401 (fixtures)
    _drop_session_table_from_metadata, nodes)
from tests.test_session_lock_and_info import (  # noqa: F401 (fixture)
    PASSWORD, _password_session, _post, _verify, make_user)

LOCKED = 'urn:ucm:problem:session-locked'
AUTH_REQUIRED = 'urn:ucm:problem:authentication-required'
PEER = {'peercert': {'subject': ()}}


def _lock(c, reason='manual'):
    r = _post(c, '/api/v2/auth/lock', {'reason': reason})
    assert r.status_code == 200, r.data
    return r


def _refused_as_locked(r):
    assert r.status_code == 401, r.data
    body = r.get_json()
    assert body['type'] == LOCKED, body
    return body


def _profile(c, **kwargs):
    return c.get('/api/v2/account/profile', **kwargs)


def _next_code(user):
    return pyotp.TOTP(user['secret']).at(time.time() + 30)


def _audits(application, action, username):
    with application.app_context():
        return [(row.success, row.details) for row in AuditLog.query.filter_by(
            action=action, username=username).order_by(AuditLog.id)]


@pytest.fixture
def certificates(monkeypatch):
    """Client certificates presented on a request: ``environ_base={'peercert': {'owner': name}}``
    is a certificate enrolled for that account; mTLS is on."""
    from services.certificate_parser import CertificateParser
    from services.mtls_auth_service import MTLSAuthService
    monkeypatch.setattr(MTLSAuthService, 'is_mtls_enabled', staticmethod(lambda: True))
    monkeypatch.setattr(CertificateParser, 'extract_from_flask_native',
                        staticmethod(lambda peercert: {'owner': peercert.get('owner')}))

    def authenticate(cert_info):
        user = User.query.filter_by(username=cert_info.get('owner')).first()
        if user is None:
            return None, None, 'Certificate not enrolled'
        return user, SimpleNamespace(id=user.id, cert_serial=f'0a{user.id}', name='client'), None
    monkeypatch.setattr(MTLSAuthService, 'authenticate_certificate', staticmethod(authenticate))
    return lambda name: {'peercert': {'owner': name}}


@pytest.fixture
def factors(app):
    """Enrolls a certificate or a passkey on an account; removed after the test."""
    from models.auth_certificate import AuthCertificate
    from models.webauthn import WebAuthnCredential
    made = []

    def _add(user, kind, application=None):
        application = application or app
        with application.app_context():
            if kind == 'certificate':
                row = AuthCertificate(user_id=user['id'], cert_serial=uuid.uuid4().hex[:16],
                                      cert_subject=f"CN={user['username']}", cert_issuer='CN=probe')
            else:
                row = WebAuthnCredential(user_id=user['id'], credential_id=uuid.uuid4().bytes,
                                         public_key=b'probe', sign_count=0, name='probe')
            db.session.add(row)
            db.session.commit()
            made.append((application, type(row), row.id))
            return row.id if kind == 'certificate' else row.credential_id

    yield _add
    from models.webauthn import WebAuthnChallenge
    for application, model, row_id in made:
        with application.app_context():
            row = db.session.get(model, row_id)
            if row is not None:
                WebAuthnChallenge.query.filter_by(user_id=row.user_id).delete()
                db.session.delete(row)
                db.session.commit()


# --- The lock keeps the session and refuses everything that needs it -----------------

def test_a_locked_session_answers_401_locked_with_its_account(app, make_user):
    user = make_user()
    c = _password_session(app, user)
    _lock(c)
    body = _refused_as_locked(_profile(c))
    assert body['details'] == {'username': user['username'], 'reason': 'manual'}
    data = _verify(c)
    assert data['authenticated'] is False
    assert data['locked']['username'] == user['username']
    assert data['locked']['reason'] == 'manual'
    assert data['locked']['methods'] == ['password']


def test_the_idle_lock_is_the_same_lock(app, make_user):
    user = make_user()
    c = _password_session(app, user)
    _lock(c, 'idle')
    assert _refused_as_locked(_profile(c))['details']['reason'] == 'inactivity'


def test_locking_a_locked_session_again_changes_nothing(app, make_user):
    user = make_user()
    c = _password_session(app, user)
    _lock(c)
    _lock(c, 'idle')
    assert _refused_as_locked(_profile(c))['details']['reason'] == 'manual'
    assert len(_audits(app, 'session_locked', user['username'])) == 1


def test_no_route_serves_a_locked_session_more_than_an_anonymous_caller(app, make_user):
    """Every GET route without a parameter: where no session gets 401, the locked one gets
    the locked 401; elsewhere both get the same status."""
    user = make_user()
    c = _password_session(app, user)
    _lock(c)
    anonymous = app.test_client()
    rules = sorted({r.rule for r in app.url_map.iter_rules()
                    if r.rule.startswith('/api/v2/') and 'GET' in r.methods and not r.arguments})
    assert len(rules) > 50
    for rule in rules:
        if rule in ('/api/v2/auth/verify', '/api/v2/sso/login', '/api/v2/sso/callback'):
            continue
        plain = anonymous.get(rule)
        locked = c.get(rule)
        if plain.status_code == 401:
            assert locked.status_code == 401, rule
            assert locked.get_json()['type'] == LOCKED, rule
        else:
            assert locked.status_code == plain.status_code, rule


def test_an_api_key_beside_a_locked_cookie_is_its_own_credential(app, make_user, auth_client):
    from tests.conftest import assert_success
    key = assert_success(auth_client.post('/api/v2/account/apikeys', data=json.dumps(
        {'name': 'beside-lock', 'permissions': ['read:certificates']}),
        content_type='application/json'), 201)
    try:
        user = make_user()
        c = _password_session(app, user)
        _lock(c)
        assert c.get('/api/v2/certificates', headers={'X-API-Key': key['key']}).status_code == 200
        _refused_as_locked(c.get('/api/v2/certificates'))
        bad = c.get('/api/v2/certificates', headers={'X-API-Key': 'ucm_ak_forged'})
        assert bad.status_code == 401 and bad.get_json()['type'] == AUTH_REQUIRED
    finally:
        auth_client.delete(f"/api/v2/account/apikeys/{key['id']}")


def test_the_session_check_refuses_a_locked_session(app):
    """The check the API, the guide and the WebSocket share."""
    from flask import session
    from auth.session_lock import lock_session
    from auth.unified import AuthManager
    with app.app_context():
        admin = User.query.filter_by(username='admin').first()
        from auth.session_start import account_proof, ACCOUNT_KEY
        from auth.session_epoch import SESSION_KEY, current_epoch
        from utils.datetime_utils import utc_now
        with app.test_request_context('/api/v2/account/profile'):
            session.update({'user_id': admin.id, 'username': admin.username,
                            'session_version': admin.session_version or 0,
                            ACCOUNT_KEY: account_proof(admin), SESSION_KEY: current_epoch(),
                            'login_time': utc_now().isoformat(),
                            'last_activity': utc_now().isoformat()})
            assert AuthManager().verify_session() is not None
            lock_session('manual')
            assert AuthManager().verify_session() is None
            assert session.get('user_id') == admin.id


# --- No automatic door reopens it ---------------------------------------------------

def test_a_certificate_presented_never_reopens_a_locked_session(app, make_user, certificates):
    user = make_user()
    c = _password_session(app, user)
    _lock(c)
    with app.app_context():
        floor = db.session.query(db.func.max(AuditLog.id)).scalar() or 0
    for path in ('/api/v2/auth/verify', '/api/v2/auth/methods', '/api/v2/sso/available',
                 '/api/v2/account/profile'):
        c.get(path, environ_base=certificates(user['username']))
    _refused_as_locked(_profile(c, environ_base=certificates(user['username'])))
    data = c.get('/api/v2/auth/verify', environ_base=certificates(user['username'])).get_json()['data']
    assert data['authenticated'] is False and data['locked']['username'] == user['username']
    with app.app_context():
        assert not AuditLog.query.filter(AuditLog.id > floor, AuditLog.action == 'login_success').count()


def test_the_methods_door_does_not_call_a_locked_certificate_session_signed_in(
        app, make_user, certificates):
    user = make_user()
    c = app.test_client()
    # Signed in by the certificate alone, then locked
    assert c.get('/api/v2/auth/verify', environ_base=certificates(user['username'])
                 ).get_json()['data']['authenticated'] is True
    _lock(c)
    methods = c.get('/api/v2/auth/methods', environ_base=certificates(user['username'])).get_json()['data']
    assert methods['mtls_status'] != 'auto_logged_in'
    _refused_as_locked(_profile(c, environ_base=certificates(user['username'])))


@pytest.mark.parametrize('door', ['password', 'other-password', 'mtls', 'passkey', 'ldap', 'legacy'])
def test_no_sign_in_door_replaces_a_locked_session(app, make_user, certificates, monkeypatch, door):
    from services.webauthn_service import WebAuthnService
    user, other = make_user(), make_user()
    monkeypatch.setattr(WebAuthnService, 'verify_authentication', staticmethod(
        lambda user_id, response, host, **_kw: (True, '', db.session.get(User, user_id))))
    c = _password_session(app, user)
    _lock(c)
    if door in ('password', 'other-password', 'legacy'):
        name = other['username'] if door == 'other-password' else user['username']
        url = '/api/v2/auth/login' if door == 'legacy' else '/api/v2/auth/login/password'
        r = _post(c, url, {'username': name, 'password': PASSWORD})
    elif door == 'mtls':
        r = c.post('/api/v2/auth/login/mtls', environ_base=certificates(user['username']))
    elif door == 'passkey':
        r = _post(c, '/api/v2/auth/login/webauthn/verify',
                  {'username': user['username'], 'response': {'id': 'x'}})
    else:
        r = _post(c, '/api/v2/sso/ldap/login', {'username': user['username'], 'password': PASSWORD})
    _refused_as_locked(r)
    _refused_as_locked(_profile(c))
    assert any(not ok for ok, _ in _audits(app, 'session_unlock_failure', user['username']))


@pytest.mark.parametrize('path', ['/api/v2/sso/login/oauth2', '/api/v2/sso/callback/oauth2',
                                  '/api/v2/sso/login/saml', '/api/v2/sso/callback/saml'])
def test_an_sso_return_never_replaces_a_locked_session(app, make_user, path):
    user = make_user()
    c = _password_session(app, user)
    _lock(c)
    r = c.get(path)
    assert r.status_code == 302
    assert r.headers['Location'].endswith('/login?error=session_locked')
    _refused_as_locked(_profile(c))


def test_a_sign_in_over_a_locked_session_is_refused_at_its_start(app, make_user):
    """begin_session is where every sign-in starts: it refuses a locked session itself."""
    from flask import session
    from auth.session_lock import SessionLocked, lock_session
    from auth.session_start import begin_session
    user = make_user()
    with app.app_context():
        row = db.session.get(User, user['id'])
        with app.test_request_context('/'):
            session['user_id'] = row.id
            lock_session('manual')
            with pytest.raises(SessionLocked):
                begin_session(row)
            assert session.get('user_id') == row.id


# --- Sign-out stays open --------------------------------------------------------------

def test_signing_out_ends_a_locked_session(app, make_user):
    user = make_user()
    c = _password_session(app, user)
    _lock(c)
    assert _post(c, '/api/v2/auth/logout').status_code == 200
    r = _profile(c)
    assert r.status_code == 401 and r.get_json()['type'] == AUTH_REQUIRED
    assert 'locked' not in _verify(c)
    # Another account then signs in
    other = make_user()
    assert _post(c, '/api/v2/auth/login/password',
                 {'username': other['username'], 'password': PASSWORD}).status_code == 200
    assert _profile(c).status_code == 200


# --- Unlock by password -------------------------------------------------------------

def test_the_password_unlocks_into_a_new_identifier(app, make_user):
    user = make_user()
    c = _password_session(app, user)
    _lock(c)
    held = c.get_cookie('session').value
    r = _post(c, '/api/v2/auth/unlock/password', {'password': PASSWORD})
    assert r.status_code == 200, r.data
    data = r.get_json()['data']
    assert data['user']['username'] == user['username'] and data['auth_method'] == 'password'
    assert data['csrf_token']
    assert _profile(c).status_code == 200
    assert c.get_cookie('session').value != held
    replay = app.test_client()
    replay.set_cookie('session', held)
    assert _profile(replay).status_code == 401
    assert _audits(app, 'session_unlocked', user['username']) == [
        (True, f"Session unlocked by {user['username']} (password)")]


def test_a_wrong_password_is_refused_audited_and_counted(app, make_user):
    user = make_user()
    c = _password_session(app, user)
    _lock(c)
    r = _post(c, '/api/v2/auth/unlock/password', {'password': 'wrong'})
    assert r.status_code == 401 and r.get_json()['type'] != LOCKED
    _refused_as_locked(_profile(c))
    assert _audits(app, 'session_unlock_failure', user['username']) == [
        (False, 'Unlock refused for {} (password: invalid password)'.format(user['username']))]
    with app.app_context():
        assert db.session.get(User, user['id']).failed_logins == 1


def test_password_unlock_tries_end_at_the_sign_in_limit(app, make_user):
    from api.v2.sso.helpers import _get_lockout_settings
    with app.app_context():
        max_attempts = _get_lockout_settings()[0]
    user = make_user()
    c = _password_session(app, user)
    _lock(c)
    for _ in range(max_attempts):
        assert _post(c, '/api/v2/auth/unlock/password', {'password': 'wrong'}).status_code == 401
    # The right password is refused too while the account is locked, as at the sign-in
    assert _post(c, '/api/v2/auth/unlock/password', {'password': PASSWORD}).status_code == 401
    _refused_as_locked(_profile(c))
    assert _post(app.test_client(), '/api/v2/auth/login/password',
                 {'username': user['username'], 'password': PASSWORD}).status_code == 401


def test_the_password_unlock_asks_the_second_factor_the_sign_in_asks(app, make_user):
    user = make_user(totp=True)
    c = _password_session(app, user)
    _lock(c)
    r = _post(c, '/api/v2/auth/unlock/password', {'password': PASSWORD})
    assert r.status_code == 200
    assert r.get_json()['data'] == {'requires_2fa': True, 'methods': ['totp']}
    _refused_as_locked(_profile(c))
    assert _post(c, '/api/v2/auth/unlock/2fa', {'code': '000000'}).status_code == 401
    _refused_as_locked(_profile(c))
    # The sign-in spent the current step: the next one, inside the accepted window
    r = _post(c, '/api/v2/auth/unlock/2fa', {'code': _next_code(user)})
    assert r.status_code == 200, r.data
    assert _profile(c).status_code == 200
    assert _audits(app, 'session_unlocked', user['username'])[-1] == (
        True, f"Session unlocked by {user['username']} (password and two-factor code)")


def test_the_second_factor_step_needs_the_password_first(app, make_user):
    user = make_user(totp=True)
    c = _password_session(app, user)
    _lock(c)
    r = _post(c, '/api/v2/auth/unlock/2fa', {'code': _next_code(user)})
    assert r.status_code == 401
    _refused_as_locked(_profile(c))


def test_an_account_without_a_password_is_not_offered_one(app, make_user):
    from api.v2.sso.account_state import SSO_NO_PASSWORD
    user = make_user()
    c = _password_session(app, user)
    with app.app_context():
        db.session.get(User, user['id']).password_hash = SSO_NO_PASSWORD
        db.session.commit()
    _lock(c)
    assert _verify(c)['locked']['methods'] == []
    r = _post(c, '/api/v2/auth/unlock/password', {'password': PASSWORD})
    assert r.status_code == 400


def test_a_directory_account_unlocks_through_its_directory(app, make_user, monkeypatch):
    """An LDAP session checks the password at the directory, on the same account only."""
    import api.v2.auth_unlock as unlock
    from models import SSOProvider, UserSSOIdentity
    user = make_user()
    with app.app_context():
        provider = SSOProvider(name=f'unlock-ldap-{uuid.uuid4().hex[:6]}', provider_type='ldap',
                               enabled=True, ldap_server='ldap.example.test', ldap_port=389,
                               ldap_base_dn='dc=example,dc=test')
        db.session.add(provider)
        db.session.flush()
        db.session.add(UserSSOIdentity(user_id=user['id'], provider_id=provider.id,
                                       external_id=f"uid={user['username']}"))
        db.session.commit()
        provider_id = provider.id
    seen = []

    def bind(provider, username, password, before_bind=None):
        seen.append((provider.id, username))
        identity = {'dn': f'uid={username}', 'username': username, 'email': ''}
        if before_bind is not None and not before_bind(identity):
            return None, unlock.ATTEMPT_REFUSED
        return (dict(identity, groups=[]), None) if password == 'directory-pass' else (None, 'Invalid credentials')
    monkeypatch.setattr(unlock, '_ldap_authenticate_user', bind)
    monkeypatch.setattr(unlock, '_ldap_local_account',
                        lambda p, identity: User.query.filter_by(username=identity['username']).first())
    try:
        c = _password_session(app, user)
        with c.session_transaction() as sess:
            sess['auth_method'] = 'ldap'
        _lock(c)
        assert _verify(c)['locked']['methods'] == ['password']
        assert _post(c, '/api/v2/auth/unlock/password', {'password': PASSWORD}).status_code == 401
        r = _post(c, '/api/v2/auth/unlock/password', {'password': 'directory-pass'})
        assert r.status_code == 200, r.data
        assert r.get_json()['data']['auth_method'] == 'ldap'
        assert seen and all(entry == (provider_id, user['username']) for entry in seen)
        assert _profile(c).status_code == 200
    finally:
        with app.app_context():
            UserSSOIdentity.query.filter_by(provider_id=provider_id).delete()
            db.session.delete(db.session.get(SSOProvider, provider_id))
            db.session.commit()


# --- Unlock by client certificate ------------------------------------------------------

def test_the_accounts_own_certificate_unlocks(app, make_user, certificates, factors):
    user = make_user()
    factors(user, 'certificate')
    c = _password_session(app, user)
    _lock(c)
    assert _verify(c)['locked']['methods'] == ['password', 'certificate']
    r = c.post('/api/v2/auth/unlock/certificate', environ_base=certificates(user['username']))
    assert r.status_code == 200, r.data
    assert r.get_json()['data']['auth_method'] == 'mtls'
    assert _profile(c).status_code == 200
    assert _audits(app, 'session_unlocked', user['username'])[-1] == (
        True, f"Session unlocked by {user['username']} (client certificate)")


def test_the_certificate_of_another_account_is_refused_and_audited(app, make_user, certificates):
    user, other = make_user(), make_user()
    c = _password_session(app, user)
    _lock(c)
    r = c.post('/api/v2/auth/unlock/certificate', environ_base=certificates(other['username']))
    assert r.status_code == 401
    _refused_as_locked(_profile(c))
    assert _audits(app, 'session_unlock_failure', user['username'])[-1] == (
        False, f"Unlock refused for {user['username']} (client certificate: "
               f"certificate of another account, {other['username']})")


@pytest.mark.parametrize('presented', ['none', 'not-enrolled'])
def test_no_certificate_or_an_unknown_one_is_refused(app, make_user, certificates, presented):
    user = make_user()
    c = _password_session(app, user)
    _lock(c)
    kwargs = {} if presented == 'none' else {'environ_base': certificates('nobody-' + uuid.uuid4().hex)}
    r = c.post('/api/v2/auth/unlock/certificate', **kwargs)
    assert r.status_code == 401
    _refused_as_locked(_profile(c))
    assert _audits(app, 'session_unlock_failure', user['username'])


def test_the_certificate_door_is_shut_when_mtls_is_off(app, make_user, certificates, monkeypatch):
    from services.mtls_auth_service import MTLSAuthService
    user = make_user()
    c = _password_session(app, user)
    _lock(c)
    monkeypatch.setattr(MTLSAuthService, 'is_mtls_enabled', staticmethod(lambda: False))
    r = c.post('/api/v2/auth/unlock/certificate', environ_base=certificates(user['username']))
    assert r.status_code == 400
    _refused_as_locked(_profile(c))


# --- Unlock by passkey ------------------------------------------------------------------

def test_the_accounts_passkey_unlocks(app, make_user, factors, monkeypatch):
    from services.webauthn_service import WebAuthnService
    user = make_user()
    factors(user, 'passkey')
    calls = []

    def verify(user_id, response, host, challenge_type='authentication', expected_challenge=None):
        calls.append((user_id, challenge_type, expected_challenge))
        return True, '', db.session.get(User, user_id)
    monkeypatch.setattr(WebAuthnService, 'verify_authentication', staticmethod(verify))
    c = _password_session(app, user)
    _lock(c)
    assert _verify(c)['locked']['methods'] == ['password', 'passkey']
    # No options asked: nothing to answer
    assert _post(c, '/api/v2/auth/unlock/webauthn/verify', {'response': {'id': 'x'}}).status_code == 401
    r = _post(c, '/api/v2/auth/unlock/webauthn/options')
    assert r.status_code == 200, r.data
    challenge = r.get_json()['data']['options']['challenge']
    r = _post(c, '/api/v2/auth/unlock/webauthn/verify', {'response': {'id': 'x'}})
    assert r.status_code == 200, r.data
    assert r.get_json()['data']['auth_method'] == 'webauthn'
    assert calls[-1] == (user['id'], 'unlock', challenge)
    assert _profile(c).status_code == 200


def test_the_passkey_of_another_account_is_refused_and_audited(app, make_user, factors):
    import base64
    user, other = make_user(), make_user()
    factors(user, 'passkey')
    foreign = factors(other, 'passkey')
    c = _password_session(app, user)
    _lock(c)
    assert _post(c, '/api/v2/auth/unlock/webauthn/options').status_code == 200
    cred = base64.urlsafe_b64encode(foreign).rstrip(b'=').decode()
    r = _post(c, '/api/v2/auth/unlock/webauthn/verify', {'response': {'id': cred, 'response': {}}})
    assert r.status_code == 401
    _refused_as_locked(_profile(c))
    assert _audits(app, 'session_unlock_failure', user['username'])[-1] == (
        False, f"Unlock refused for {user['username']} (passkey: passkey of another account, "
               f"{other['username']})")


def test_passkey_unlock_tries_end_at_the_passkey_limit(app, make_user, factors, monkeypatch):
    from api.v2.sso.helpers import _get_lockout_settings
    from services.webauthn_service import WebAuthnService
    with app.app_context():
        max_attempts = _get_lockout_settings()[0]
    user = make_user()
    factors(user, 'passkey')
    ok = []
    monkeypatch.setattr(WebAuthnService, 'verify_authentication', staticmethod(
        lambda user_id, response, host, **_kw: (bool(ok), '', db.session.get(User, user_id))))
    c = _password_session(app, user)
    _lock(c)
    try:
        for _ in range(max_attempts):
            assert _post(c, '/api/v2/auth/unlock/webauthn/options').status_code == 200
            assert _post(c, '/api/v2/auth/unlock/webauthn/verify', {'response': {'id': 'x'}}).status_code == 401
        ok.append(True)
        assert _post(c, '/api/v2/auth/unlock/webauthn/options').status_code == 200
        assert _post(c, '/api/v2/auth/unlock/webauthn/verify', {'response': {'id': 'x'}}).status_code == 429
        _refused_as_locked(_profile(c))
    finally:
        from models.second_factor_failure import SecondFactorFailure
        with app.app_context():
            SecondFactorFailure.query.filter_by(target=user['username']).delete()
            db.session.commit()


def test_a_security_key_second_factor_completes_a_password_unlock(app, make_user, factors, monkeypatch):
    from services.webauthn_service import WebAuthnService
    user = make_user()
    factors(user, 'passkey')
    with app.app_context():
        db.session.get(User, user['id']).webauthn_2fa = True
        db.session.commit()
    calls = []

    def verify(user_id, response, host, challenge_type='authentication', expected_challenge=None):
        calls.append((challenge_type, expected_challenge))
        return True, '', db.session.get(User, user_id)
    monkeypatch.setattr(WebAuthnService, 'verify_authentication', staticmethod(verify))
    c = app.test_client()
    assert _post(c, '/api/v2/auth/login/password',
                 {'username': user['username'], 'password': PASSWORD}).get_json()['data']['requires_2fa']
    assert _post(c, '/api/v2/auth/login/2fa/webauthn/options').status_code == 200
    assert _post(c, '/api/v2/auth/login/2fa/webauthn/verify', {'response': {'id': 'x'}}).status_code == 200
    _lock(c)
    r = _post(c, '/api/v2/auth/unlock/password', {'password': PASSWORD})
    assert r.get_json()['data'] == {'requires_2fa': True, 'methods': ['webauthn']}
    _refused_as_locked(_profile(c))
    r = _post(c, '/api/v2/auth/unlock/2fa/webauthn/options')
    assert r.status_code == 200, r.data
    challenge = r.get_json()['data']['options']['challenge']
    r = _post(c, '/api/v2/auth/unlock/2fa/webauthn/verify', {'response': {'id': 'x'}})
    assert r.status_code == 200, r.data
    assert calls[-1] == ('2fa', challenge)
    assert _profile(c).status_code == 200
    assert _audits(app, 'session_unlocked', user['username'])[-1] == (
        True, f"Session unlocked by {user['username']} (password and security key)")


def test_an_account_without_a_passkey_gets_no_options(app, make_user):
    user = make_user()
    c = _password_session(app, user)
    _lock(c)
    assert _post(c, '/api/v2/auth/unlock/webauthn/options').status_code == 400


# --- The unlock doors themselves ------------------------------------------------------

@pytest.mark.parametrize('path', [
    '/api/v2/auth/unlock/password', '/api/v2/auth/unlock/certificate', '/api/v2/auth/unlock/2fa',
    '/api/v2/auth/unlock/2fa/webauthn/options', '/api/v2/auth/unlock/2fa/webauthn/verify',
    '/api/v2/auth/unlock/webauthn/options', '/api/v2/auth/unlock/webauthn/verify'])
def test_the_unlock_doors_need_a_locked_session(app, make_user, path):
    assert _post(app.test_client(), path, {'password': PASSWORD}).status_code == 401
    user = make_user()
    c = _password_session(app, user)
    assert _post(c, path, {'password': PASSWORD}).status_code == 409
    assert _profile(c).status_code == 200


@pytest.fixture
def csrf_on(monkeypatch):
    from security.csrf import CSRFProtection
    monkeypatch.setattr(CSRFProtection, 'is_enabled', classmethod(lambda cls: True))


def test_unlocking_needs_the_csrf_token_the_locked_verify_gives(app, make_user, csrf_on):
    user = make_user()
    c = _password_session(app, user)
    token = _verify(c)['csrf_token']
    assert _post(c, '/api/v2/auth/lock', headers={'X-CSRF-Token': token}).status_code == 200
    assert _post(c, '/api/v2/auth/unlock/password', {'password': PASSWORD}).status_code == 403
    token = _verify(c)['csrf_token']
    assert token
    r = _post(c, '/api/v2/auth/unlock/password', {'password': PASSWORD},
              headers={'X-CSRF-Token': token})
    assert r.status_code == 200, r.data


def test_an_unlock_keeps_a_forced_enrolment(app, make_user):
    with app.app_context():
        from models import SystemConfig
        row = SystemConfig.query.filter_by(key='enforce_2fa').first()
        before = row.value if row else None
        if row is None:
            row = SystemConfig(key='enforce_2fa', value='true')
            db.session.add(row)
        row.value = 'true'
        db.session.commit()
    try:
        user = make_user()
        c = app.test_client()
        r = _post(c, '/api/v2/auth/login/password', {'username': user['username'], 'password': PASSWORD})
        assert r.get_json()['data']['requires_2fa_enrollment'] is True
        _lock(c)
        r = _post(c, '/api/v2/auth/unlock/password', {'password': PASSWORD})
        assert r.status_code == 200, r.data
        assert r.get_json()['data']['requires_2fa_enrollment'] is True
        assert _profile(c).status_code == 403
    finally:
        with app.app_context():
            from models import SystemConfig
            row = SystemConfig.query.filter_by(key='enforce_2fa').first()
            if before is None:
                db.session.delete(row)
            else:
                row.value = before
            db.session.commit()


def test_a_disabled_account_cannot_unlock(app, make_user):
    user = make_user()
    c = _password_session(app, user)
    _lock(c)
    with app.app_context():
        db.session.get(User, user['id']).active = False
        db.session.commit()
    assert _post(c, '/api/v2/auth/unlock/password', {'password': PASSWORD}).status_code == 401
    _refused_as_locked(_profile(c))


# --- HA: the lock and the unlock are seen by every node ----------------------------------

def test_the_lock_holds_on_every_node_and_any_node_unlocks(nodes, make_user, certificates):
    first, second = nodes
    user = make_user(first)
    c = _password_session(first, user)
    held = c.get_cookie('session').value
    other = second.test_client()
    other.set_cookie('session', held)
    assert _profile(other).status_code == 200
    _lock(c)
    # The certificate presented on the other node opens nothing
    _refused_as_locked(_profile(other, environ_base=certificates(user['username'])))
    assert other.get('/api/v2/auth/verify', environ_base=certificates(user['username'])
                     ).get_json()['data']['locked']['username'] == user['username']
    _refused_as_locked(_profile(c))
    r = _post(other, '/api/v2/auth/unlock/password', {'password': PASSWORD})
    assert r.status_code == 200, r.data
    reopened = other.get_cookie('session').value
    back = first.test_client()
    back.set_cookie('session', reopened)
    assert _profile(back).status_code == 200
    stale = first.test_client()
    stale.set_cookie('session', held)
    assert _profile(stale).status_code == 401


# --- A request in flight never undoes the lock -------------------------------------------

@contextmanager
def _profile_in_flight(application, client):
    """A GET /account/profile of ``client`` held at its view, its session copy already read,
    until the block ends; it then completes and saves that copy. Yields its response holder."""
    endpoint = application.url_map.bind('localhost').match('/api/v2/account/profile', method='GET')[0]
    view = application.view_functions[endpoint]
    entered, release, held, response = threading.Event(), threading.Event(), [], {}

    def holding(*args, **kwargs):
        if not held:
            held.append(1)
            entered.set()
            release.wait(15)
        return view(*args, **kwargs)

    application.view_functions[endpoint] = holding
    worker = threading.Thread(target=lambda: response.setdefault('r', _profile(client)))
    worker.start()
    try:
        assert entered.wait(15), 'the request in flight never reached its view'
        yield response
    finally:
        release.set()
        worker.join(30)
        application.view_functions[endpoint] = view
    assert not worker.is_alive()


def _held_by(application, cookie):
    client = application.test_client()
    client.set_cookie('session', cookie)
    return client


def test_a_request_in_flight_when_the_lock_lands_never_lifts_it(nodes, make_user):
    """It read the session before the lock and saves its copy after: the lock stays,
    on the node that locked and on the one that served the request."""
    first, second = nodes
    user = make_user(first)
    c = _password_session(first, user)
    held = c.get_cookie('session').value
    with _profile_in_flight(second, _held_by(second, held)) as flight:
        _lock(c)
        _refused_as_locked(_profile(c))
    assert flight['r'].status_code == 200
    for client in (c, _held_by(first, held), _held_by(second, held)):
        _refused_as_locked(_profile(client))
        assert _verify(client)['authenticated'] is False


def test_a_request_in_flight_across_an_unlock_never_brings_the_old_session_back(nodes, make_user):
    first, second = nodes
    user = make_user(first)
    c = _password_session(first, user)
    held = c.get_cookie('session').value
    with _profile_in_flight(second, _held_by(second, held)):
        _lock(c)
        assert _post(c, '/api/v2/auth/unlock/password', {'password': PASSWORD}).status_code == 200
    assert c.get_cookie('session').value != held
    assert _profile(c).status_code == 200
    for node in (first, second):
        r = _profile(_held_by(node, held))
        assert r.status_code == 401 and r.get_json()['type'] == AUTH_REQUIRED


@pytest.mark.parametrize('locked', [False, True])
def test_a_request_in_flight_across_a_sign_out_never_brings_the_session_back(nodes, make_user, locked):
    first, second = nodes
    user = make_user(first)
    c = _password_session(first, user)
    held = c.get_cookie('session').value
    with _profile_in_flight(second, _held_by(second, held)):
        if locked:
            _lock(c)
        assert _post(c, '/api/v2/auth/logout').status_code == 200
    for node in (first, second):
        r = _profile(_held_by(node, held))
        assert r.status_code == 401 and r.get_json()['type'] == AUTH_REQUIRED


def _store_raw(application, store_id, data):
    """Writes ``data`` as the stored record of ``store_id``, as another node's save would."""
    interface = application.session_interface
    encoded = interface.serializer.encode(data)
    if application.config['SESSION_TYPE'] == 'redis':
        assert interface.client.set(store_id, encoded, keepttl=True, xx=True)
        return
    model = interface.sql_session_model
    with interface._store() as s:
        assert s.query(model).filter_by(session_id=store_id).update(
            {'data': encoded}, synchronize_session=False) == 1
        s.commit()


def test_a_lock_stored_between_the_read_and_the_write_of_a_save_is_kept(nodes, make_user, monkeypatch):
    """The save compares and swaps (SQL) or watches the key (Redis): a lock landing after it
    read the record is read again and kept, never overwritten."""
    first, second = nodes
    kind = second.config['SESSION_TYPE']
    if kind == 'filesystem':
        pytest.skip('the file store writes a lock under an exclusive flock, which no save straddles')
    import utils.session_store as module
    if kind == 'redis':
        import utils.session_store_redis as module
    user = make_user(first)
    c = _password_session(first, user)
    held = c.get_cookie('session').value
    store_id = second.session_interface._get_store_id(held)
    real, landed = module.keep_stored_lock, []

    def lock_lands_now(session, stored):
        if not landed:
            landed.append(True)
            _store_raw(second, store_id, dict(stored, locked={'at': utc_now().isoformat(), 'reason': 'manual'}))
        return real(session, stored)

    monkeypatch.setattr(module, 'keep_stored_lock', lock_lands_now)
    assert _profile(_held_by(second, held)).status_code == 200
    assert landed
    _refused_as_locked(_profile(c))
