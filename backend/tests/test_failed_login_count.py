"""A login attempt is counted before its password is checked, so a burst of requests on any
number of nodes checks at most ``max_login_attempts`` passwords before the lockout.

A burst is forced here by a password check that sends the next request of the burst while
it is still running, as a second node would; the threaded race is at the end of the file."""
import logging
import os
import threading
import time
import uuid
from datetime import timedelta

import pytest
from sqlalchemy import event, select

from models import SSOProvider, User, db
from utils.datetime_utils import utc_now

_PG_URL = os.environ.get('UCM_TEST_PG_URL')
PASSWORD = 'Counted-Passw0rd!'
TABLE = User.__table__
MAX_ATTEMPTS = 5
BURST = MAX_ATTEMPTS + 3
PASSWORD_DOOR = '/api/v2/auth/login/password'
LDAP_DOOR = '/api/v2/sso/ldap/login'


@pytest.fixture(autouse=True)
def five_attempts(app):
    """Pin the lockout threshold: other files in the same database may change it."""
    from models import SystemConfig
    with app.app_context():
        row = SystemConfig.query.filter_by(key='max_login_attempts').first()
        saved = row.value if row else None
        if row is None:
            row = SystemConfig(key='max_login_attempts')
            db.session.add(row)
        row.value = str(MAX_ATTEMPTS)
        db.session.commit()
    yield
    with app.app_context():
        row = SystemConfig.query.filter_by(key='max_login_attempts').first()
        if saved is None:
            db.session.delete(row)
        else:
            row.value = saved
        db.session.commit()


def _new_user(name, **columns):
    user = User(username=name, email=f'{name}@example.test', role='viewer', **columns)
    user.set_password(PASSWORD)
    db.session.add(user)
    db.session.commit()


@pytest.fixture
def username(app):
    name = f'cnt{uuid.uuid4().hex[:8]}'
    with app.app_context():
        _new_user(name)
    yield name
    with app.app_context():
        User.query.filter_by(username=name).delete(synchronize_session=False)
        db.session.commit()


@pytest.fixture
def ldap_provider(app):
    with app.app_context():
        provider = SSOProvider(
            name=f'cnt-ldap-{uuid.uuid4().hex[:6]}', provider_type='ldap', enabled=True,
            ldap_server='ldap.example.test', ldap_port=389, ldap_base_dn='dc=example,dc=test',
            ldap_user_filter='(uid={username})', ldap_username_attr='uid',
        )
        db.session.add(provider)
        db.session.commit()
        provider_id = provider.id
    yield provider_id
    with app.app_context():
        from models.sso import SSOSession
        SSOSession.query.filter_by(provider_id=provider_id).delete()
        db.session.delete(db.session.get(SSOProvider, provider_id))
        db.session.commit()


@pytest.fixture
def ldap_user(app, username, ldap_provider):
    """``username`` as an account of the LDAP provider, so a bind opens it."""
    with app.app_context():
        User.query.filter_by(username=username).update(
            {'auth_source': 'ldap', 'sso_provider_id': ldap_provider})
        db.session.commit()
    return username


@pytest.fixture
def alerts(monkeypatch):
    import api.v2.sso.helpers as helpers
    sent = []
    monkeypatch.setattr(helpers, 'notify_account_locked', sent.append)
    return sent


def _another_node_writes(name, **columns):
    with db.engine.begin() as conn:
        conn.execute(TABLE.update().where(TABLE.c.username == name).values(**columns))


def _stored(name):
    with db.engine.connect() as conn:
        return conn.execute(select(TABLE.c.failed_logins, TABLE.c.locked_until)
                            .where(TABLE.c.username == name)).one()


def _ldap_body(name, provider_id, password='wrong'):
    return {'username': name, 'password': password, 'provider_id': provider_id}


def _bind_result(name):
    return {'dn': f'uid={name}', 'uid': name, 'username': name,
            'email': f'{name}@example.test', 'fullname': name, 'groups': []}


def _found(name, before_bind):
    """The directory found ``name``: the door's hook runs before the user's bind, as the
    real search does; False when it refused the attempt."""
    if before_bind is None:
        return True
    return before_bind({k: v for k, v in _bind_result(name).items() if k != 'groups'})


