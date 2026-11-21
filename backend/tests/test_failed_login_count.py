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
        from models import UserSSOIdentity
        UserSSOIdentity.query.filter_by(provider_id=provider_id).delete()
        db.session.delete(db.session.get(SSOProvider, provider_id))
        db.session.commit()


@pytest.fixture
def ldap_user(app, username, ldap_provider):
    """``username`` as an account of the LDAP provider, so a bind opens it."""
    with app.app_context():
        from tests.sso_identity_support import attach
        attach(username, ldap_provider)
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


def _signed_in(client):
    return bool(client.get('/api/v2/auth/verify').get_json()['data'].get('authenticated'))


def test_the_right_password_checked_while_a_burst_locks_opens_one_session_unlocked(
        app, client, username, alerts, monkeypatch):
    """Counted first, the right password is checked; the burst sent meanwhile on another
    connection checks the rest of the threshold and locks: the success clears that lock."""
    real, checked = User.check_password, []

    def a_burst_locks_meanwhile(self, password):
        checked.append(password)
        if password == PASSWORD:
            with app.app_context():
                other = app.test_client()
                for _ in range(BURST):
                    assert other.post(PASSWORD_DOOR, json={'username': username,
                                                           'password': 'wrong'}
                                      ).status_code == 401
                assert _stored(username)[1] is not None
        return real(self, password)

    monkeypatch.setattr(User, 'check_password', a_burst_locks_meanwhile)
    response = client.post(PASSWORD_DOOR, json={'username': username, 'password': PASSWORD})
    assert response.status_code == 200 and _signed_in(client)
    assert len(checked) == MAX_ATTEMPTS
    with app.app_context():
        assert tuple(_stored(username)) == (0, None)


def test_the_right_password_sent_once_a_burst_locked_opens_no_session(
        app, client, username, alerts, monkeypatch):
    real, checked, right = User.check_password, [], []

    def the_right_password_arrives_meanwhile(self, password):
        checked.append(password)
        if len(checked) < BURST:
            with app.app_context():
                other = app.test_client()
                if len(checked) == MAX_ATTEMPTS:
                    right.append(other.post(PASSWORD_DOOR, json={'username': username,
                                                                  'password': PASSWORD}))
                    right.append(_signed_in(other))
                else:
                    other.post(PASSWORD_DOOR, json={'username': username, 'password': 'wrong'})
        return real(self, password)

    monkeypatch.setattr(User, 'check_password', the_right_password_arrives_meanwhile)
    assert client.post(PASSWORD_DOOR, json={'username': username, 'password': 'wrong'}
                       ).status_code == 401
    assert right[0].status_code == 401 and right[1] is False
    assert len(checked) == MAX_ATTEMPTS and PASSWORD not in checked
    with app.app_context():
        failures, locked_until = _stored(username)
    assert failures == MAX_ATTEMPTS and locked_until is not None and alerts == [username]


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


def test_a_lock_armed_by_a_right_password_whose_reset_fails_is_alerted_once(
        app, client, username, alerts, caplog):
    """The lock stays, as the database left it: the alert says so."""
    with app.app_context():
        _another_node_writes(username, failed_logins=MAX_ATTEMPTS - 1)
        restore = _refuse_the_reset(db.engine)
    try:
        with caplog.at_level(logging.WARNING):
            response = client.post(PASSWORD_DOOR, json={'username': username,
                                                        'password': PASSWORD})
    finally:
        restore()
    assert response.status_code == 500
    assert alerts == [username] and len(_lock_lines(caplog, username)) == 1
    with app.app_context():
        assert _stored(username)[1] is not None


# --- Giving back a proved attempt -------------------------------------------------
# Only the attempt that armed the lock can show its window is still open: the lock it
# wrote is still the stored one. It then lifts that lock and gives its unit back.

def _reserved(name, before):
    _another_node_writes(name, failed_logins=before)
    user = User.query.filter_by(username=name).one()
    rank, armed = user.reserve_login_attempt(MAX_ATTEMPTS, 900)
    db.session.commit()
    return user, rank, armed


