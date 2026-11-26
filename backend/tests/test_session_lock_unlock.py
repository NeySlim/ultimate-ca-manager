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

from auth.session_start import SessionNotKept
from models import AuditLog, User, db
from utils.datetime_utils import utc_now
from tests.test_factor_change_sessions import (  # noqa: F401 (fixtures)
    PG_URL, _drop_session_table_from_metadata, nodes)
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
        {'password': 'changeme123', 'name': 'beside-lock', 'permissions': ['read:certificates']}),
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


def test_a_lock_saved_while_a_file_store_save_is_under_way_waits_and_wins(app, make_user, monkeypatch):
    """The file store writes a lock under an exclusive flock: a save that read the record before
    the lock finishes first, then the lock is written over it, never the reverse."""
    first = second = app
    if app.config['SESSION_TYPE'] != 'filesystem':
        pytest.skip('the SQL and Redis stores compare and swap (test above)')
    import utils.session_store as module
    monkeypatch.setattr(second.session_interface, 'lock_wait', 20.0)
    user = make_user(first)
    c = _password_session(first, user)
    held = c.get_cookie('session').value
    real, locking, done = module.keep_stored_lock, [], threading.Event()

    def lock_while_saving(session, stored):
        if not locking:
            # The lock request saves now; under the shared flock of this save it must wait
            worker = threading.Thread(target=lambda: (_lock(c), done.set()))
            locking.append(worker)
            worker.start()
            done.wait(1.5)
        return real(session, stored)

    monkeypatch.setattr(module, 'keep_stored_lock', lock_while_saving)
    assert _profile(_held_by(second, held)).status_code == 200
    locking[0].join(30)
    assert done.is_set()
    monkeypatch.setattr(module, 'keep_stored_lock', real)
    _refused_as_locked(_profile(c))


# --- A renewal of the identifier carries a lock that landed meanwhile --------------------

LOCK_NOT_STORED = 'urn:ucm:problem:session-lock-not-stored'
NEW_PASSWORD = 'An0ther-L0ck-Rotation!'


@contextmanager
def _in_flight(application, client, method, url, body=None):
    """``client``'s request held at its view, its session copy already read, until the block
    ends; it then completes and saves that copy. Yields its response holder."""
    endpoint = application.url_map.bind('localhost').match(url, method=method)[0]
    view = application.view_functions[endpoint]
    entered, release, held, response = threading.Event(), threading.Event(), [], {}

    def holding(*args, **kwargs):
        if not held:
            held.append(1)
            entered.set()
            release.wait(15)
        return view(*args, **kwargs)

    def send():
        response['r'] = client.open(url, method=method, data=json.dumps(body or {}),
                                     content_type='application/json')

    application.view_functions[endpoint] = holding
    worker = threading.Thread(target=send)
    worker.start()
    try:
        assert entered.wait(15), 'the request in flight never reached its view'
        yield response
    finally:
        release.set()
        worker.join(30)
        application.view_functions[endpoint] = view
    assert not worker.is_alive()


def _renewal(application, user, operation, factors):
    """(method, url, body, password after it) of a request that keeps the caller's session
    under a new identifier."""
    if operation == 'change-password':
        return 'POST', '/api/v2/account/password', {
            'current_password': PASSWORD, 'new_password': NEW_PASSWORD}, NEW_PASSWORD
    if operation == 'close-other-sessions':
        return 'POST', '/api/v2/account/sessions/revoke-all', None, PASSWORD
    if operation == 'disable-totp':
        return 'POST', '/api/v2/account/2fa/disable', {'code': _next_code(user)}, PASSWORD
    if operation == 'own-password-reset':
        # An administrator's reset of its own password: the route catches what the store raises
        with application.app_context():
            db.session.get(User, user['id']).role = 'admin'
            db.session.commit()
        return 'POST', f"/api/v2/users/{user['id']}/reset-password", {
            'current_password': PASSWORD, 'new_password': NEW_PASSWORD}, NEW_PASSWORD
    from models.webauthn import WebAuthnCredential
    credential = factors(user, 'passkey', application)
    with application.app_context():
        row_id = WebAuthnCredential.query.filter_by(credential_id=credential).one().id
    return 'DELETE', f'/api/v2/webauthn/credentials/{row_id}', None, PASSWORD