def _lock_lines(caplog, name):
    return [r for r in caplog.records if 'locked after' in r.getMessage() and name in r.getMessage()]


# --- Password door ---------------------------------------------------------------

def test_a_burst_checks_at_most_max_attempts_passwords(app, client, username, alerts,
                                                       monkeypatch, caplog):
    checked = []

    def the_next_request_arrives_meanwhile(self, password):
        checked.append(password)
        if len(checked) < BURST:
            with app.app_context():
                assert client.post(PASSWORD_DOOR, json={'username': username,
                                                        'password': 'wrong'}).status_code == 401
        return False

    monkeypatch.setattr(User, 'check_password', the_next_request_arrives_meanwhile)
    with caplog.at_level(logging.WARNING):
        response = client.post(PASSWORD_DOOR, json={'username': username, 'password': 'wrong'})
    assert response.status_code == 401
    assert len(checked) == MAX_ATTEMPTS
    with app.app_context():
        failures, locked_until = _stored(username)
    assert failures == MAX_ATTEMPTS and locked_until is not None
    assert alerts == [username]
    assert len(_lock_lines(caplog, username)) == 1


def test_a_locked_account_refuses_the_right_password_unchecked(app, client, username,
                                                              monkeypatch):
    with app.app_context():
        _another_node_writes(username, failed_logins=MAX_ATTEMPTS,
                             locked_until=utc_now() + timedelta(minutes=15))
    checked = []
    real = User.check_password
    monkeypatch.setattr(User, 'check_password',
                        lambda self, pw: checked.append(pw) or real(self, pw))
    response = client.post(PASSWORD_DOOR, json={'username': username, 'password': PASSWORD})
    assert (response.status_code, response.get_json()['message']) == (401, 'Invalid credentials')
    assert checked == []


def test_a_count_past_a_lowered_threshold_locks_unchecked(app, client, username, monkeypatch):
    """Counted under a higher max_login_attempts and never locked: the next attempt locks."""
    with app.app_context():
        _another_node_writes(username, failed_logins=MAX_ATTEMPTS + 2)
    checked = []
    monkeypatch.setattr(User, 'check_password', lambda self, pw: checked.append(pw) or True)
    response = client.post(PASSWORD_DOOR, json={'username': username, 'password': PASSWORD})
    assert response.status_code == 401 and checked == []
    with app.app_context():
        assert _stored(username)[1] is not None


def test_a_lock_armed_past_a_lowered_threshold_is_alerted_once(app, client, username,
                                                                alerts, caplog):
    with app.app_context():
        _another_node_writes(username, failed_logins=MAX_ATTEMPTS + 2)
    with caplog.at_level(logging.WARNING):
        for _ in range(3):
            assert client.post(PASSWORD_DOOR, json={'username': username, 'password': 'wrong'}
                               ).status_code == 401
    assert alerts == [username]
    assert len(_lock_lines(caplog, username)) == 1


def test_an_expired_lock_restarts_the_count(app, client, username):
    with app.app_context():
        _another_node_writes(username, failed_logins=MAX_ATTEMPTS,
                             locked_until=utc_now() - timedelta(seconds=1))
    response = client.post(PASSWORD_DOOR, json={'username': username, 'password': 'wrong'})
    assert response.status_code == 401
    with app.app_context():
        assert tuple(_stored(username)) == (1, None)


def test_the_right_password_admitted_before_another_node_locked_clears_it(
        app, client, username, monkeypatch):
    """Its attempt was counted within the threshold: a success resets the stored row."""
    real = User.check_password

    def another_node_locks_meanwhile(self, password):
        _another_node_writes(self.username, failed_logins=MAX_ATTEMPTS,
                             locked_until=utc_now() + timedelta(minutes=15))
        return real(self, password)

    monkeypatch.setattr(User, 'check_password', another_node_locks_meanwhile)
    response = client.post(PASSWORD_DOOR, json={'username': username, 'password': PASSWORD})
    assert response.status_code == 200
    with app.app_context():
        assert tuple(_stored(username)) == (0, None)


