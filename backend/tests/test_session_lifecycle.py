"""Session identifiers, one-time TOTP codes and sessions closed by a credential change.

RFC 6265 §8.4 (session fixation): every login hands out a new identifier.
RFC 6238 §5.2: a TOTP code accepted once is refused the second time.
A password change or reset, a 2FA reset and "revoke all" close the other sessions.
"""
import hashlib
import json
import time
import uuid
from datetime import timedelta

import pyotp
import pytest

from models import User, db
from tests.conftest import get_json
from tests.test_auth_failure_messages import ldap_provider  # noqa: F401 (fixture)
from utils.datetime_utils import utc_now

PASSWORD = 'Sess10n-Lifecycle!'
NEW_PASSWORD = 'Sess10n-Changed-42!'


def _post(c, url, body=None):
    return c.post(url, data=json.dumps(body or {}), content_type='application/json')


def _sid(c):
    cookie = c.get_cookie('session')
    return cookie.value if cookie else None


def _authenticated(c):
    return c.get('/api/v2/account/profile').status_code == 200


def _login(c, username, password=PASSWORD):
    return _post(c, '/api/v2/auth/login/password', {'username': username, 'password': password})


@pytest.fixture
def make_user(app):
    created = []

    def _make(totp=False, role='operator'):
        with app.app_context():
            user = User(username=f'sess-{uuid.uuid4().hex[:8]}',
                        email=f'{uuid.uuid4().hex[:8]}@example.test', role=role)
            user.set_password(PASSWORD)
            if totp:
                user.totp_secret = pyotp.random_base32()
                user.totp_confirmed = True
            db.session.add(user)
            db.session.commit()
            created.append(user.id)
            return user.id, user.username, user.totp_secret

    yield _make

    from api.v2.auth_methods import _2fa_failed_attempts
    _2fa_failed_attempts.clear()
    with app.app_context():
        for uid in created:
            user = db.session.get(User, uid)
            if user:
                db.session.delete(user)
        db.session.commit()


def _session(app, username, password=PASSWORD):
    c = app.test_client()
    r = _login(c, username, password)
    assert r.status_code == 200, r.data
    assert _authenticated(c)
    return c


def _code(secret, steps_ahead=0):
    """The code of the current time step, or of a later one still in the window."""
    return pyotp.TOTP(secret).at(time.time() + 30 * steps_ahead)


# --- RFC 6238 §5.2: one-time use ------------------------------------------

def test_a_totp_code_logs_in_once(app, make_user):
    _uid, username, secret = make_user(totp=True)
    code = _code(secret)

    first = app.test_client()
    assert get_json(_login(first, username))['data']['requires_2fa'] is True
    assert _post(first, '/api/v2/auth/login/2fa', {'code': code}).status_code == 200

    second = app.test_client()
    assert get_json(_login(second, username))['data']['requires_2fa'] is True
    r = _post(second, '/api/v2/auth/login/2fa', {'code': code})
    assert r.status_code == 401, r.data
    assert not _authenticated(second)


def test_an_older_step_is_refused_after_a_newer_one(app, make_user):
    _uid, username, secret = make_user(totp=True)
    c = app.test_client()
    _login(c, username)
    assert _post(c, '/api/v2/auth/login/2fa', {'code': _code(secret, 1)}).status_code == 200

    c = app.test_client()
    _login(c, username)
    assert _post(c, '/api/v2/auth/login/2fa', {'code': _code(secret)}).status_code == 401


def test_the_login_code_cannot_disable_2fa(app, make_user):
    _uid, username, secret = make_user(totp=True)
    c = app.test_client()
    _login(c, username)
    code = _code(secret)
    assert _post(c, '/api/v2/auth/login/2fa', {'code': code}).status_code == 200

    assert _post(c, '/api/v2/account/2fa/disable', {'code': code}).status_code == 400
    assert _post(c, '/api/v2/account/2fa/disable', {'code': _code(secret, 1)}).status_code == 200


# --- RFC 6265 §8.4: no session fixation -------------------------------------

def test_login_issues_a_new_session_identifier(app, make_user):
    _uid, victim_name, _ = make_user()
    _uid2, attacker_name, _ = make_user()
    attacker = _session(app, attacker_name)
    planted = _sid(attacker)

    victim = app.test_client()
    victim.set_cookie('session', planted)
    assert _login(victim, victim_name).status_code == 200
    assert _sid(victim) != planted

    profile = attacker.get('/api/v2/account/profile')
    assert profile.status_code == 401 or get_json(profile)['data']['username'] != victim_name


def test_relogin_drops_the_previous_identifier(app, make_user):
    _uid, username, _ = make_user()
    c = _session(app, username)
    before = _sid(c)
    assert _login(c, username).status_code == 200
    assert _sid(c) != before

    stale = app.test_client()
    stale.set_cookie('session', before)
    assert not _authenticated(stale)


def test_second_factor_completion_issues_a_new_identifier(app, make_user):
    _uid, username, secret = make_user(totp=True)
    c = app.test_client()
    _login(c, username)
    pending = _sid(c)
    assert _post(c, '/api/v2/auth/login/2fa', {'code': _code(secret)}).status_code == 200
    assert _sid(c) != pending