def test_a_release_lifts_the_lock_its_attempt_armed(app, username):
    with app.app_context():
        user, rank, armed = _reserved(username, MAX_ATTEMPTS - 1)
        assert rank == MAX_ATTEMPTS and armed
        user.release_login_attempt(armed)
        db.session.commit()
        assert tuple(_stored(username)) == (MAX_ATTEMPTS - 1, None)


def test_a_release_leaves_a_lock_armed_after_its_own(app, username):
    """Cleared by a right password, then locked again by a burst, while it was checked."""
    relock = utc_now() + timedelta(minutes=15)
    with app.app_context():
        user, _rank, armed = _reserved(username, MAX_ATTEMPTS - 1)
        _another_node_writes(username, failed_logins=MAX_ATTEMPTS, locked_until=relock)
        user.release_login_attempt(armed)
        db.session.commit()
        assert tuple(_stored(username)) == (MAX_ATTEMPTS, relock)


def test_a_release_after_its_lock_expired_and_the_count_restarted_gives_nothing(app, username):
    """A bind slower than lockout_duration: the count it took belongs to an ended window."""
    with app.app_context():
        user, _rank, armed = _reserved(username, MAX_ATTEMPTS - 1)
        _another_node_writes(username, failed_logins=1, locked_until=None)
        user.release_login_attempt(armed)
        db.session.commit()
        assert tuple(_stored(username)) == (1, None)


def test_a_release_after_its_own_lock_expired_gives_nothing(app, username):
    """A bind slower than lockout_duration, nothing counted since: the window has ended,
    and the next attempt restarts the count at 1 instead of arming a lock at once."""
    with app.app_context():
        _another_node_writes(username, failed_logins=MAX_ATTEMPTS - 1)
        user = User.query.filter_by(username=username).one()
        _rank, armed = user.reserve_login_attempt(MAX_ATTEMPTS, 0)
        db.session.commit()
        user.release_login_attempt(armed)
        db.session.commit()
        assert tuple(_stored(username)) == (MAX_ATTEMPTS, armed)
        assert user.reserve_login_attempt(MAX_ATTEMPTS, 900) == (1, None)
        db.session.rollback()


def test_a_release_of_an_attempt_that_armed_nothing_gives_nothing(app, username):
    """Cleared, then counted three times, while it was checked: its unit is not the new
    window's to give back."""
    with app.app_context():
        user, rank, armed = _reserved(username, 0)
        assert rank == 1 and not armed
        _another_node_writes(username, failed_logins=3)
        user.release_login_attempt(armed)
        db.session.commit()
        assert tuple(_stored(username)) == (3, None)


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


@pytest.mark.parametrize('reason', ['account_disabled', 'group_denied', 'groups_unreadable'])
def test_a_proved_ldap_password_refused_for_another_reason_never_locks(
        app, client, username, ldap_provider, monkeypatch, reason):
    """The attempt that armed the lock gives it back with its unit."""
    import api.v2.sso.ldap_routes as ldap_routes
    with app.app_context():
        _another_node_writes(username, failed_logins=MAX_ATTEMPTS - 1)
    monkeypatch.setattr(ldap_routes, '_ldap_authenticate_user', lambda p, n, pw, before_bind=None: (_found(n, before_bind), (None, reason))[1])
    for _ in range(3):
        assert client.post(LDAP_DOOR, json=_ldap_body(username, ldap_provider)).status_code == 403
    with app.app_context():
        assert tuple(_stored(username)) == (MAX_ATTEMPTS - 1, None)


@pytest.mark.parametrize('reason', ['account_disabled', 'group_denied', 'groups_unreadable'])
def test_a_proved_ldap_password_that_armed_nothing_stays_counted(
        app, client, username, ldap_provider, monkeypatch, reason):
    """Nothing stored tells its window from a later one, so its unit is not given back."""
    import api.v2.sso.ldap_routes as ldap_routes
    monkeypatch.setattr(ldap_routes, '_ldap_authenticate_user', lambda p, n, pw, before_bind=None: (_found(n, before_bind), (None, reason))[1])
    assert client.post(LDAP_DOOR, json=_ldap_body(username, ldap_provider)).status_code == 403
    with app.app_context():
        assert tuple(_stored(username)) == (1, None)