def test_a_success_resets_the_stored_count_not_its_copy(app, client, username, monkeypatch):
    real = User.check_password

    def another_node_fails_meanwhile(self, password):
        _another_node_writes(self.username, failed_logins=3)
        return real(self, password)

    monkeypatch.setattr(User, 'check_password', another_node_fails_meanwhile)
    response = client.post(PASSWORD_DOOR, json={'username': username, 'password': PASSWORD})
    assert response.status_code == 200
    with app.app_context():
        assert tuple(_stored(username)) == (0, None)


def _refuse_the_count(engine):
    def refuse(conn, cursor, statement, *args):
        if statement.lstrip().upper().startswith('UPDATE USERS SET FAILED_LOGINS'):
            raise RuntimeError('database unavailable')
    event.listen(engine, 'before_cursor_execute', refuse)
    return lambda: event.remove(engine, 'before_cursor_execute', refuse)


def test_a_count_that_cannot_be_stored_answers_500_unchecked(app, client, username,
                                                             monkeypatch):
    checked = []
    monkeypatch.setattr(User, 'check_password', lambda self, pw: checked.append(pw) or True)
    with app.app_context():
        restore = _refuse_the_count(db.engine)
    try:
        response = client.post(PASSWORD_DOOR, json={'username': username, 'password': PASSWORD})
    finally:
        restore()
    assert (response.status_code, response.get_json()['message']) == \
        (500, 'Failed to record login attempt')
    assert checked == []


def test_the_count_holds_on_a_database_without_update_returning(app, client, username,
                                                                 monkeypatch, alerts):
    """SQLite before 3.35: the rank is read back under the write lock."""
    def refuse_returning(conn, cursor, statement, *args):
        if 'RETURNING' in statement.upper():
            raise RuntimeError('RETURNING is not available on this database')

    with app.app_context():
        engine = db.engine
    monkeypatch.setattr(engine.dialect, 'update_returning', False)
    event.listen(engine, 'before_cursor_execute', refuse_returning)
    try:
        codes = [client.post(PASSWORD_DOOR, json={'username': username, 'password': 'wrong'}
                             ).status_code for _ in range(MAX_ATTEMPTS + 1)]
        with app.app_context():
            stored = tuple(_stored(username))
        right = client.post(PASSWORD_DOOR, json={'username': username, 'password': PASSWORD})
    finally:
        event.remove(engine, 'before_cursor_execute', refuse_returning)
    assert codes == [401] * (MAX_ATTEMPTS + 1)
    assert stored[0] == MAX_ATTEMPTS and stored[1] is not None
    assert right.status_code == 401 and alerts == [username]


def _refuse_the_reset(engine):
    """Refuse the success's reset of the count, and only it."""
    def refuse(conn, cursor, statement, parameters, *args):
        if statement.lstrip().upper().startswith('UPDATE USERS SET FAILED_LOGINS') \
                and 'LOCKED_UNTIL' in statement.upper() and 'CASE' not in statement.upper():
            raise RuntimeError('database unavailable')
    event.listen(engine, 'before_cursor_execute', refuse)
    return lambda: event.remove(engine, 'before_cursor_execute', refuse)


def test_a_reset_that_cannot_be_stored_answers_500_without_a_session(app, client, username):
    with app.app_context():
        restore = _refuse_the_reset(db.engine)
    try:
        response = client.post(PASSWORD_DOOR, json={'username': username, 'password': PASSWORD})
        me = client.get('/api/v2/auth/verify').get_json()['data']
    finally:
        restore()
    assert (response.status_code, response.get_json()['message']) == \
        (500, 'Failed to update login stats')
    assert not me.get('authenticated')


# --- LDAP door -------------------------------------------------------------------

def test_an_ldap_burst_binds_at_most_max_attempts_times(app, client, username, ldap_provider,
                                                        alerts, monkeypatch, caplog):
    import api.v2.sso.ldap_routes as ldap_routes
    binds = []

    def the_next_request_arrives_meanwhile(provider, name, password, before_bind=None):
        if not _found(name, before_bind):
            return None, 'attempt_refused'
        binds.append(password)
        if len(binds) < BURST:
            with app.app_context():
                assert client.post(LDAP_DOOR, json=_ldap_body(name, ldap_provider)
                                   ).status_code == 401
        return None, 'Invalid credentials'

    monkeypatch.setattr(ldap_routes, '_ldap_authenticate_user', the_next_request_arrives_meanwhile)
    with caplog.at_level(logging.WARNING):
        response = client.post(LDAP_DOOR, json=_ldap_body(username, ldap_provider))
    assert response.status_code == 401
    assert len(binds) == MAX_ATTEMPTS
    with app.app_context():
        failures, locked_until = _stored(username)
    assert failures == MAX_ATTEMPTS and locked_until is not None
    assert alerts == [username]
    assert len(_lock_lines(caplog, username)) == 1


