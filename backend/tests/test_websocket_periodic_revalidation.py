"""A socket that only listens is revalidated by the server on its own timer, not only at its
next message: an account deactivated, a session ended, expired or bumped, a restore's epoch or a
permission withdrawn cut it within the revalidation delay; a permission granted joins its room.

The handshake registers the socket before it reads its session again from the store, so a
cut that lands while the handshake checks the session never misses it.
"""
import threading

import pytest
from flask import has_app_context, has_request_context

from models import SystemConfig, User, db
from tests.test_websocket_realtime import (  # noqa: F401 (fixture)
    PRIVILEGED, READER, _deactivate_unseen, _rooms, _session_client, _set_permissions, _sid,
    _socket, make_user)
from websocket import emitters, events


@pytest.fixture
def clock(monkeypatch):
    now = [10_000.0]
    monkeypatch.setattr(events, '_monotonic', lambda: now[0])
    return now


@pytest.fixture
def listening(app, make_user, clock):  # noqa: F811
    """A connected reader's socket that sends nothing, with its user id and its client."""
    user_id = make_user(role_perms=READER)
    client = _session_client(app, user_id)
    with _socket(app, client) as ws:
        assert ws.is_connected()
        ws.get_received()
        yield ws, user_id, client


def _due(clock):
    clock[0] += events.DEFAULT_REVALIDATE_SECONDS


def _sql(app, statement, **values):
    """A change no flush sees: only a revalidation can notice it."""
    with app.app_context():
        db.session.execute(statement.values(**values))
        db.session.commit()
        db.session.remove()


def test_a_socket_not_due_is_left_as_it_is(app, listening, clock):
    ws, user_id, _client = listening
    _deactivate_unseen(app, user_id)
    clock[0] += events.DEFAULT_REVALIDATE_SECONDS - 1
    assert events.revalidate_due_sockets(app) == 0
    assert ws.is_connected()


def test_a_deactivated_account_loses_its_listening_socket(app, listening, clock):
    ws, user_id, _client = listening
    _deactivate_unseen(app, user_id)
    _due(clock)
    assert events.revalidate_due_sockets(app) == 1
    assert not ws.is_connected() and _sid(ws) not in events.connected_clients


def test_a_session_version_bumped_unseen_cuts_the_socket(app, listening, clock):
    ws, user_id, _client = listening
    _sql(app, db.update(User).where(User.id == user_id),
         session_version=User.session_version + 1)
    _due(clock)
    assert events.revalidate_due_sockets(app) == 1
    assert not ws.is_connected()


def test_a_restore_epoch_advanced_unseen_cuts_the_socket(app, listening, clock):
    from auth.session_epoch import EPOCH_KEY, current_epoch
    ws, _user_id, _client = listening
    with app.app_context():
        epoch = current_epoch()
        row = SystemConfig.query.filter_by(key=EPOCH_KEY).first()
        if row is None:
            db.session.add(SystemConfig(key=EPOCH_KEY, value=str(epoch + 1), encrypted=False))
        else:
            row.value = str(epoch + 1)
        db.session.commit()
        db.session.remove()
    _due(clock)
    assert events.revalidate_due_sockets(app) == 1
    assert not ws.is_connected()


def test_an_expired_session_cuts_the_socket(app, listening, clock, monkeypatch):
    from auth.unified import AuthManager
    ws, _user_id, _client = listening
    monkeypatch.setattr(AuthManager, 'session_ended', staticmethod(lambda *a, **k: True))
    _due(clock)
    assert events.revalidate_due_sockets(app) == 1
    assert not ws.is_connected()


def test_a_session_gone_from_the_store_cuts_the_socket(app, listening, clock):
    ws, _user_id, client = listening
    iface = app.session_interface
    sid = client.get_cookie('session').value
    with app.app_context():
        iface._delete_session(iface._get_store_id(sid))
    _due(clock)
    assert events.revalidate_due_sockets(app) == 1
    assert not ws.is_connected()


def test_a_permission_withdrawn_cuts_and_one_granted_joins_its_room(app, make_user, clock):  # noqa: F811
    withdrawn, granted = make_user(role_perms=PRIVILEGED), make_user(role_perms=READER)
    with _socket(app, _session_client(app, withdrawn)) as ws_withdrawn, \
            _socket(app, _session_client(app, granted)) as ws_granted:
        _set_permissions(app, withdrawn, READER)
        _set_permissions(app, granted, PRIVILEGED)
        _due(clock)
        assert events.revalidate_due_sockets(app) == 1
        assert not ws_withdrawn.is_connected()
        assert ws_granted.is_connected() and emitters.ROOM_CAS in _rooms(ws_granted)