# --- credential changes close the other sessions ----------------------------

def test_password_change_closes_the_other_sessions(app, make_user):
    _uid, username, _ = make_user()
    other = _session(app, username)
    current = _session(app, username)
    before = _sid(current)

    r = _post(current, '/api/v2/account/password',
              {'current_password': PASSWORD, 'new_password': NEW_PASSWORD})
    assert r.status_code == 200, r.data

    assert not _authenticated(other)
    assert _authenticated(current)
    assert _sid(current) != before


def test_admin_password_reset_closes_the_user_sessions(app, make_user, auth_client):
    uid, username, _ = make_user()
    victim = _session(app, username)
    r = _post(auth_client, f'/api/v2/users/{uid}/reset-password', {'new_password': NEW_PASSWORD})
    assert r.status_code == 200, r.data
    assert not _authenticated(victim)


def test_email_reset_closes_the_user_sessions(app, make_user):
    uid, username, _ = make_user()
    victim = _session(app, username)
    token = uuid.uuid4().hex
    with app.app_context():
        user = db.session.get(User, uid)
        user.password_reset_token = hashlib.sha256(token.encode()).hexdigest()
        user.password_reset_expires = utc_now() + timedelta(hours=1)
        db.session.commit()
    r = _post(app.test_client(), '/api/v2/auth/reset-password', {'token': token, 'password': NEW_PASSWORD})
    assert r.status_code == 200, r.data
    assert not _authenticated(victim)


def test_admin_2fa_reset_closes_the_user_sessions(app, make_user, auth_client):
    uid, username, secret = make_user(totp=True)
    victim = app.test_client()
    _login(victim, username)
    assert _post(victim, '/api/v2/auth/login/2fa', {'code': _code(secret)}).status_code == 200
    assert _authenticated(victim)
    assert _post(auth_client, f'/api/v2/users/{uid}/reset-2fa').status_code == 200
    assert not _authenticated(victim)


def test_revoke_all_closes_the_other_sessions_only(app, make_user):
    _uid, username, _ = make_user()
    other = _session(app, username)
    current = _session(app, username)
    assert _post(current, '/api/v2/account/sessions/revoke-all').status_code == 200
    assert not _authenticated(other)
    assert _authenticated(current)


def test_an_unrelated_user_keeps_its_session(app, make_user):
    _uid, username, _ = make_user()
    _uid2, bystander_name, _ = make_user()
    bystander = _session(app, bystander_name)
    current = _session(app, username)
    _post(current, '/api/v2/account/password',
          {'current_password': PASSWORD, 'new_password': NEW_PASSWORD})
    assert _authenticated(bystander)


def test_ldap_login_issues_a_new_identifier(app, make_user, ldap_provider, monkeypatch):
    from tests.test_auth_failure_messages import _bind_succeeds
    _uid, attacker_name, _ = make_user()
    planted = _sid(_session(app, attacker_name))
    username = f'ldapsess{uuid.uuid4().hex[:6]}'
    _bind_succeeds(monkeypatch, username)

    victim = app.test_client()
    victim.set_cookie('session', planted)
    r = _post(victim, '/api/v2/sso/ldap/login',
              {'username': username, 'password': PASSWORD, 'provider_id': ldap_provider})
    try:
        assert r.status_code == 200, r.data
        assert _sid(victim) != planted
    finally:
        with app.app_context():
            from models.sso import SSOSession
            user = User.query.filter_by(username=username).first()
            if user:
                SSOSession.query.filter_by(user_id=user.id).delete()
                db.session.delete(user)
                db.session.commit()


def test_a_pending_second_factor_ends_with_a_password_change(app, make_user):
    uid, username, secret = make_user(totp=True)
    pending = app.test_client()
    assert _login(pending, username).status_code == 200
    with app.app_context():
        user = db.session.get(User, uid)
        user.set_password(NEW_PASSWORD)
        db.session.commit()
    assert _post(pending, '/api/v2/auth/login/2fa', {'code': _code(secret)}).status_code == 401
    assert not _authenticated(pending)


@pytest.mark.parametrize('route, body', [
    ('reset-password', {'new_password': NEW_PASSWORD, 'current_password': PASSWORD}),
    ('', {'password': NEW_PASSWORD, 'current_password': PASSWORD}),
])
def test_an_admin_keeps_its_session_after_changing_its_own_password(app, make_user, route, body):
    uid, username, _ = make_user(role='admin')
    admin = _session(app, username)
    before = _sid(admin)
    url = f'/api/v2/users/{uid}/{route}'.rstrip('/')
    send = admin.post if route else admin.put
    r = send(url, data=json.dumps(body), content_type='application/json')
    assert r.status_code == 200, r.data
    assert _authenticated(admin)
    assert _sid(admin) != before


def test_a_locked_password_refusal_is_audited(app, make_user):
    from models import AuditLog
    uid, username, _ = make_user()
    with app.app_context():
        user = db.session.get(User, uid)
        user.locked_until = utc_now() + timedelta(minutes=30)
        db.session.commit()
    assert _login(app.test_client(), username).status_code == 401
    with app.app_context():
        assert AuditLog.query.filter_by(action='login_failure', username=username).filter(
            AuditLog.details.contains('account locked')).count() == 1
