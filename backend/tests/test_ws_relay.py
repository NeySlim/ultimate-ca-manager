"""WebSocket events of the scheduler process reach the web workers' clients without Redis."""
import json
import logging
import os
import sqlite3
import subprocess
import sys
import textwrap
import time
from datetime import timedelta

import pytest
from sqlalchemy import create_engine, text

from services import ws_relay
from tests.test_websocket_realtime import _named, _session_client, _socket, make_user  # noqa: F401
from utils.datetime_utils import utc_now
from websocket import emitters, events, socketio

BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ROOM = emitters.ROOM_CERTIFICATES


def wait_for(predicate, timeout=10.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.02)
    return predicate()


@pytest.fixture
def relay_db(tmp_path):
    """A file database with migration 149, as the scheduler and the workers share it."""
    import importlib
    path = tmp_path / 'relay.db'
    conn = sqlite3.connect(path)
    importlib.import_module('migrations.149_websocket_relay').upgrade(conn)
    conn.close()
    engine = create_engine(f'sqlite:///{path}')
    yield path, engine
    engine.dispose()


def _payload(n):
    return {'type': 'certificate.renewed', 'data': {'n': n}, 'timestamp': 't'}


def _rows(engine):
    with engine.connect() as conn:
        return conn.execute(text("SELECT id, room, payload FROM websocket_relay ORDER BY id")).fetchall()


class Clock:
    def __init__(self):
        self.now = 1000.0

    def __call__(self):
        return self.now


def _reader(engine, clock=None, **kw):
    got = []
    reader = ws_relay.RelayReader(engine, lambda room, payload: got.append((room, payload)),
                                  monotonic=clock or time.monotonic, **kw)
    return reader, got


def test_an_event_emitted_in_another_process_reaches_a_worker_client(app, make_user, relay_db,
                                                                     tmp_path):
    path, engine = relay_db
    reader, _ = _reader(engine)
    reader.deliver = ws_relay._emit_local
    reader.tick = 0.05
    user_id = make_user(role_perms=['read:certificates'])
    with _socket(app, _session_client(app, user_id)) as ws:
        assert ws.is_connected()
        ws.get_received()
        reader.start()
        try:
            assert wait_for(lambda: reader.seen is not None)
            # The scheduler process: no client, no message queue, the full emit path
            script = textwrap.dedent(f"""
                import sys
                sys.path.insert(0, {BACKEND!r})
                from sqlalchemy import create_engine
                from services.ws_relay import RelayPublisher
                from websocket import emitters, events
                publisher = RelayPublisher(create_engine({f'sqlite:///{path}'!r}))
                events.relay_through(publisher)
                emitters.on_certificate_renewed(7, 8, 'relayed.test')
                publisher.stop(timeout=10)
            """)
            env = dict(os.environ, UCM_CONFIG_DIR=str(tmp_path))
            done = subprocess.run([sys.executable, '-c', script], env=env, cwd=str(tmp_path),
                                  capture_output=True, text=True, timeout=120)
            assert done.returncode == 0, done.stderr[-2000:]
            received = []
            assert wait_for(lambda: received.extend(_named(ws.get_received(), 'event')) or
                            any(e['type'] == 'certificate.renewed' for e in received))
            time.sleep(0.3)  # several more passes: nothing is sent twice
            received.extend(_named(ws.get_received(), 'event'))
        finally:
            reader.stop()
    renewed = [e for e in received if e['type'] == 'certificate.renewed']
    assert len(renewed) == 1
    assert renewed[0]['data']['id'] == 7 and renewed[0]['data']['old_id'] == 8


def test_the_reader_skips_what_was_there_and_delivers_each_row_once_in_order(relay_db):
    _, engine = relay_db
    old = ws_relay.RelayPublisher(engine)
    old.publish(ROOM, _payload(-1))
    old.stop()
    reader, got = _reader(engine)
    reader.run_once()
    assert got == []
    publisher = ws_relay.RelayPublisher(engine)
    for n in range(50):
        publisher.publish(ROOM, _payload(n))
    publisher.stop()
    reader.run_once()
    reader.run_once()
    assert [p['data']['n'] for _, p in got] == list(range(50))
    assert {room for room, _ in got} == {ROOM}


def test_the_first_event_after_a_purge_emptied_the_table_is_not_delayed(relay_db):
    _, engine = relay_db
    old = ws_relay.RelayPublisher(engine)
    for n in range(3):
        old.publish(ROOM, _payload(n))
    old.stop()
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM websocket_relay"))  # what a quiet retention period leaves
    clock = Clock()
    reader, got = _reader(engine, clock)
    reader.run_once()
    publisher = ws_relay.RelayPublisher(engine)
    publisher.publish(ROOM, _payload(9))
    publisher.stop()
    reader.run_once()
    assert [p['data']['n'] for _, p in got] == [9]  # on the next tick, no gap grace