def test_a_valid_socket_is_kept_and_not_checked_again_before_it_is_due(app, listening, clock,
                                                                         monkeypatch):
    ws, _user_id, _client = listening
    _due(clock)
    assert events.revalidate_due_sockets(app) == 0
    assert ws.is_connected()
    checked = []
    monkeypatch.setattr(events, '_session_identity', lambda: checked.append(1))
    clock[0] += 1
    assert events.revalidate_due_sockets(app) == 0
    assert checked == [] and ws.is_connected()


class TestOneTimerPerProcess:
    @pytest.fixture(autouse=True)
    def _stopped(self):
        yield
        events.stop_revalidator()

    def test_started_once_it_checks_on_its_tick_until_stopped(self, app, monkeypatch):
        ticks = threading.Event()
        calls = []

        def checked(application):
            calls.append(application)
            ticks.set()
            return 0
        monkeypatch.setattr(events, 'revalidate_due_sockets', checked)
        first = events.start_revalidator(app, tick=0.01)
        assert events.start_revalidator(app, tick=0.01) is first
        assert [t for t in threading.enumerate() if t.name == events.REVALIDATOR_NAME] == [first._thread]
        assert ticks.wait(5) and calls[0] is app
        events.stop_revalidator()
        assert not first._thread.is_alive()

    def test_a_failed_round_does_not_stop_the_timer(self, app, monkeypatch):
        rounds = []
        again = threading.Event()

        def failing(application):
            rounds.append(1)
            if len(rounds) > 1:
                again.set()
            raise RuntimeError('database unreachable (test)')
        monkeypatch.setattr(events, 'revalidate_due_sockets', failing)
        events.start_revalidator(app, tick=0.01)
        assert again.wait(5)

    def test_the_worker_hooks_start_and_stop_it(self, app, monkeypatch):
        from tests.test_db_fork import _load_gunicorn_config, _worker
        module = _load_gunicorn_config(monkeypatch, app)
        for name in ('utils.db_fork.forget_inherited_connections',
                     'protocol_http_server.start_http_protocol_server',
                     'services.ws_relay.start_reader', 'services.ws_relay.stop_reader',
                     'services.cluster_commands.start_applier',
                     'services.cluster_commands.stop_applier'):
            monkeypatch.setattr(name, lambda *a, **k: None)
        module.post_worker_init(_worker())
        revalidator = events._revalidator
        assert revalidator is not None and revalidator.app is app
        assert revalidator._thread.is_alive()
        module.worker_exit(None, _worker())
        assert events._revalidator is None and not revalidator._thread.is_alive()

    def test_the_default_tick_is_well_under_the_revalidation_delay(self):
        assert 0 < events.REVALIDATE_TICK_SECONDS <= events.DEFAULT_REVALIDATE_SECONDS / 2