def test_a_proved_ldap_password_leaves_a_lock_armed_after_its_own(
        app, client, username, ldap_provider, monkeypatch):
    """It armed the lock; meanwhile a success cleared it and a burst armed another: that
    one stays, with its count, so the burst's binds stay within the threshold."""
    import api.v2.sso.ldap_routes as ldap_routes
    relock = utc_now() + timedelta(minutes=15)

    def cleared_and_locked_again_while_it_binds(provider, name, password, before_bind=None):
        assert _found(name, before_bind)
        assert _stored(name)[1] is not None
        _another_node_writes(name, failed_logins=MAX_ATTEMPTS, locked_until=relock)
        return None, 'group_denied'

    with app.app_context():
        _another_node_writes(username, failed_logins=MAX_ATTEMPTS - 1)
    monkeypatch.setattr(ldap_routes, '_ldap_authenticate_user',
                        cleared_and_locked_again_while_it_binds)
    assert client.post(LDAP_DOOR, json=_ldap_body(username, ldap_provider, PASSWORD)
                       ).status_code == 403
    with app.app_context():
        assert tuple(_stored(username)) == (MAX_ATTEMPTS, relock)


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


@pytest.mark.parametrize('before, after', [(2, 3), (MAX_ATTEMPTS - 1, MAX_ATTEMPTS - 1)],
                         ids=['armed-nothing', 'armed-the-lock'])
def test_a_locally_disabled_ldap_account_is_counted_but_never_locked_by_it(
        app, client, ldap_user, ldap_provider, monkeypatch, before, after):
    import api.v2.sso.ldap_routes as ldap_routes
    with app.app_context():
        _another_node_writes(ldap_user, active=False, failed_logins=before)
    monkeypatch.setattr(ldap_routes, '_ldap_authenticate_user',
                        lambda p, n, pw, before_bind=None:
                        (_found(n, before_bind), (_bind_result(n), None))[1])
    assert client.post(LDAP_DOOR, json=_ldap_body(ldap_user, ldap_provider)).status_code == 403
    with app.app_context():
        assert tuple(_stored(ldap_user)) == (after, None)


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


def test_an_ldap_lock_armed_by_a_right_password_whose_reset_fails_is_alerted_once(
        app, client, ldap_user, ldap_provider, alerts, monkeypatch, caplog):
    import api.v2.sso.ldap_routes as ldap_routes
    monkeypatch.setattr(ldap_routes, '_ldap_authenticate_user',
                        _case_blind_directory([], ldap_user))
    with app.app_context():
        _another_node_writes(ldap_user, failed_logins=MAX_ATTEMPTS - 1)
        restore = _refuse_the_reset(db.engine)
    try:
        with caplog.at_level(logging.WARNING):
            response = client.post(LDAP_DOOR, json=_ldap_body(ldap_user, ldap_provider, PASSWORD))
    finally:
        restore()
    assert response.status_code == 500
    assert alerts == [ldap_user] and len(_lock_lines(caplog, ldap_user)) == 1
    with app.app_context():
        assert _stored(ldap_user)[1] is not None


# --- Other authenticators ---------------------------------------------------------
# The count and the lock are the password's (NIST SP 800-63B rev. 4 §3.2.2): a client
# certificate or a passkey neither reads them nor resets them.

MTLS_DOOR = '/api/v2/auth/login/mtls'
PASSKEY_DOOR = '/api/v2/auth/login/webauthn/verify'


def _signs_in_by_certificate(monkeypatch, name, meanwhile=None):
    from types import SimpleNamespace
    from services.certificate_parser import CertificateParser
    from services.mtls_auth_service import MTLSAuthService

    def authenticate(cert_info):
        user = User.query.filter_by(username=name).one()
        if meanwhile:
            meanwhile()
        return user, SimpleNamespace(id=1, cert_serial='0a', name='client'), None
    monkeypatch.setattr(CertificateParser, 'extract_from_flask_native',
                        staticmethod(lambda peercert: {'serial': '0a'}))
    monkeypatch.setattr(MTLSAuthService, 'authenticate_certificate', staticmethod(authenticate))
    return lambda client: client.post(MTLS_DOOR, environ_base={'peercert': {'subject': ()}})


