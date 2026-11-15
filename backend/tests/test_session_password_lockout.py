"""A password checked again inside an open session is bounded per account.

NIST SP 800-63B-4 §3.2.2: failed attempts are limited per authenticator. Every
route that compares the password of a caller already signed in counts its failures
in the database, apart from the login's counter, with the second factor's threshold
and duration; once locked, even the right password gets 429 until the lock expires.
"""
import os
import threading
import uuid
from datetime import timedelta

import pytest

from models import AuditLog, User, db
from models.second_factor_failure import SecondFactorFailure
from tests.fresh_app import fresh_app
from tests.test_backup_cross_installation import _bound_to
from tests.test_second_factor_failures import LOCKED, _database
from utils.datetime_utils import utc_now

_PG_URL = os.environ.get('UCM_TEST_PG_URL')
PASSWORD = 'Sess10n-Rever1fy-Pass!'
NEW_PASSWORD = 'Sess10n-Rever1fy-New-42!'
KIND = 'session_pw'


def _account_password(c, uid, password):
    return c.post('/api/v2/account/password',
                  json={'current_password': password, 'new_password': NEW_PASSWORD})


def _users_update(c, uid, password):
    return c.put(f'/api/v2/users/{uid}',
                 json={'password': NEW_PASSWORD, 'current_password': password})


def _users_reset(c, uid, password):
    return c.post(f'/api/v2/users/{uid}/reset-password',
                  json={'new_password': NEW_PASSWORD, 'current_password': password})


def _key_second_factor_off(c, uid, password):
    return c.put('/api/v2/account/2fa/webauthn', json={'enabled': False, 'password': password})


# Every route found to compare the password of a caller already authenticated: route, wrong-password code
ROUTES = {
    'account-password': (_account_password, 403),
    'users-update': (_users_update, 400),
    'users-reset-password': (_users_reset, 400),
    'key-second-factor-off': (_key_second_factor_off, 403),
}


@pytest.fixture(params=[
    'sqlite',
    pytest.param('postgresql', marks=[
        pytest.mark.postgres,
        pytest.mark.skipif(not _PG_URL, reason='UCM_TEST_PG_URL not set')]),
])
def nodes(app, request, tmp_path):
    """(node A, node B, user): two applications on one database, an admin without 2FA."""
    pg = request.param == 'postgresql'
    with _database(request.param, tmp_path) as url, _bound_to(app, url, is_postgresql=pg), \
            fresh_app() as other, _bound_to(other, url, is_postgresql=pg, create_schema=False):
        with app.app_context():
            user = User(username=f'reverify-{uuid.uuid4().hex[:8]}', role='admin',
                        email=f'{uuid.uuid4().hex[:8]}@example.test', webauthn_2fa=True)
            user.set_password(PASSWORD)
            db.session.add(user)
            db.session.commit()
            info = {'id': user.id, 'username': user.username, 'pg': pg}
            db.session.remove()
        yield app, other, info


def _session(application, user):
    c = application.test_client()
    r = c.post('/api/v2/auth/login/password',
               json={'username': user['username'], 'password': PASSWORD})
    assert r.status_code == 200, r.data
    assert 'requires_2fa' not in (r.get_json().get('data') or {}), r.data
    return c


def _settings(application):
    from api.v2.auth_methods import _get_2fa_lockout_settings
    with application.app_context():
        settings = _get_2fa_lockout_settings()
        db.session.remove()
        return settings


def _row(application, user):
    with application.app_context():
        row = db.session.get(SecondFactorFailure, (KIND, str(user['id'])))
        found = (row.failures, row.locked_until) if row else None
        db.session.remove()
        return found


def _account(application, user):
    with application.app_context():
        u = db.session.get(User, user['id'])
        state = {'failed_logins': u.failed_logins or 0, 'locked_until': u.locked_until,
                 'password_kept': u.check_password(PASSWORD)}
        db.session.remove()
        return state


def _locks_audited(application, user):
    with application.app_context():
        n = AuditLog.query.filter_by(action='session_password_locked',
                                     resource_id=str(user['id'])).count()
        db.session.remove()
        return n