class TestHandshakeRace:
    """A cut that lands after the handshake read the session, before the socket was listed."""

    @staticmethod
    def _cut_while_checking(app, monkeypatch, change):
        real = events._session_identity

        def identity_then_cut():
            identity = real()
            if identity is not None:
                change(identity[0])
            return identity
        monkeypatch.setattr(events, '_session_identity', identity_then_cut)

    def test_a_session_bump_meanwhile_refuses_the_socket(self, app, make_user, monkeypatch):  # noqa: F811
        user_id = make_user(role_perms=READER)
        client = _session_client(app, user_id)

        def bump(uid):
            _sql(app, db.update(User).where(User.id == uid),
                 session_version=User.session_version + 1)
            with app.app_context():
                version = db.session.get(User, uid).session_version
                db.session.remove()
            events.end_account_sockets(uid, below=version)  # the commit's cut, before the listing
        self._cut_while_checking(app, monkeypatch, bump)
        with _socket(app, client) as ws:
            assert not ws.is_connected()
            assert events.connected_clients == {}

    def test_a_deactivation_meanwhile_refuses_the_socket(self, app, make_user, monkeypatch):  # noqa: F811
        user_id = make_user(role_perms=READER)
        client = _session_client(app, user_id)

        def deactivate(uid):
            _deactivate_unseen(app, uid)
            events.end_account_sockets(uid)
        self._cut_while_checking(app, monkeypatch, deactivate)
        with _socket(app, client) as ws:
            assert not ws.is_connected()

    def test_a_restore_meanwhile_refuses_the_socket(self, app, make_user, monkeypatch):  # noqa: F811
        from auth.session_epoch import advance_epoch
        user_id = make_user(role_perms=READER)
        client = _session_client(app, user_id)

        def restore(_uid):
            with app.app_context():
                advance_epoch()
                db.session.remove()
        self._cut_while_checking(app, monkeypatch, restore)
        with _socket(app, client) as ws:
            assert not ws.is_connected()

    def test_a_sign_out_meanwhile_refuses_the_socket(self, app, make_user, monkeypatch):  # noqa: F811
        """The record removed and its cut sent before the listing: only the record tells."""
        client = _session_client(app, make_user(role_perms=READER))
        iface = app.session_interface
        sid = client.get_cookie('session').value

        def sign_out(_uid):
            with app.app_context():
                iface._delete_session(iface._get_store_id(sid))
            events.end_session_sockets(sid)
        self._cut_while_checking(app, monkeypatch, sign_out)
        with _socket(app, client) as ws:
            assert not ws.is_connected()
            assert events.connected_clients == {}

    def test_a_lock_meanwhile_refuses_the_socket(self, app, make_user, monkeypatch):  # noqa: F811
        from auth.session_lock import LOCK_KEY
        client = _session_client(app, make_user(role_perms=READER))

        def lock(_uid):
            with client.session_transaction() as sess:
                sess[LOCK_KEY] = {'at': '2026-01-01T00:00:00', 'reason': 'manual'}
            events.end_session_sockets(client.get_cookie('session').value)
        self._cut_while_checking(app, monkeypatch, lock)
        with _socket(app, client) as ws:
            assert not ws.is_connected()

    def test_nothing_meanwhile_connects(self, app, make_user, monkeypatch):  # noqa: F811
        user_id = make_user(role_perms=READER)
        self._cut_while_checking(app, monkeypatch, lambda uid: None)
        with _socket(app, _session_client(app, user_id)) as ws:
            assert ws.is_connected()


def _database_away():
    from sqlalchemy.exc import OperationalError
    return OperationalError('SELECT 1', {}, ConnectionError('database unreachable (test)'))


@pytest.fixture
def outage(monkeypatch):
    """While true, the session check meets a database that does not answer."""
    from auth.unified import AuthManager
    down = [True]
    real = AuthManager.verify_session

    def verify(self):
        if down[0]:
            raise _database_away()
        return real(self)
    monkeypatch.setattr(AuthManager, 'verify_session', verify)
    return down


@pytest.fixture
def refusals(app, monkeypatch):
    """The reason of each handshake the server refuses, as the browser's connect_error reads it."""
    from socketio import packet
    server = events.socketio.server
    seen = []

    class Recording(server.packet_class):
        def __init__(self, packet_type=packet.EVENT, data=None, *args, **kwargs):
            if packet_type == packet.CONNECT_ERROR:
                seen.append(data)
            super().__init__(packet_type, data, *args, **kwargs)
    monkeypatch.setattr(server, 'packet_class', Recording)
    return seen