def test_an_ldap_bind_admitted_before_another_node_locked_clears_it(
        app, client, ldap_user, ldap_provider, monkeypatch):
    import api.v2.sso.ldap_routes as ldap_routes

    def another_node_locks_meanwhile(provider, name, password, before_bind=None):
        assert _found(name, before_bind)
        _another_node_writes(name, failed_logins=MAX_ATTEMPTS,
                             locked_until=utc_now() + timedelta(minutes=15))
        return _bind_result(name), None

    monkeypatch.setattr(ldap_routes, '_ldap_authenticate_user', another_node_locks_meanwhile)
    response = client.post(LDAP_DOOR, json=_ldap_body(ldap_user, ldap_provider, PASSWORD))
    assert response.status_code == 200
    with app.app_context():
        assert tuple(_stored(ldap_user)) == (0, None)


def test_an_ldap_lock_armed_past_a_lowered_threshold_is_alerted_once(
        app, client, ldap_user, ldap_provider, alerts, monkeypatch, caplog):
    import api.v2.sso.ldap_routes as ldap_routes
    binds = []
    monkeypatch.setattr(ldap_routes, '_ldap_authenticate_user',
                        _case_blind_directory(binds, ldap_user))
    with app.app_context():
        _another_node_writes(ldap_user, failed_logins=MAX_ATTEMPTS + 2)
    with caplog.at_level(logging.WARNING):
        for _ in range(3):
            assert client.post(LDAP_DOOR, json=_ldap_body(ldap_user, ldap_provider)
                               ).status_code == 401
    assert binds == [] and alerts == [ldap_user]
    assert len(_lock_lines(caplog, ldap_user)) == 1


@pytest.mark.parametrize('reason', ['account_disabled', 'group_denied'])
def test_a_proved_ldap_password_refused_for_another_reason_does_not_count(
        app, client, username, ldap_provider, monkeypatch, reason):
    import api.v2.sso.ldap_routes as ldap_routes
    with app.app_context():
        _another_node_writes(username, failed_logins=MAX_ATTEMPTS - 1)
    monkeypatch.setattr(ldap_routes, '_ldap_authenticate_user', lambda p, n, pw, before_bind=None: (_found(n, before_bind), (None, reason))[1])
    assert client.post(LDAP_DOOR, json=_ldap_body(username, ldap_provider)).status_code == 403
    with app.app_context():
        assert tuple(_stored(username)) == (MAX_ATTEMPTS - 1, None)


def test_a_proved_ldap_password_leaves_the_lock_another_attempt_armed(
        app, client, username, ldap_provider, alerts, monkeypatch):
    """Released while wrong passwords locked the account: the lock stays, so no more
    than max_login_attempts binds are made in all."""
    import api.v2.sso.ldap_routes as ldap_routes
    binds = []

    def group_denied_while_a_burst_locks(provider, name, password, before_bind=None):
        if not _found(name, before_bind):
            return None, 'attempt_refused'
        binds.append(password)
        if password != PASSWORD:
            return None, 'Invalid credentials'
        with app.app_context():
            for _ in range(MAX_ATTEMPTS - 1):
                assert client.post(LDAP_DOOR, json=_ldap_body(name, ldap_provider)
                                   ).status_code == 401
        return None, 'group_denied'

    monkeypatch.setattr(ldap_routes, '_ldap_authenticate_user', group_denied_while_a_burst_locks)
    assert client.post(LDAP_DOOR, json=_ldap_body(username, ldap_provider, PASSWORD)
                       ).status_code == 403
    assert client.post(LDAP_DOOR, json=_ldap_body(username, ldap_provider)).status_code == 401
    assert len(binds) == MAX_ATTEMPTS and alerts == [username]
    with app.app_context():
        assert _stored(username)[1] is not None