@pytest.mark.parametrize('operation', ['change-password', 'close-other-sessions',
                                       'disable-totp', 'delete-passkey'])
def test_a_lock_landing_while_the_identifier_is_renewed_moves_to_the_new_one(
        nodes, make_user, factors, operation):
    """A factor change read the session before the lock and renews its identifier after:
    the session it keeps under the new identifier is locked too, on every store."""
    first, second = nodes
    user = make_user(first, totp=operation == 'disable-totp')
    c = _password_session(first, user)
    held = c.get_cookie('session').value
    method, url, body, password = _renewal(first, user, operation, factors)
    renewing = _held_by(second, held)
    with _in_flight(second, renewing, method, url, body) as flight:
        _lock(c)
        _refused_as_locked(_profile(c))
    assert flight['r'].status_code == 200, flight['r'].data
    renewed = renewing.get_cookie('session').value
    assert renewed != held
    for node in (first, second):
        _refused_as_locked(_profile(_held_by(node, renewed)))
        assert _verify(_held_by(node, renewed))['authenticated'] is False
        r = _profile(_held_by(node, held))
        assert r.status_code == 401 and r.get_json()['type'] == AUTH_REQUIRED
    # Its own account unlocks it as any locked session
    back = _held_by(first, renewed)
    r = _post(back, '/api/v2/auth/unlock/password', {'password': password})
    assert r.status_code == 200, r.data
    assert _profile(back).status_code == 200


def test_a_lock_stored_between_the_read_and_the_move_of_a_renewal_moves_too(
        nodes, make_user, monkeypatch):
    """The move deletes the old record only as it read it (SQL) or under a watch (Redis): a
    lock landing after that read is read again and moves to the new identifier."""
    first, second = nodes
    kind = second.config['SESSION_TYPE']
    if kind == 'filesystem':
        pytest.skip('the file store moves a record under an exclusive flock, which no lock straddles')
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
    renewing = _held_by(second, held)
    assert _post(renewing, '/api/v2/account/sessions/revoke-all').status_code == 200
    assert landed
    renewed = renewing.get_cookie('session').value
    assert renewed != held
    _refused_as_locked(_profile(_held_by(first, renewed)))


# --- A renewal keeps its session against the old cookie's requests -------------------------

RENEWAL_OPERATIONS = ['change-password', 'close-other-sessions', 'disable-totp', 'delete-passkey']


@contextmanager
def _held_before_its_save(application):
    """The next request of ``application`` held once its view answered, before its session
    is saved, until the block ends."""
    entered, release, held = threading.Event(), threading.Event(), []

    def holding(response):
        if not held:
            held.append(1)
            entered.set()
            release.wait(15)
        return response

    hooks = application.after_request_funcs.setdefault(None, [])
    hooks.append(holding)
    try:
        yield entered
    finally:
        release.set()
        hooks.remove(holding)


def _send(client, method, url, body, response):
    response['r'] = client.open(url, method=method, data=json.dumps(body or {}),
                                content_type='application/json')


def _session_cookie_sent(r):
    return any(h.startswith('session=') for h in r.headers.getlist('Set-Cookie'))


