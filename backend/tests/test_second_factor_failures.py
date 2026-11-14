"""Second-factor and WebAuthn lockout counters live in the database, one row per target.

Two applications bound to one database stand for two nodes: what one counts or
locks, the other sees, and parallel attempts never get more tries than the
threshold. SQLite and PostgreSQL each get a database of their own with real
concurrent connections.
"""
import os
import threading
import uuid
from contextlib import contextmanager
from datetime import timedelta

import pyotp
import pytest

from models import SystemConfig, User, db
from models.second_factor_failure import SecondFactorFailure
from tests.fresh_app import fresh_app
from tests.test_backup_cross_installation import _bound_to
from tests.test_restore_reference_resolution_pg import _a_schema_of_our_own
from utils.datetime_utils import utc_now

_PG_URL = os.environ.get('UCM_TEST_PG_URL')
PASSWORD = 'Lock-Out-Counter-Pass1!'
WEBAUTHN_URL = '/api/v2/auth/login/webauthn/verify'
LOCKED = (429, 'Too many failed attempts. Try again later.')


@contextmanager
def _database(backend, tmp_path):
    if backend == 'sqlite':
        yield f"sqlite:///{tmp_path / 'lockout.db'}"
    else:
        worker = os.environ.get('PYTEST_XDIST_WORKER', 'main')
        with _a_schema_of_our_own(f'second_factor_failures_{worker}') as url:
            yield url


@pytest.fixture(params=[
    'sqlite',
    pytest.param('postgresql', marks=[
        pytest.mark.postgres,
        pytest.mark.skipif(not _PG_URL, reason='UCM_TEST_PG_URL not set')]),
])
def nodes(app, request, tmp_path):
    """(node A, node B, user): two applications on one database, a TOTP user in it."""
    pg = request.param == 'postgresql'
    with _database(request.param, tmp_path) as url, _bound_to(app, url, is_postgresql=pg), \
            fresh_app() as other, _bound_to(other, url, is_postgresql=pg, create_schema=False):
        with app.app_context():
            user = User(username=f'lockout-{uuid.uuid4().hex[:8]}', role='operator',
                        email=f'{uuid.uuid4().hex[:8]}@example.test',
                        totp_secret=pyotp.random_base32(), totp_confirmed=True)
            user.set_password(PASSWORD)
            db.session.add(user)
            db.session.commit()
            info = {'id': user.id, 'username': user.username, 'secret': user.totp_secret,
                    'url': url, 'pg': pg}
            db.session.remove()
        yield app, other, info


def _rows(application, kind=None):
    with application.app_context():
        query = SecondFactorFailure.query
        if kind:
            query = query.filter_by(kind=kind)
        rows = {(r.kind, r.target): (r.failures, r.locked_until) for r in query.all()}
        db.session.remove()
        return rows


def _webauthn(application, username):
    r = application.test_client().post(WEBAUTHN_URL, json={'username': username,
                                                          'response': {'id': 'not-a-key'}})
    return r.status_code, (r.get_json() or {}).get('message') or (r.get_json() or {}).get('error')


def _code(status_message):
    return status_message[0]


def _max_attempts(application):
    from api.v2.auth_methods import _get_2fa_lockout_settings
    with application.app_context():
        return _get_2fa_lockout_settings()


def _put(application, kind, target, failures, locked_until=None, updated_at=None):
    with application.app_context():
        db.session.merge(SecondFactorFailure(kind=kind, target=target, failures=failures,
                                             locked_until=locked_until,
                                             updated_at=updated_at or utc_now()))
        db.session.commit()
        db.session.remove()


# Invariant 1 and 3: one counter per target, in the database, honoured by every node