def _reply(r):
    return r.status_code, (r.get_json() or {}).get('message')


@pytest.mark.parametrize('route', sorted(ROUTES))
def test_wrong_passwords_lock_and_then_the_right_one_is_refused(nodes, route):
    a, b, user = nodes
    call, wrong = ROUTES[route]
    max_attempts, duration = _settings(a)
    c = _session(a, user)
    for n in range(1, max_attempts + 1):
        assert call(c, user['id'], f'Wrong-{n}-Password!').status_code == wrong
        assert _row(b, user)[0] == n
    r = call(c, user['id'], 'Wrong-again-Password!')
    assert _reply(r) == LOCKED
    assert 0 < int(r.headers['Retry-After']) <= duration
    r = call(c, user['id'], PASSWORD)
    assert _reply(r) == LOCKED
    # Seen from the other node too, and the login's own counter is untouched
    assert _reply(call(_session(b, user), user['id'], PASSWORD)) == LOCKED
    assert _account(a, user) == {'failed_logins': 0, 'locked_until': None, 'password_kept': True}
    assert _locks_audited(b, user) == 1


@pytest.mark.parametrize('route', sorted(ROUTES))
def test_the_lock_ends_with_its_duration(nodes, route, monkeypatch):
    a, _b, user = nodes
    call, wrong = ROUTES[route]
    max_attempts, duration = _settings(a)
    c = _session(a, user)
    for _ in range(max_attempts):
        assert call(c, user['id'], 'Wrong-Password-1!').status_code == wrong
    assert _reply(call(c, user['id'], PASSWORD)) == LOCKED
    later = utc_now() + timedelta(seconds=duration + 1)
    monkeypatch.setattr('api.v2.auth_methods.utc_now', lambda: later)
    r = call(c, user['id'], PASSWORD)
    assert r.status_code == 200, r.data
    assert _row(a, user) is None


@pytest.mark.parametrize('route', sorted(ROUTES))
def test_a_right_password_before_the_cap_clears_the_counter(nodes, route):
    a, _b, user = nodes
    call, wrong = ROUTES[route]
    max_attempts, _ = _settings(a)
    c = _session(a, user)
    for _ in range(max_attempts - 1):
        assert call(c, user['id'], 'Wrong-Password-1!').status_code == wrong
    r = call(c, user['id'], PASSWORD)
    assert r.status_code == 200, r.data
    assert _row(a, user) is None
    for _ in range(max_attempts - 1):
        assert call(c, user['id'], 'Wrong-Password-2!').status_code == wrong


def test_the_login_still_opens_while_session_checks_are_locked(nodes):
    a, b, user = nodes
    max_attempts, _ = _settings(a)
    c = _session(a, user)
    for _ in range(max_attempts + 1):
        _account_password(c, user['id'], 'Wrong-Password-1!')
    assert _reply(_account_password(c, user['id'], PASSWORD)) == LOCKED
    _session(b, user)


@pytest.mark.parametrize('route', sorted(ROUTES))
def test_two_requests_at_the_last_attempt_count_once(nodes, route):
    a, b, user = nodes
    call, wrong = ROUTES[route]
    max_attempts, _ = _settings(a)
    clients = [_session(a, user), _session(b, user)]
    with a.app_context():
        db.session.merge(SecondFactorFailure(kind=KIND, target=str(user['id']),
                                             failures=max_attempts - 1, updated_at=utc_now()))
        db.session.commit()
        db.session.remove()
    barrier = threading.Barrier(2)
    codes = []

    def attempt(client):
        barrier.wait(10)
        codes.append(call(client, user['id'], 'Wrong-Password-9!').status_code)

    threads = [threading.Thread(target=attempt, args=(client,)) for client in clients]
    for t in threads:
        t.start()
    for t in threads:
        t.join(60)
    assert sorted(codes) == sorted([wrong, 429]), codes
    assert _row(a, user)[0] == max_attempts
    assert _locks_audited(a, user) == 1