def _signs_in_by_passkey(monkeypatch, name, meanwhile=None):
    from services.webauthn_service import WebAuthnService

    def verify(user_id, response, host, **_kwargs):
        if meanwhile:
            meanwhile()
        return True, '', db.session.get(User, user_id)
    monkeypatch.setattr(WebAuthnService, 'verify_authentication', staticmethod(verify))
    return lambda client: client.post(PASSKEY_DOOR, json={'username': name,
                                                          'response': {'id': 'x'}})


_OTHER_DOORS = pytest.mark.parametrize('door', [_signs_in_by_certificate, _signs_in_by_passkey],
                                       ids=['certificate', 'passkey'])


@_OTHER_DOORS
def test_a_password_lock_does_not_stop_a_certificate_or_a_passkey(
        app, client, username, monkeypatch, door):
    """The session opens; the password's count and lock stay as they were."""
    until = utc_now() + timedelta(minutes=15)
    with app.app_context():
        _another_node_writes(username, failed_logins=MAX_ATTEMPTS, locked_until=until)
    assert door(monkeypatch, username)(client).status_code == 200
    with app.app_context():
        assert tuple(_stored(username)) == (MAX_ATTEMPTS, until)
    assert client.post(PASSWORD_DOOR, json={'username': username, 'password': PASSWORD}
                       ).status_code == 401


@_OTHER_DOORS
def test_a_certificate_or_a_passkey_gives_no_password_guess_back(
        app, client, username, monkeypatch, door):
    checked = []
    real = User.check_password
    with app.app_context():
        _another_node_writes(username, failed_logins=MAX_ATTEMPTS - 1)
    assert door(monkeypatch, username)(client).status_code == 200
    with app.app_context():
        assert tuple(_stored(username)) == (MAX_ATTEMPTS - 1, None)
    monkeypatch.setattr(User, 'check_password',
                        lambda self, pw: checked.append(pw) or real(self, pw))
    for _ in range(3):
        assert client.post(PASSWORD_DOOR, json={'username': username, 'password': 'wrong'}
                           ).status_code == 401
    assert len(checked) == 1


@_OTHER_DOORS
def test_a_certificate_or_a_passkey_keeps_a_count_written_while_it_checks(
        app, client, username, monkeypatch, door):
    meanwhile = lambda: _another_node_writes(username, failed_logins=MAX_ATTEMPTS - 1)
    assert door(monkeypatch, username, meanwhile)(client).status_code == 200
    with app.app_context():
        assert tuple(_stored(username)) == (MAX_ATTEMPTS - 1, None)


def test_a_passkey_success_clears_its_own_count(app, client, username, monkeypatch):
    """The passkey's counter, apart from the password's, is the one its success resets."""
    from models.second_factor_failure import SecondFactorFailure
    assert _signs_in_by_passkey(monkeypatch, username)(client).status_code == 200
    with app.app_context():
        assert SecondFactorFailure.query.filter_by(kind='webauthn', target=username).count() == 0


def test_a_certificate_auto_login_leaves_the_password_count(app, username, monkeypatch):
    """The mTLS middleware opens a session on any call: the count and the lock stay."""
    import middleware.mtls_middleware as mtls_middleware
    from services.mtls_auth_service import MTLSAuthService
    from tests.test_session_lifecycle import _cert_login
    until = utc_now() + timedelta(minutes=15)
    with app.app_context():
        _another_node_writes(username, failed_logins=MAX_ATTEMPTS, locked_until=until)
        uid = User.query.filter_by(username=username).one().id
    monkeypatch.setattr(MTLSAuthService, 'is_mtls_enabled', staticmethod(lambda: True))
    monkeypatch.setattr(mtls_middleware, '_extract_certificate', lambda: {'serial': '0a'})
    _cert_login(monkeypatch, app, uid)
    assert app.test_client().get('/api/v2/account/profile').status_code == 200
    with app.app_context():
        assert tuple(_stored(username)) == (MAX_ATTEMPTS, until)


