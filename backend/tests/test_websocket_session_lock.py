"""A lock cuts the WebSocket of that session at once, on every process, and only of that session.

The node that takes ``POST /api/v2/auth/lock`` closes its own sockets of the session before it
answers; the other processes hear it through the transport their events take (the database
relay, or the Redis message queue). A locked session cannot open a socket again.
"""
import json
import time
from contextlib import contextmanager

import pytest

from services import ws_relay
from tests import pg_app_harness
from tests.test_session_lock_and_info import (  # noqa: F401 (fixture)
    _password_session, _post, make_user)
from websocket import events, socketio


def _lock(c, reason='manual'):
    r = _post(c, '/api/v2/auth/lock', {'reason': reason})
    assert r.status_code == 200, r.data
    return r


@contextmanager
def _socket(app, client):
    ws = socketio.test_client(app, flask_test_client=client)
    try:
        yield ws
    finally:
        if ws.is_connected():
            ws.disconnect()


def _sid(ws):
    return socketio.server.manager.sid_from_eio_sid(ws.eio_sid, '/')


def _key_of(ws):
    return events.connected_clients[_sid(ws)]['session']


def _wait_for(predicate, timeout=10.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.05)
    return predicate()


@pytest.fixture
def relay_engine(app, tmp_path):
    """The relay table the nodes share: the application's PostgreSQL schema, else a file database."""
    if pg_app_harness.ENABLED:
        from services.scheduler_leader import _dedicated_engine, application_url
        with app.app_context():
            engine = _dedicated_engine(application_url())
    else:
        import importlib
        import sqlite3
        from sqlalchemy import create_engine
        path = tmp_path / 'relay.db'
        conn = sqlite3.connect(path)
        importlib.import_module('migrations._from_2_254.149_websocket_relay').upgrade(conn)
        conn.close()
        engine = create_engine(f'sqlite:///{path}')
    yield engine
    engine.dispose()


@pytest.fixture
def two_sessions(app, make_user):  # noqa: F811
    """Two sessions of one account, each with its socket open (revalidation not due)."""
    user = make_user()
    first, second = _password_session(app, user), _password_session(app, user)
    with _socket(app, first) as ws_first, _socket(app, second) as ws_second:
        assert ws_first.is_connected() and ws_second.is_connected()
        assert _key_of(ws_first) != _key_of(ws_second)
        yield (first, ws_first), (second, ws_second)


class TestLockCutsTheSessionSockets:
    def test_the_locked_session_socket_is_cut_before_any_frame(self, app, two_sessions):
        (first, ws_first), (_, ws_second) = two_sessions
        sid_first, sid_second = _sid(ws_first), _sid(ws_second)
        _lock(first)
        # Cut by the lock itself: no frame sent, the 60 s revalidation not due
        assert not ws_first.is_connected()
        assert sid_first not in events.connected_clients
        # The other session of the same account keeps its socket
        assert ws_second.is_connected()
        assert sid_second in events.connected_clients
        ws_second.emit('ping')
        assert [m['name'] for m in ws_second.get_received()][-1] == 'pong'

    def test_a_locked_session_cannot_open_a_socket_again(self, app, two_sessions):
        (first, _), _ = two_sessions
        _lock(first)
        with _socket(app, first) as again:
            assert not again.is_connected()

    def test_an_idle_lock_cuts_too(self, app, two_sessions):
        (first, ws_first), (_, ws_second) = two_sessions
        _lock(first, reason='idle')
        assert not ws_first.is_connected()
        assert ws_second.is_connected()


class TestOtherProcesses:
    def test_the_lock_tells_the_relay_the_session_key_only(self, app, two_sessions, monkeypatch):
        (first, ws_first), _ = two_sessions
        key = _key_of(ws_first)
        published = []

        class Publisher:
            def publish(self, room, payload):
                published.append((room, payload))

        monkeypatch.setattr(events, '_relay_publisher', Publisher())
        monkeypatch.setattr(events, '_relay_emits_here', True)
        _lock(first)
        assert published == [(events.SESSION_END_ROOM,
                              {'type': events.SESSION_END_EVENT, 'session': key})]
        # The session id itself, a credential, never reaches the shared table
        cookie = first.get_cookie('session').value
        assert cookie not in json.dumps(published)

    def test_a_relayed_session_end_cuts_that_session_here(self, app, two_sessions, relay_engine):
        """Another node locked the session: its relay row reaches this worker's reader."""
        (_, ws_first), (_, ws_second) = two_sessions
        engine = relay_engine
        reader = ws_relay.RelayReader(engine, ws_relay._emit_local, tick=0.05, gap_grace=0.2)
        reader.run_once()  # its cursor, before the other node writes
        other_node = ws_relay.RelayPublisher(engine, origin='other-node')
        try:
            other_node.publish(events.SESSION_END_ROOM,
                               {'type': events.SESSION_END_EVENT, 'session': _key_of(ws_first)})
            assert _wait_for(lambda: (reader.run_once(), not ws_first.is_connected())[1])
            assert ws_second.is_connected()
        finally:
            other_node.stop()

    def test_the_redis_queue_carries_the_session_end_to_the_other_hosts(self, app, two_sessions):
        """The queue's listener cuts the session here instead of sending the event to a browser."""
        (_, ws_first), (_, ws_second) = two_sessions
        sent = []

        class Base:
            def _handle_emit(self, message):
                sent.append(message)

        manager = events._session_ending(Base)()
        manager._handle_emit({'method': 'emit', 'event': events.SESSION_END_EVENT,
                              'data': [{'session': _key_of(ws_first)}],
                              'room': events.SESSION_END_ROOM, 'namespace': '/'})
        assert not ws_first.is_connected()
        assert ws_second.is_connected()
        assert sent == []
        other = {'method': 'emit', 'event': 'event', 'data': [{}], 'room': 'scope:certificates'}
        manager._handle_emit(other)
        assert sent == [other]

    def test_the_queue_publishes_the_session_end_once_locked(self, app, two_sessions, monkeypatch):
        (first, ws_first), _ = two_sessions
        key = _key_of(ws_first)
        emitted = []
        monkeypatch.setattr(events, '_queue_in_use', True)
        monkeypatch.setattr(events.socketio, 'emit',
                            lambda event, data, **kw: emitted.append((event, data, kw.get('to'))))
        _lock(first)
        assert emitted == [(events.SESSION_END_EVENT, {'session': key}, events.SESSION_END_ROOM)]

    def test_no_business_event_can_target_the_control_room(self):
        with pytest.raises(events.WebSocketValidationError):
            events.emit_event('certificate.issued', {}, room=events.SESSION_END_ROOM)