def test_failures_counted_on_a_lock_the_other_node(nodes):
    a, b, user = nodes
    max_attempts, duration = _max_attempts(a)
    for n in range(1, max_attempts + 1):
        assert _code(_webauthn(a if n % 2 else b, user['username'])) == 401
        failures, locked_until = _rows(a)[('webauthn', user['username'])]
        assert failures == n
        assert (locked_until is not None) == (n >= max_attempts)
    assert _webauthn(b, user['username']) == LOCKED
    assert _webauthn(a, user['username']) == LOCKED
    _, locked_until = _rows(b)[('webauthn', user['username'])]
    assert abs((locked_until - utc_now()).total_seconds() - duration) < 60


def test_a_lock_in_the_database_outlives_the_process_until_it_expires(nodes):
    """A row written by another process (or before a restart) is what decides."""
    a, b, user = nodes
    max_attempts, _ = _max_attempts(a)
    _put(a, 'webauthn', user['username'], max_attempts, utc_now() + timedelta(minutes=5))
    with fresh_app() as restarted, _bound_to(restarted, user['url'], is_postgresql=user['pg'],
                                             create_schema=False):
        assert _webauthn(restarted, user['username']) == LOCKED
    assert _webauthn(b, user['username']) == LOCKED

    _put(a, 'webauthn', user['username'], max_attempts, utc_now() - timedelta(seconds=1))
    assert _code(_webauthn(b, user['username'])) == 401
    assert _rows(a)[('webauthn', user['username'])] == (1, None)


def test_a_lock_set_by_one_node_holds_on_a_node_started_after_it(nodes):
    """Locks armed through the routes of A refuse on an application created afterwards."""
    from api.v2.auth_methods import TWO_FA, _check_2fa_lockout
    a, _b, user = nodes
    max_attempts, _ = _max_attempts(a)
    for _ in range(max_attempts):
        assert _code(_webauthn(a, user['username'])) == 401
    c = a.test_client()
    assert c.post('/api/v2/auth/login/password', json={'username': user['username'],
                                                       'password': PASSWORD}).status_code == 200
    for _ in range(max_attempts):
        assert c.post('/api/v2/auth/login/2fa', json={'code': '00000000'}).status_code == 401
    with fresh_app() as restarted, _bound_to(restarted, user['url'], is_postgresql=user['pg'],
                                             create_schema=False):
        assert _webauthn(restarted, user['username']) == LOCKED
        with restarted.app_context():
            assert _check_2fa_lockout(TWO_FA, str(user['id']))
            db.session.remove()


def test_a_pending_second_factor_is_refused_when_the_database_says_locked(nodes):
    a, b, user = nodes
    max_attempts, _ = _max_attempts(a)
    c = b.test_client()
    r = c.post('/api/v2/auth/login/password', json={'username': user['username'],
                                                    'password': PASSWORD})
    assert r.status_code == 200, r.data
    _put(a, '2fa', str(user['id']), max_attempts, utc_now() + timedelta(minutes=5))
    r = c.post('/api/v2/auth/login/2fa', json={'code': pyotp.TOTP(user['secret']).now()})
    assert (r.status_code, r.get_json()['message']) == LOCKED


# Invariant 2: no race, across two applications