class TestDatabaseOrStoreAway:
    """A check that cannot reach the database or the session store is no refusal: the socket
    stays, unverified, for at most twice the revalidation delay, while a refusal cuts at once."""

    @staticmethod
    def _rounds_until(app, clock, seconds):
        """Rounds every tick over ``seconds``: the sockets cut."""
        cut, end = 0, clock[0] + seconds
        while clock[0] + events.REVALIDATE_TICK_SECONDS <= end:
            clock[0] += events.REVALIDATE_TICK_SECONDS
            cut += events.revalidate_due_sockets(app)
        return cut

    def test_a_round_during_an_outage_cuts_nothing_and_the_socket_stays_once_back(
            self, app, listening, clock, outage):
        ws, _user_id, _client = listening
        state = events.connected_clients[_sid(ws)]
        validated = state['validated_at']
        _due(clock)
        assert events.revalidate_due_sockets(app) == 0
        assert ws.is_connected() and state['validated_at'] == validated
        outage[0] = False
        clock[0] += events.REVALIDATE_TICK_SECONDS
        assert events.revalidate_due_sockets(app) == 0
        assert ws.is_connected() and state['validated_at'] == clock[0]
        # A later outage starts its own allowance
        outage[0] = True
        _due(clock)
        assert self._rounds_until(app, clock, events.DEFAULT_REVALIDATE_SECONDS) == 0
        assert ws.is_connected()

    def test_a_store_that_does_not_answer_is_an_outage_too(self, app, listening, clock,
                                                         monkeypatch):
        ws, _user_id, _client = listening

        def unreachable(_store_id):
            raise _database_away()
        with monkeypatch.context() as patched:
            patched.setattr(app.session_interface, '_retrieve_session_data', unreachable)
            _due(clock)
            assert events.revalidate_due_sockets(app) == 0
            assert ws.is_connected()
            # The context whose session could not open is not left pushed on the timer's thread
            assert not has_request_context() and not has_app_context()
        clock[0] += events.REVALIDATE_TICK_SECONDS
        assert events.revalidate_due_sockets(app) == 0
        assert events.connected_clients[_sid(ws)]['validated_at'] == clock[0]

    def test_an_outage_past_twice_the_delay_cuts_the_socket(self, app, listening, clock, outage):
        ws, _user_id, _client = listening
        _due(clock)
        assert events.revalidate_due_sockets(app) == 0
        bound = 2 * events.DEFAULT_REVALIDATE_SECONDS
        assert self._rounds_until(app, clock, bound - events.REVALIDATE_TICK_SECONDS) == 0
        assert ws.is_connected()
        assert self._rounds_until(app, clock, events.REVALIDATE_TICK_SECONDS) == 1
        assert not ws.is_connected() and _sid(ws) not in events.connected_clients

    def test_a_refusal_after_an_outage_cuts_at_once(self, app, listening, clock, outage):
        ws, user_id, _client = listening
        _due(clock)
        assert events.revalidate_due_sockets(app) == 0
        outage[0] = False
        _deactivate_unseen(app, user_id)
        clock[0] += events.REVALIDATE_TICK_SECONDS
        assert events.revalidate_due_sockets(app) == 1
        assert not ws.is_connected()

    def test_a_message_during_an_outage_is_answered_until_the_bound(self, app, listening, clock,
                                                                    outage):
        ws, _user_id, _client = listening
        _due(clock)
        ws.emit('ping')
        assert [m['name'] for m in ws.get_received()] == ['pong']
        assert ws.is_connected()
        clock[0] += 2 * events.DEFAULT_REVALIDATE_SECONDS
        ws.emit('ping')
        assert not ws.is_connected() and _sid(ws) not in events.connected_clients

    def test_a_handshake_during_an_outage_is_refused_as_unavailable(
            self, app, make_user, outage, refusals):  # noqa: F811
        client = _session_client(app, make_user(role_perms=READER))
        with _socket(app, client) as ws:
            assert not ws.is_connected()
        assert refusals == [{'message': events.HANDSHAKE_UNAVAILABLE}]
        assert events.connected_clients == {}
        outage[0] = False
        with _socket(app, client) as ws:
            assert ws.is_connected()

    def test_a_store_away_at_the_handshake_second_read_is_refused_as_unavailable(
            self, app, make_user, refusals, monkeypatch):  # noqa: F811
        client = _session_client(app, make_user(role_perms=READER))
        iface = app.session_interface
        real = iface._retrieve_session_data
        reads = []

        def first_read_only(store_id):
            reads.append(store_id)
            if len(reads) > 1:
                raise _database_away()
            return real(store_id)
        with monkeypatch.context() as patched:
            patched.setattr(iface, '_retrieve_session_data', first_read_only)
            with _socket(app, client) as ws:
                assert not ws.is_connected()
            assert not has_request_context()
        assert len(reads) == 2
        assert refusals == [{'message': events.HANDSHAKE_UNAVAILABLE}]
        assert events.connected_clients == {}

    def test_a_refused_handshake_keeps_the_plain_refusal(self, app, refusals):
        with _socket(app, _session_client(app)) as ws:
            assert not ws.is_connected()
        assert refusals and refusals[0] != {'message': events.HANDSHAKE_UNAVAILABLE}