# --- A new password, an administrator's unlock -----------------------------------

def test_a_password_reset_by_link_clears_a_lock_written_meanwhile(app, username, monkeypatch):
    """The new password restarts its count in the database, not only on the copy read."""
    import hashlib
    from tests.test_session_lifecycle import NEW_PASSWORD, _post
    token = uuid.uuid4().hex
    with app.app_context():
        _another_node_writes(username, password_reset_token=hashlib.sha256(token.encode()).hexdigest(),
                             password_reset_expires=utc_now() + timedelta(hours=1))
    real = User.set_password

    def another_node_locks_meanwhile(self, password):
        _another_node_writes(self.username, failed_logins=MAX_ATTEMPTS,
                             locked_until=utc_now() + timedelta(minutes=15))
        return real(self, password)

    monkeypatch.setattr(User, 'set_password', another_node_locks_meanwhile)
    response = _post(app.test_client(), '/api/v2/auth/reset-password',
                     {'token': token, 'password': NEW_PASSWORD})
    assert response.status_code == 200, response.data
    with app.app_context():
        assert tuple(_stored(username)) == (0, None)


def _locked_after_the_read(monkeypatch, uid, name):
    """Another node locks the account just after the unlock read it."""
    real = db.session.get

    def get(entity, ident, *args, **kwargs):
        found = real(entity, ident, *args, **kwargs)
        if entity is User and ident == uid:
            _another_node_writes(name, failed_logins=MAX_ATTEMPTS,
                                 locked_until=utc_now() + timedelta(minutes=15))
        return found
    monkeypatch.setattr(db.session, 'get', get)


def test_an_unlock_lifts_a_lock_written_after_the_account_was_read(
        app, username, auth_client, monkeypatch):
    with app.app_context():
        uid = User.query.filter_by(username=username).one().id
    _locked_after_the_read(monkeypatch, uid, username)
    response = auth_client.post(f'/api/v2/users/{uid}/unlock')
    monkeypatch.undo()
    assert response.status_code == 200
    assert response.get_json()['message'] == f'User {username} unlocked successfully'
    with app.app_context():
        assert tuple(_stored(username)) == (0, None)


NEW_PASSWORD = 'Another-Passw0rd-7!'


def _locked_elsewhere(name):
    _another_node_writes(name, failed_logins=MAX_ATTEMPTS,
                         locked_until=utc_now() + timedelta(minutes=15))


def test_a_password_set_by_an_administrator_ends_the_lock_of_the_old_one(app, username, auth_client):
    """The count was of guesses at a password that no longer exists."""
    with app.app_context():
        uid = User.query.filter_by(username=username).one().id
        _locked_elsewhere(username)
    response = auth_client.post(f'/api/v2/users/{uid}/reset-password', json={'new_password': NEW_PASSWORD})
    assert response.status_code == 200, response.get_json()
    with app.app_context():
        assert tuple(_stored(username)) == (0, None)


def test_a_password_changed_in_a_session_ends_the_lock_of_the_old_one(app, client, username):
    assert client.post(PASSWORD_DOOR, json={'username': username, 'password': PASSWORD}).status_code == 200
    with app.app_context():
        _locked_elsewhere(username)
    response = client.post('/api/v2/account/password',
                           json={'current_password': PASSWORD, 'new_password': NEW_PASSWORD})
    assert response.status_code == 200, response.get_json()
    with app.app_context():
        assert tuple(_stored(username)) == (0, None)


def test_an_unlock_of_an_account_without_count_says_so(app, username, auth_client):
    with app.app_context():
        uid = User.query.filter_by(username=username).one().id
    response = auth_client.post(f'/api/v2/users/{uid}/unlock')
    assert (response.status_code, response.get_json()['message']) == (200, 'Account is not locked')


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
        from tests.sso_identity_support import attach_from_another_node
        attach_from_another_node(username, ldap_provider, f'uuid-{entry_uid}')
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