def test_a_locally_disabled_ldap_account_does_not_count(app, client, ldap_user, ldap_provider,
                                                        monkeypatch):
    import api.v2.sso.ldap_routes as ldap_routes
    with app.app_context():
        _another_node_writes(ldap_user, active=False, failed_logins=2)
    monkeypatch.setattr(ldap_routes, '_ldap_authenticate_user',
                        lambda p, n, pw, before_bind=None:
                        (_found(n, before_bind), (_bind_result(n), None))[1])
    assert client.post(LDAP_DOOR, json=_ldap_body(ldap_user, ldap_provider)).status_code == 403
    with app.app_context():
        assert tuple(_stored(ldap_user)) == (2, None)


def _case_blind_directory(binds, stored_name):
    """A directory whose name match ignores case (uid, sAMAccountName) and returns its own."""
    def bind(provider, name, password, before_bind=None):
        if name.lower() == stored_name.lower() and not _found(stored_name, before_bind):
            return None, 'attempt_refused'
        binds.append(name)
        if name.lower() != stored_name.lower() or password != PASSWORD:
            return None, 'Invalid credentials'
        return _bind_result(stored_name), None
    return bind


def test_an_ldap_name_in_another_case_is_counted_on_the_same_account(
        app, client, ldap_user, ldap_provider, monkeypatch):
    import api.v2.sso.ldap_routes as ldap_routes
    binds = []
    monkeypatch.setattr(ldap_routes, '_ldap_authenticate_user',
                        _case_blind_directory(binds, ldap_user))
    for _ in range(BURST * 2):
        assert client.post(LDAP_DOOR, json=_ldap_body(ldap_user.upper(), ldap_provider)
                           ).status_code == 401
    assert len(binds) == MAX_ATTEMPTS
    response = client.post(LDAP_DOOR, json=_ldap_body(ldap_user.upper(), ldap_provider, PASSWORD))
    assert response.status_code == 401
    assert len(binds) == MAX_ATTEMPTS
    with app.app_context():
        failures, locked_until = _stored(ldap_user)
    assert failures == MAX_ATTEMPTS and locked_until is not None


def test_an_ldap_success_in_another_case_clears_the_account(
        app, client, ldap_user, ldap_provider, monkeypatch):
    import api.v2.sso.ldap_routes as ldap_routes
    with app.app_context():
        _another_node_writes(ldap_user, failed_logins=MAX_ATTEMPTS - 2)
    monkeypatch.setattr(ldap_routes, '_ldap_authenticate_user',
                        _case_blind_directory([], ldap_user))
    response = client.post(LDAP_DOOR, json=_ldap_body(ldap_user.upper(), ldap_provider, PASSWORD))
    assert response.status_code == 200
    with app.app_context():
        assert tuple(_stored(ldap_user)) == (0, None)


def test_an_ldap_count_that_cannot_be_stored_answers_500_unbound(app, client, username,
                                                                ldap_provider, monkeypatch):
    import api.v2.sso.ldap_routes as ldap_routes
    binds = []
    monkeypatch.setattr(ldap_routes, '_ldap_authenticate_user',
                        lambda p, n, pw, before_bind=None: (_found(n, before_bind) and binds.append(pw)) or (None, 'Invalid credentials'))
    with app.app_context():
        restore = _refuse_the_count(db.engine)
    try:
        response = client.post(LDAP_DOOR, json=_ldap_body(username, ldap_provider))
    finally:
        restore()
    assert (response.status_code, response.get_json()['message']) == \
        (500, 'Failed to record login attempt')
    assert binds == []


def test_an_ldap_reset_that_cannot_be_stored_answers_500_without_a_session(
        app, client, ldap_user, ldap_provider, monkeypatch):
    import api.v2.sso.ldap_routes as ldap_routes
    from models.sso import SSOSession
    monkeypatch.setattr(ldap_routes, '_ldap_authenticate_user',
                        _case_blind_directory([], ldap_user))
    with app.app_context():
        restore = _refuse_the_reset(db.engine)
    try:
        response = client.post(LDAP_DOOR, json=_ldap_body(ldap_user, ldap_provider, PASSWORD))
        me = client.get('/api/v2/auth/verify').get_json()['data']
    finally:
        restore()
    assert (response.status_code, response.get_json()['message']) == \
        (500, 'Failed to update login stats')
    assert not me.get('authenticated')
    with app.app_context():
        assert SSOSession.query.filter_by(provider_id=ldap_provider).count() == 0
        assert _stored(ldap_user)[0] == 1


