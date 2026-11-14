"""Codes checked inside an open session share the login's second-factor lockout.

Disabling 2FA and regenerating recovery codes check a TOTP or recovery code: they
count on the same per-account budget as the second step of a login, answer 429
past it, clear it on success, and a request refused whatever its code counts nothing.
"""
import json
import time
import uuid

import pyotp
import pytest

from models import SystemConfig, User, db
from models.webauthn import WebAuthnCredential
from tests.test_webauthn_second_factor import SoftKey

PASSWORD = 'Sess10n-Lockout-Pass!'
RECOVERY = 'AAAA-BBBB-CCCC-DDDD'
LOCKED = (429, 'Too many failed attempts. Try again later.')
ROUTES = {
    'disable-totp': ('/api/v2/account/2fa/disable', 'code'),
    'disable-recovery': ('/api/v2/account/2fa/disable', 'backup_code'),
    'regenerate': ('/api/v2/account/2fa/recovery-codes/regenerate', 'code'),
}


def _post(c, url, body):
    return c.post(url, data=json.dumps(body), content_type='application/json')


def _reply(r):
    return r.status_code, (r.get_json() or {}).get('message')


def _failures(user_id):
    from api.v2.auth_methods import _2fa_failed_attempts
    return _2fa_failed_attempts.get(str(user_id), {}).get('count', 0)


@pytest.fixture
def make_user(app):
    from api.v2.auth_methods import _2fa_failed_attempts
    from utils.backup_codes import hash_codes
    created = []

    def _make(totp=True, key=False):
        with app.app_context():
            user = User(username=f'sflock-{uuid.uuid4().hex[:8]}',
                        email=f'{uuid.uuid4().hex[:8]}@example.test', role='operator')
            user.set_password(PASSWORD)
            if totp:
                user.totp_secret = pyotp.random_base32()
                user.totp_confirmed = True
                user.backup_codes = hash_codes([RECOVERY])
            db.session.add(user)
            db.session.flush()
            soft = SoftKey() if key else None
            if soft:
                user.webauthn_2fa = True
                db.session.add(WebAuthnCredential(user_id=user.id, credential_id=soft.credential_id,
                                                  public_key=soft.cose, sign_count=0, name='soft'))
            db.session.commit()
            created.append(user.id)
            return {'id': user.id, 'username': user.username, 'secret': user.totp_secret,
                    'key': soft}

    _2fa_failed_attempts.clear()
    yield _make
    _2fa_failed_attempts.clear()
    with app.app_context():
        from models.webauthn import WebAuthnChallenge
        for uid in created:
            WebAuthnChallenge.query.filter_by(user_id=uid).delete()
            WebAuthnCredential.query.filter_by(user_id=uid).delete()
            row = db.session.get(User, uid)
            if row:
                db.session.delete(row)
        SystemConfig.query.filter_by(key='enforce_2fa').delete()
        db.session.commit()


def _max_attempts(app):
    from api.v2.auth_methods import _get_2fa_lockout_settings
    with app.app_context():
        return _get_2fa_lockout_settings()[0]


def _password(c, user):
    r = _post(c, '/api/v2/auth/login/password', {'username': user['username'], 'password': PASSWORD})
    assert r.status_code == 200, r.data
    return r


def _session(app, user):
    """A full session after password and second factor."""
    c = app.test_client()
    _password(c, user)
    if user['secret']:
        r = _post(c, '/api/v2/auth/login/2fa', {'code': pyotp.TOTP(user['secret']).now()})
    else:
        from tests.test_webauthn_second_factor import _challenge, _verify
        r = _verify(c, user['key'].assert_(_challenge(c)))
    assert r.status_code == 200, r.data
    return c


def _right_value(user, field):
    return RECOVERY if field == 'backup_code' else pyotp.TOTP(user['secret']).at(time.time() + 30)


def _totp_on(app, user):
    with app.app_context():
        return db.session.get(User, user['id']).totp_confirmed


@pytest.mark.parametrize('route', sorted(ROUTES))
def test_codes_checked_in_a_session_are_bounded_with_the_login(app, make_user, route):
    user = make_user()
    max_attempts = _max_attempts(app)
    url, field = ROUTES[route]
    c = _session(app, user)
    for n in range(1, max_attempts + 1):
        r = _post(c, url, {field: '00000000'})
        assert r.status_code == 400, r.data
        assert _failures(user['id']) == n
    for value in ('00000000', _right_value(user, field)):
        assert _reply(_post(c, url, {field: value})) == LOCKED
    assert _failures(user['id']) == max_attempts
    assert _totp_on(app, user)
    # One budget per secret: the next login of the same user waits for the lock too
    other = app.test_client()
    _password(other, user)
    r = _post(other, '/api/v2/auth/login/2fa', {'code': pyotp.TOTP(user['secret']).now()})
    assert _reply(r) == LOCKED


@pytest.mark.parametrize('route', sorted(ROUTES))
def test_failed_logins_lock_the_session_code_checks(app, make_user, route):
    user = make_user()
    url, field = ROUTES[route]
    c = _session(app, user)
    other = app.test_client()
    _password(other, user)
    for _ in range(_max_attempts(app)):
        assert _post(other, '/api/v2/auth/login/2fa', {'code': '00000000'}).status_code == 401
    assert _reply(_post(c, url, {field: _right_value(user, field)})) == LOCKED
    assert _totp_on(app, user)


@pytest.mark.parametrize('route', sorted(ROUTES))
def test_a_session_code_check_that_succeeds_clears_the_counter(app, make_user, route):
    user = make_user()
    url, field = ROUTES[route]
    c = _session(app, user)
    for _ in range(_max_attempts(app) - 1):
        assert _post(c, url, {field: '00000000'}).status_code == 400
    r = _post(c, url, {field: _right_value(user, field)})
    assert r.status_code == 200, r.data
    assert _failures(user['id']) == 0


def test_a_disable_refused_by_required_2fa_uses_no_attempt(app, make_user):
    """Required 2FA with no key left refuses whatever the code: nothing is counted."""
    user = make_user()
    c = _session(app, user)
    with app.app_context():
        db.session.add(SystemConfig(key='enforce_2fa', value='true'))
        db.session.commit()
    for field in ('code', 'backup_code'):
        for _ in range(_max_attempts(app) + 1):
            r = _post(c, '/api/v2/account/2fa/disable', {field: '00000000'})
            assert r.status_code == 403, r.data
    assert _failures(user['id']) == 0
    assert _totp_on(app, user)


@pytest.mark.parametrize('route', sorted(ROUTES))
def test_a_check_without_2fa_enabled_uses_no_attempt(app, make_user, route):
    """A key-only account shares the counter: a TOTP route it cannot pass counts nothing."""
    user = make_user(totp=False, key=True)
    url, field = ROUTES[route]
    c = _session(app, user)
    for _ in range(_max_attempts(app) + 1):
        assert _reply(_post(c, url, {field: '00000000'})) == (400, '2FA not enabled')
    assert _failures(user['id']) == 0


def test_a_code_checked_against_an_unconfirmed_secret_uses_no_attempt(app, make_user):
    """A TOTP enrolment not confirmed yet is no factor of the login: its codes are not counted,
    so a key-only account cannot lock its own security-key login with them."""
    user = make_user(totp=False, key=True)
    c = _session(app, user)
    assert _post(c, '/api/v2/account/2fa/enable', {}).status_code == 200
    for _ in range(_max_attempts(app) + 1):
        assert _reply(_post(c, '/api/v2/account/2fa/disable', {'code': '00000000'})) == (
            400, 'Invalid verification code')
    assert _failures(user['id']) == 0