def test_a_gap_waits_then_a_late_row_is_still_delivered_once(relay_db):
    _, engine = relay_db
    clock = Clock()
    reader, got = _reader(engine, clock)
    reader.run_once()
    base = reader.seen

    def insert(row_id, n):
        with engine.begin() as conn:
            conn.execute(text("INSERT INTO websocket_relay (id, created_at, room, payload) "
                              "VALUES (:i, :t, :r, :p)"),
                         {'i': row_id, 't': utc_now(), 'r': ROOM, 'p': json.dumps(_payload(n))})

    insert(base + 2, 2)
    reader.run_once()
    assert got == []  # the missing id may still commit: the newer one waits
    clock.now += ws_relay.GAP_GRACE_SECONDS + 1
    reader.run_once()
    assert [p['data']['n'] for _, p in got] == [2]
    insert(base + 1, 1)
    reader.run_once()
    reader.run_once()
    assert [p['data']['n'] for _, p in got] == [2, 1]


def test_a_broken_row_or_delivery_holds_nothing_back(relay_db, caplog):
    _, engine = relay_db
    calls = []

    def deliver(room, payload):
        calls.append(payload['data']['n'])
        if payload['data']['n'] == 0:
            raise RuntimeError('client gone')

    reader = ws_relay.RelayReader(engine, deliver)
    reader.run_once()
    with engine.begin() as conn:
        conn.execute(text("INSERT INTO websocket_relay (created_at, room, payload) "
                          "VALUES (:t, :r, 'not json')"), {'t': utc_now(), 'r': ROOM})
    publisher = ws_relay.RelayPublisher(engine)
    publisher.publish(ROOM, _payload(0))
    publisher.publish(ROOM, _payload(1))
    publisher.stop()
    with caplog.at_level(logging.WARNING, logger='services.ws_relay'):
        reader.run_once()
        reader.run_once()
    assert calls == [0, 1]


def test_rows_past_the_retention_are_purged(relay_db):
    _, engine = relay_db
    times = [utc_now() - ws_relay.RETENTION - timedelta(minutes=1)]
    publisher = ws_relay.RelayPublisher(engine, clock=lambda: times[0])
    publisher.publish(ROOM, _payload(0))
    publisher.stop()
    assert len(_rows(engine)) == 1
    times[0] = utc_now()
    publisher = ws_relay.RelayPublisher(engine, clock=lambda: times[0])
    publisher.publish(ROOM, _payload(1))
    publisher.stop()
    assert [json.loads(r.payload)['data']['n'] for r in _rows(engine)] == [1]
    # Its own rows still in the window: it wakes again to purge them, then sleeps
    assert publisher._wait_seconds() == ws_relay.PURGE_EVERY_SECONDS
    times[0] = utc_now() + ws_relay.RETENTION + timedelta(minutes=1)
    publisher._next_purge = 0.0
    publisher.run_once()
    assert _rows(engine) == []
    assert publisher._wait_seconds() is None


def test_an_unreachable_database_blocks_neither_side(tmp_path, caplog):
    engine = create_engine(f'sqlite:///{tmp_path}/missing/dir/relay.db')
    publisher = ws_relay.RelayPublisher(engine, queue_max=5)
    with caplog.at_level(logging.WARNING, logger='services.ws_relay'):
        started = time.monotonic()
        for n in range(20):
            publisher.publish(ROOM, _payload(n))
        assert time.monotonic() - started < 1.0
        publisher.stop(timeout=2)
        reader, got = _reader(engine)
        reader.run_once()
        reader.run_once()
    assert len(publisher._queue) == 5  # bounded: the oldest are dropped
    assert [item[2] for item in publisher._queue][0] == json.dumps(_payload(15))
    assert reader.seen is None and got == []
    errors = [r for r in caplog.records if r.name == 'services.ws_relay' and r.levelno >= logging.ERROR]
    assert len([r for r in errors if 'read' in r.getMessage()]) == 1


def test_the_scheduler_process_relays_instead_of_emitting(app, monkeypatch, relay_db):
    _, engine = relay_db
    seen = []
    monkeypatch.setattr(socketio, 'emit', lambda *a, **kw: seen.append((a, kw)))
    monkeypatch.setattr(events, '_queue_in_use', False)
    monkeypatch.setattr(ws_relay, '_engine', lambda _app: engine)
    publisher = ws_relay.start_publisher(app)
    try:
        assert publisher is not None
        emitters.on_ca_created(5, 'relay-ca', 'relay-ca', 'system')
    finally:
        ws_relay.stop_publisher()
    assert seen == []
    (row,) = _rows(engine)
    assert row.room == emitters.ROOM_CAS
    assert json.loads(row.payload)['data']['id'] == 5
    emitters.on_ca_created(6, 'direct-ca', 'direct-ca', 'system')  # once stopped, this process emits directly again
    assert len(seen) == 1


def test_with_a_message_queue_nothing_is_relayed(app, monkeypatch, relay_db):
    _, engine = relay_db
    calls = []
    monkeypatch.setattr(events.socketio, 'init_app', lambda *a, **kw: calls.append(kw))
    monkeypatch.setattr(events, '_queue_in_use', events._queue_in_use)
    monkeypatch.setattr(events, '_message_queue', lambda _app: object())  # Redis configured
    monkeypatch.setattr(ws_relay, '_engine', lambda _app: engine)
    events.init_websocket(app)
    assert calls[0]['client_manager'] is not None
    assert ws_relay.start_publisher(app) is None
    assert ws_relay.start_reader(app) is None
    seen = []
    monkeypatch.setattr(socketio, 'emit', lambda *a, **kw: seen.append((a, kw)))
    emitters.on_ca_created(5, 'queued-ca', 'queued-ca', 'system')
    assert len(seen) == 1 and _rows(engine) == []