# --- Threads on one database -----------------------------------------------------

WORKERS = 8


def _wrong_passwords_together(app, monkeypatch, alerts):
    """WORKERS wrong passwords sent at once, each password check held long enough
    for every other request to reach its own lockout check."""
    name = f'race{uuid.uuid4().hex[:8]}'
    with app.app_context():
        _new_user(name)
        db.session.remove()
    checked, errors, start = [], [], threading.Barrier(WORKERS)

    def slow_wrong(self, password):
        checked.append(password)
        time.sleep(0.3)
        return False

    monkeypatch.setattr(User, 'check_password', slow_wrong)

    def worker():
        try:
            client = app.test_client()
            try:
                start.wait(10)
            except threading.BrokenBarrierError:
                pass
            status = client.post(PASSWORD_DOOR, json={'username': name,
                                                      'password': 'wrong'}).status_code
            if status != 401:
                errors.append(status)
        except Exception as exc:  # noqa: BLE001
            errors.append(repr(exc))

    threads = [threading.Thread(target=worker) for _ in range(WORKERS)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(60)
    with app.app_context():
        failures, locked_until = _stored(name)
        db.session.remove()
    assert errors == []
    assert len(checked) <= MAX_ATTEMPTS
    assert failures == MAX_ATTEMPTS and locked_until is not None
    assert alerts == [name]


def _pin_threshold():
    from models import SystemConfig
    with db.session.begin():
        db.session.add(SystemConfig(key='max_login_attempts', value=str(MAX_ATTEMPTS)))


def test_wrong_passwords_sent_together_lock_once_on_sqlite(app, tmp_path, monkeypatch, alerts):
    """A database file: the suite's in-memory one is a single connection threads cannot share."""
    from tests.test_backup_cross_installation import _bound_to
    with _bound_to(app, f"sqlite:///{tmp_path / 'login-race.db'}"):
        with app.app_context():
            _pin_threshold()
            db.session.remove()
        _wrong_passwords_together(app, monkeypatch, alerts)


@pytest.mark.postgres
@pytest.mark.skipif(not _PG_URL, reason='UCM_TEST_PG_URL not set')
def test_wrong_passwords_sent_together_lock_once_on_postgresql(app, monkeypatch, alerts):
    from tests.test_backup_cross_installation import _bound_to
    from tests.test_restore_reference_resolution_pg import _a_schema_of_our_own
    with _a_schema_of_our_own(f'login_race_{uuid.uuid4().hex[:6]}') as url, \
            _bound_to(app, url, is_postgresql=True):
        with app.app_context():
            _pin_threshold()
            db.session.remove()
        _wrong_passwords_together(app, monkeypatch, alerts)


# --- The directory decides whose account a name opens ----------------------------

class _AnySpellingDirectory:
    """A directory whose user filter accepts the uid or the mail of an entry and returns
    the stored uid: the attempt must be counted on that entry's account, whatever was typed."""

    def __init__(self, uid, mail, entry_uuid=None):
        self.uid, self.mail, self.entry_uuid, self.binds = uid, mail, entry_uuid, []

    def connection(self, server, user=None, password=None, **kwargs):
        directory = self

        class _Conn:
            def __init__(self):
                self.user, self.password, self.entries = user, password, []

            def search(self, base, query, attributes=None):
                if f'={directory.uid})' not in query and f'={directory.mail})' not in query:
                    return
                entry = type('Entry', (), {})()
                entry.entry_dn = f'uid={directory.uid},dc=example,dc=test'
                entry.uid, entry.mail, entry.cn = directory.uid, directory.mail, directory.uid
                entry.entryUUID = type('V', (), {'value': directory.entry_uuid})()
                self.entries = [entry]

            def unbind(self):
                return None
        return _Conn()

    def bind(self, conn, provider):
        if conn.user.startswith('cn=svc'):
            return True
        self.binds.append(conn.user)
        return conn.password == PASSWORD


@pytest.fixture
def any_spelling(app, ldap_provider, monkeypatch):
    """The real search and bind of the LDAP door, against _AnySpellingDirectory."""
    import ldap3
    import api.v2.sso.connection_tests as connection_tests
    with app.app_context():
        provider = db.session.get(SSOProvider, ldap_provider)
        provider.ldap_user_filter = '(|(uid={username})(mail={username}))'
        provider.ldap_bind_dn = 'cn=svc,dc=example,dc=test'
        provider.ldap_email_attr, provider.ldap_fullname_attr = 'mail', 'cn'
        db.session.commit()

    def install(directory):
        monkeypatch.setattr(ldap3, 'Server', lambda *a, **k: object())
        monkeypatch.setattr(ldap3, 'Connection', directory.connection)
        monkeypatch.setattr(connection_tests, 'ldap_bind', directory.bind)
        monkeypatch.setattr(connection_tests, '_build_ldap_tls', lambda provider: None)
        monkeypatch.setattr(connection_tests, '_decrypt_ldap_password', lambda provider: 'svc')
        monkeypatch.setattr(connection_tests, '_check_account_disabled', lambda *a: False)
        return directory
    return install


def test_an_ldap_name_the_filter_maps_to_an_entry_is_counted_on_its_account(
        app, client, ldap_user, ldap_provider, any_spelling, alerts):
    directory = any_spelling(_AnySpellingDirectory(ldap_user, f'{ldap_user}@example.test'))
    mail = directory.mail
    for _ in range(BURST * 2):
        assert client.post(LDAP_DOOR, json=_ldap_body(mail, ldap_provider)).status_code == 401
    assert len(directory.binds) == MAX_ATTEMPTS
    assert client.post(LDAP_DOOR, json=_ldap_body(mail, ldap_provider, PASSWORD)
                       ).status_code == 401
    assert len(directory.binds) == MAX_ATTEMPTS
    with app.app_context():
        failures, locked_until = _stored(ldap_user)
    assert failures == MAX_ATTEMPTS and locked_until is not None
    assert alerts == [ldap_user]


def test_an_ldap_success_under_another_spelling_clears_the_entry_account(
        app, client, ldap_user, ldap_provider, any_spelling):
    directory = any_spelling(_AnySpellingDirectory(ldap_user, f'{ldap_user}@example.test'))
    with app.app_context():
        _another_node_writes(ldap_user, failed_logins=MAX_ATTEMPTS - 1)
    response = client.post(LDAP_DOOR, json=_ldap_body(directory.mail, ldap_provider, PASSWORD))
    assert response.status_code == 200
    with app.app_context():
        assert tuple(_stored(ldap_user)) == (0, None)


def test_an_ldap_attempt_is_counted_on_the_account_bound_to_the_entry_id(
        app, client, username, ldap_provider, any_spelling):
    """Bound by its stable id, the account opens whatever its name now is."""
    entry_uid = f'dir{uuid.uuid4().hex[:8]}'
    directory = any_spelling(_AnySpellingDirectory(entry_uid, f'{entry_uid}@example.test',
                                                   entry_uuid=f'uuid-{entry_uid}'))
    with app.app_context():
        _another_node_writes(username, auth_source='ldap', sso_provider_id=ldap_provider,
                             sso_external_id=f'uuid-{entry_uid}')
    for _ in range(BURST):
        assert client.post(LDAP_DOOR, json=_ldap_body(entry_uid, ldap_provider)
                           ).status_code == 401
    assert len(directory.binds) == MAX_ATTEMPTS
    with app.app_context():
        failures, locked_until = _stored(username)
    assert failures == MAX_ATTEMPTS and locked_until is not None


def test_an_ldap_entry_named_like_a_local_account_is_counted_on_it(
        app, client, username, ldap_provider, any_spelling):
    """The bind of such an entry is refused 403 once proved: its guesses are bounded too."""
    directory = any_spelling(_AnySpellingDirectory(username, f'{username}@example.test'))
    for _ in range(BURST):
        assert client.post(LDAP_DOOR, json=_ldap_body(directory.mail, ldap_provider)
                           ).status_code == 401
    assert len(directory.binds) == MAX_ATTEMPTS
    assert client.post(LDAP_DOOR, json=_ldap_body(directory.mail, ldap_provider, PASSWORD)
                       ).status_code == 401
    assert len(directory.binds) == MAX_ATTEMPTS