def _records_of(application, user_id, remove=False):
    """The data of every stored session of ``user_id``; ``remove``: removes them too, as a
    revocation on another node would."""
    import os
    from itsdangerous import want_bytes
    interface = application.session_interface
    kind = application.config['SESSION_TYPE']
    found = []
    with application.app_context():
        if kind == 'filesystem':
            cache = interface.cache
            for name in cache._list_dir():
                with open(name, 'rb') as f:
                    f.read(4)
                    data = cache.serializer.load(f)
                if isinstance(data, dict) and data.get('user_id') == user_id:
                    found.append(data)
                    if remove:
                        os.remove(name)
        elif kind == 'redis':
            for key in interface.client.scan_iter(match=f'{interface.key_prefix}*'):
                blob = interface.client.get(key)
                data = interface.serializer.decode(blob) if blob else {}
                if data.get('user_id') == user_id:
                    found.append(data)
                    if remove:
                        interface.client.delete(key)
        else:
            model = interface.sql_session_model
            with interface._store() as s:
                for row in s.query(model.session_id, model.data).all():
                    data = interface.serializer.decode(want_bytes(row.data))
                    if data.get('user_id') == user_id:
                        found.append(data)
                        if remove:
                            s.query(model).filter_by(session_id=row.session_id).delete()
                s.commit()
    return found


def _remove_records_of(application, user_id):
    _records_of(application, user_id, remove=True)


@pytest.mark.parametrize('operation', RENEWAL_OPERATIONS)
def test_a_request_of_the_old_cookie_during_a_renewal_never_ends_the_kept_session(
        nodes, make_user, factors, operation):
    """Another tab's request with the old cookie, served once the renewal changed the session
    version and before its response: refused, and the session kept under the new identifier
    lives on every node."""
    first, second = nodes
    user = make_user(first, totp=operation == 'disable-totp')
    c = _password_session(first, user)
    held = c.get_cookie('session').value
    method, url, body, _password = _renewal(first, user, operation, factors)
    renewing, flight = _held_by(second, held), {}
    with _held_before_its_save(second) as entered:
        worker = threading.Thread(target=_send, args=(renewing, method, url, body, flight))
        worker.start()
        assert entered.wait(15), 'the renewal never answered'
        stale = _profile(_held_by(first, held))
        assert stale.status_code == 401 and stale.get_json()['type'] == AUTH_REQUIRED
    worker.join(30)
    assert flight['r'].status_code == 200, flight['r'].data
    renewed = renewing.get_cookie('session').value
    assert renewed != held
    for node in (first, second):
        assert _profile(_held_by(node, renewed)).status_code == 200
        assert _profile(_held_by(node, held)).status_code == 401


@pytest.mark.parametrize('operation', ['change-password', 'close-other-sessions'])
def test_a_sign_out_before_the_renewal_moves_its_record_stays_signed_out(
        nodes, make_user, factors, operation):
    """The old cookie signs out while the renewal waits at its view: the renewal answers
    without a session cookie and no identifier serves again."""
    first, second = nodes
    user = make_user(first)
    c = _password_session(first, user)
    held = c.get_cookie('session').value
    method, url, body, _password = _renewal(first, user, operation, factors)
    renewing = _held_by(second, held)
    with _in_flight(second, renewing, method, url, body) as flight:
        assert _post(c, '/api/v2/auth/logout').status_code == 200
    assert flight['r'].status_code == 200, flight['r'].data
    assert not _session_cookie_sent(flight['r'])
    for node in (first, second):
        assert _profile(_held_by(node, renewing.get_cookie('session').value)).status_code == 401
        assert _profile(_held_by(node, held)).status_code == 401


@pytest.mark.parametrize('operation', ['change-password', 'close-other-sessions'])
def test_a_renewed_record_removed_before_the_save_is_not_written_back(
        nodes, make_user, factors, operation):
    """The renewal's own save updates the record it moved, never recreates it: removed before
    that save, the session stays ended and no cookie names it."""
    first, second = nodes
    user = make_user(first)
    c = _password_session(first, user)
    held = c.get_cookie('session').value
    method, url, body, _password = _renewal(first, user, operation, factors)
    renewing, flight = _held_by(second, held), {}
    with _held_before_its_save(second) as entered:
        worker = threading.Thread(target=_send, args=(renewing, method, url, body, flight))
        worker.start()
        assert entered.wait(15), 'the renewal never answered'
        _remove_records_of(first, user['id'])
    worker.join(30)
    assert flight['r'].status_code == 200, flight['r'].data
    assert not _session_cookie_sent(flight['r'])
    assert renewing.get_cookie('session').value == held
    for node in (first, second):
        assert _profile(_held_by(node, held)).status_code == 401