@pytest.mark.parametrize('known', [True, False])
def test_parallel_attempts_on_two_nodes_never_exceed_the_threshold(nodes, known):
    a, b, user = nodes
    max_attempts, _ = _max_attempts(a)
    username = user['username'] if known else f'nobody-{uuid.uuid4().hex[:8]}'
    total = 4 * max_attempts
    barrier = threading.Barrier(total)
    results = []

    def attempt(application):
        client = application.test_client()
        barrier.wait(10)
        r = client.post(WEBAUTHN_URL, json={'username': username, 'response': {'id': 'x'}})
        results.append(r.status_code)

    threads = [threading.Thread(target=attempt, args=(a if i % 2 else b,)) for i in range(total)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(60)
    assert len(results) == total
    assert results.count(401) == max_attempts, results
    assert results.count(429) == total - max_attempts, results


def test_parallel_second_factor_reservations_never_exceed_the_threshold(nodes):
    from api.v2.auth_methods import TWO_FA, _reserve_2fa_attempt
    a, b, user = nodes
    max_attempts, _ = _max_attempts(a)
    total = 4 * max_attempts
    barrier = threading.Barrier(total)
    allowed = []

    def attempt(application):
        with application.app_context():
            barrier.wait(10)
            allowed.append(_reserve_2fa_attempt(TWO_FA, str(user['id'])))
            db.session.remove()

    threads = [threading.Thread(target=attempt, args=(a if i % 2 else b,)) for i in range(total)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(60)
    assert len(allowed) == total
    assert allowed.count(True) == max_attempts, allowed


# Invariant 4: same thresholds, messages, codes; a success clears; no new oracle


def test_unknown_and_known_names_lock_alike(nodes):
    a, b, user = nodes
    max_attempts, _ = _max_attempts(a)
    unknown = f'nobody-{uuid.uuid4().hex[:8]}'
    for _ in range(max_attempts):
        known_reply, unknown_reply = _webauthn(a, user['username']), _webauthn(b, unknown)
        assert known_reply == unknown_reply == (401, 'WebAuthn verification failed')
    assert _webauthn(b, user['username']) == _webauthn(a, unknown) == LOCKED


def test_a_success_clears_the_counter(nodes):
    a, b, user = nodes
    max_attempts, _ = _max_attempts(a)
    c = a.test_client()
    r = c.post('/api/v2/auth/login/password', json={'username': user['username'],
                                                    'password': PASSWORD})
    assert r.status_code == 200, r.data
    for _ in range(max_attempts - 1):
        r = c.post('/api/v2/auth/login/2fa', json={'code': '00000000'})
        assert (r.status_code, r.get_json()['message']) == (401, 'Invalid verification code')
    assert _rows(b)[('2fa', str(user['id']))][0] == max_attempts - 1
    r = c.post('/api/v2/auth/login/2fa', json={'code': pyotp.TOTP(user['secret']).now()})
    assert r.status_code == 200, r.data
    assert ('2fa', str(user['id'])) not in _rows(b)


def test_a_malformed_code_is_not_an_attempt(nodes):
    a, _b, user = nodes
    c = a.test_client()
    assert c.post('/api/v2/auth/login/password', json={'username': user['username'],
                                                       'password': PASSWORD}).status_code == 200
    assert c.post('/api/v2/auth/login/2fa', json={'code': '12'}).status_code == 400
    assert ('2fa', str(user['id'])) not in _rows(a)


@pytest.mark.parametrize('stored, applied', [('4', 4), ('0', 3), ('-2', 3)])
def test_the_configured_threshold_applies(nodes, stored, applied):
    """A stored value under the settings screen's minimum (3) reads as that minimum."""
    a, b, user = nodes
    with a.app_context():
        db.session.add(SystemConfig(key='max_login_attempts', value=stored))
        db.session.commit()
        db.session.remove()
    for n in range(applied):
        assert _code(_webauthn(a if n % 2 else b, user['username'])) == 401
    assert _webauthn(a, user['username']) == LOCKED


# Invariant 5: expired rows do not pile up


def test_expired_rows_are_purged_on_the_next_failure(nodes):
    a, b, user = nodes
    _, duration = _max_attempts(a)
    now = utc_now()
    _put(a, 'webauthn', 'expired-lock', 5, now - timedelta(seconds=1), now - timedelta(seconds=10))
    _put(a, 'webauthn', 'idle-count', 2, None, now - timedelta(seconds=duration + 5))
    _put(a, '2fa', 'live-lock', 5, now + timedelta(minutes=5), now - timedelta(seconds=duration + 5))
    _put(a, 'webauthn', 'recent-count', 2, None, now - timedelta(seconds=10))
    assert _code(_webauthn(b, user['username'])) == 401
    assert set(_rows(a)) == {('webauthn', user['username']), ('2fa', 'live-lock'),
                             ('webauthn', 'recent-count')}


# Backups: runtime state, never carried nor restored


@pytest.mark.parametrize('mode', ['replace', 'merge'])
def test_a_backup_neither_carries_nor_restores_a_lock(app, tmp_path, mode):
    """The rows are keyed by user id and name, which a restore may give to another
    account: the target's own locks go with the restore, in either mode."""
    from tests.test_backup_cross_installation import Keys, _installation
    from services.backup_service import BackupService
    password = 'Backup-Lock-Pass-2026!'
    locked = utc_now() + timedelta(minutes=10)
    with _installation(app, f"sqlite:///{tmp_path / 'source.db'}", Keys(tmp_path, 'source')), \
            app.app_context():
        owner = User(username='carried', role='admin', email='carried@example.test')
        owner.set_password(PASSWORD)
        db.session.add(owner)
        db.session.flush()
        db.session.add_all([SecondFactorFailure(kind=kind, target=target, failures=5,
                                                locked_until=locked, updated_at=utc_now())
                            for kind, target in (('webauthn', 'carried'), ('2fa', str(owner.id)))])
        db.session.commit()
        blob = BackupService().create_backup(password)
        _master, payload = BackupService()._decrypt_framed(blob, password)
        db.session.remove()
    assert 'second_factor_failures' not in payload and 'carried' in repr(payload)
    with _installation(app, f"sqlite:///{tmp_path / 'target.db'}", Keys(tmp_path, 'target')), \
            app.app_context():
        db.session.add_all([SecondFactorFailure(kind=kind, target=target, failures=5,
                                                locked_until=locked, updated_at=utc_now())
                            for kind, target in (('webauthn', 'target-user'), ('2fa', '1'))])
        db.session.commit()
        results = BackupService().restore_backup(blob, password, mode=mode)
        assert not results.get('errors'), results
        assert User.query.filter_by(username='carried').count() == 1
        assert SecondFactorFailure.query.count() == 0
        db.session.remove()


# SQLite before 3.35 (EL9 system library) has no INSERT ... RETURNING


def _refuse_returning(conn, cursor, statement, *args):
    if 'RETURNING' in statement.upper():
        raise RuntimeError('RETURNING is not available on this database')


@pytest.mark.parametrize('returning', [True, False])
def test_the_three_routes_count_alike_without_insert_returning(nodes, monkeypatch, returning):
    """TOTP, security key and passwordless WebAuthn give the same codes and counts
    whether or not the database supports INSERT ... RETURNING."""
    from sqlalchemy import event
    from api.v2.auth_methods import TWO_FA, _clear_2fa_failures
    a, _b, user = nodes
    max_attempts, _ = _max_attempts(a)
    with a.app_context():
        engine = db.engine
        db.session.remove()
    if not returning:
        monkeypatch.setattr(engine.dialect, 'insert_returning', False)
        event.listen(engine, 'before_cursor_execute', _refuse_returning)
    seen = []
    try:
        c = a.test_client()
        assert c.post('/api/v2/auth/login/password', json={
            'username': user['username'], 'password': PASSWORD}).status_code == 200
        for url, body in (('/api/v2/auth/login/2fa', {'code': '00000000'}),
                          ('/api/v2/auth/login/2fa/webauthn/verify', {'response': {'id': 'x'}})):
            for _ in range(max_attempts + 1):
                r = c.post(url, json=body)
                seen.append((r.status_code, _rows(a).get(('2fa', str(user['id'])), (0,))[0]))
            with a.app_context():
                _clear_2fa_failures(TWO_FA, str(user['id']))
                db.session.remove()
        for _ in range(max_attempts + 1):
            seen.append((_code(_webauthn(a, user['username'])),
                         _rows(a)[('webauthn', user['username'])][0]))
    finally:
        if not returning:
            event.remove(engine, 'before_cursor_execute', _refuse_returning)
    one_route = [(401, n) for n in range(1, max_attempts + 1)] + [(429, max_attempts)]
    assert seen == one_route * 3, seen