# --- POST /auth/lock answers 200 only once the lock is stored ------------------------------

@contextmanager
def _lock_held_before_its_write(application):
    """The next POST /auth/lock held once its session check passed, before the lock is
    set and written, until the block ends."""
    import auth.session_lock as module
    real, entered, release = module.lock_session, threading.Event(), threading.Event()

    def holding(reason):
        entered.set()
        release.wait(15)
        return real(reason)

    module.lock_session = holding
    try:
        yield entered
    finally:
        release.set()
        module.lock_session = real


def _not_stored(r, cause):
    assert r.status_code == 409, r.data
    body = r.get_json()
    assert body['type'] == LOCK_NOT_STORED, body
    assert body['details'] == {'cause': cause}
    assert r.headers.get('Retry-After') == '1'
    assert not any(h.startswith('session=') for h in r.headers.getlist('Set-Cookie'))


@pytest.mark.parametrize('ending', ['renewal', 'sign-out'])
def test_a_lock_whose_session_went_before_its_write_says_it_was_not_stored(
        nodes, make_user, ending):
    """A renewal moved the record or a sign-out removed it after the lock's check: the lock
    answers 409 so the client sends it again (to the renewed session) or signs out."""
    first, second = nodes
    user = make_user(first)
    c = _password_session(first, user)
    held = c.get_cookie('session').value
    locking = _held_by(second, held)
    response = {}
    with _lock_held_before_its_write(second) as entered:
        worker = threading.Thread(target=lambda: response.setdefault(
            'r', _post(locking, '/api/v2/auth/lock', {'reason': 'manual'})))
        worker.start()
        assert entered.wait(15)
        if ending == 'renewal':
            assert _post(c, '/api/v2/account/sessions/revoke-all').status_code == 200
        else:
            assert _post(c, '/api/v2/auth/logout').status_code == 200
    worker.join(30)
    _not_stored(response['r'], 'gone')
    assert _audits(first, 'session_locked', user['username']) == []
    if ending == 'renewal':
        # Sent again with the renewed cookie, it locks the session that stays
        assert _profile(c).status_code == 200
        _lock(c)
        _refused_as_locked(_profile(c))
    else:
        assert _profile(c).status_code == 401


def test_a_lock_the_file_store_could_not_write_says_it_was_not_stored(app, make_user, monkeypatch):
    """The file store stayed held (a removal under way): no 200 for a lock never written."""
    if app.config['SESSION_TYPE'] != 'filesystem':
        pytest.skip('the file store only')
    from utils.session_store import HELD, session_files_lock
    monkeypatch.setattr(app.session_interface, 'lock_wait', 0.2)
    user = make_user()
    c = _password_session(app, user)
    with session_files_lock(app.session_interface.cache._path, True, 2.0) as state:
        assert state == HELD
        r = _post(c, '/api/v2/auth/lock', {'reason': 'manual'})
    _not_stored(r, 'busy')
    assert _profile(c).status_code == 200
    _lock(c)
    _refused_as_locked(_profile(c))


@pytest.mark.parametrize('nodes', ['sql-sqlite', pytest.param('sql-postgresql', marks=[
    pytest.mark.postgres, pytest.mark.skipif(not PG_URL, reason='no PostgreSQL URL')])], indirect=True)
def test_a_lock_while_ha_maintenance_pauses_session_writes_says_it_was_not_stored(
        nodes, make_user, monkeypatch):
    """An HA maintenance pauses the SQL store's writes: the lock answers 409 'busy', as when
    the file store stays held, and goes through once the writes resume."""
    first, second = nodes
    from utils.session_store import IsolatedSqlSessionInterface
    user = make_user(first)
    c = _password_session(first, user)
    with monkeypatch.context() as paused:
        paused.setattr(IsolatedSqlSessionInterface, '_writes_paused', staticmethod(lambda: True))
        r = _post(_held_by(second, c.get_cookie('session').value), '/api/v2/auth/lock',
                  {'reason': 'manual'})
    _not_stored(r, 'busy')
    assert _audits(first, 'session_locked', user['username']) == []
    assert _profile(c).status_code == 200
    _lock(c)
    _refused_as_locked(_profile(c))


# --- A renewal whose move fails or is refused ----------------------------------------------

def _failing_move(application, monkeypatch):
    """The store's move raises from now on, on every node of ``application``'s store."""
    kind = application.config['SESSION_TYPE']
    name = '_move_keeping_lock' if kind not in ('filesystem', 'redis') else '_move'

    def failing(*args, **kwargs):
        raise RuntimeError('session store failed during the move')

    monkeypatch.setattr(type(application.session_interface), name, failing)


@pytest.mark.parametrize('operation', RENEWAL_OPERATIONS + ['own-password-reset'])
def test_a_renewal_whose_move_fails_sends_no_cookie_and_writes_nothing_unguarded(
        nodes, make_user, factors, monkeypatch, operation):
    """The store raises while it moves the record, once a lock landed on it: the answer (an
    error, from the error handler or the route) names no new identifier, nothing is written
    without the store's guard, and the lock stays on every record of the session."""
    from auth.session_lock import is_locked
    first, second = nodes
    user = make_user(first, totp=operation == 'disable-totp')
    c = _password_session(first, user)
    held = c.get_cookie('session').value
    method, url, body, _password = _renewal(first, user, operation, factors)
    renewing = _held_by(second, held)
    with _in_flight(second, renewing, method, url, body) as flight:
        _lock(c)
        _failing_move(second, monkeypatch)
    r = flight['r']
    assert r.status_code == 500, r.data
    assert not _session_cookie_sent(r)
    assert renewing.get_cookie('session').value == held
    records = _records_of(first, user['id'])
    assert records and all(is_locked(data) for data in records), records
    for node in (first, second):
        assert _profile(_held_by(node, held)).status_code == 401


@contextmanager
def _move_refused_as_busy(application, monkeypatch):
    """The store refuses the renewal's move as 'busy', by a cause of its own: the file store
    stays held, the SQL row or the Redis key keeps changing under the move."""
    from utils.session_store import LOCK_MERGE_ATTEMPTS
    kind = application.config['SESSION_TYPE']
    if kind == 'filesystem':
        from utils.session_store import HELD, session_files_lock
        monkeypatch.setattr(application.session_interface, 'lock_wait', 0.2)
        with session_files_lock(application.session_interface.cache._path, True, 2.0) as state:
            assert state == HELD
            yield
        return
    import utils.session_store as module
    if kind == 'redis':
        import utils.session_store_redis as module
    real, changes = module.keep_stored_lock, []

    def changing(session, stored):
        moved = getattr(session, 'rotated_from', None)
        if moved:
            changes.append(1)
            _store_raw(application, moved, dict(stored, touched=len(changes)))
        return real(session, stored)

    monkeypatch.setattr(module, 'keep_stored_lock', changing)
    yield
    assert len(changes) == LOCK_MERGE_ATTEMPTS


def test_a_renewal_refused_by_the_store_counts_only_the_other_sessions(
        nodes, make_user, factors, monkeypatch):
    """The move refused as 'busy' leaves the caller's record at the replaced version: the
    answer says the change is saved but the session not kept, and the audit counts the
    account's other sessions only."""
    first, second = nodes
    user = make_user(first)
    other = _password_session(second, user)
    c = _password_session(first, user)
    method, url, body, _password = _renewal(first, user, 'delete-passkey', factors)
    with _move_refused_as_busy(first, monkeypatch):
        r = c.open(url, method=method, data=json.dumps(body or {}), content_type='application/json')
    assert r.status_code == 500, r.data
    assert r.get_json()['message'] == SessionNotKept.message
    assert not _session_cookie_sent(r)
    [(success, details)] = _audits(first, 'webauthn_delete', user['username'])
    assert success and '(1 other session closed)' in details, details
    assert _profile(other).status_code == 401
