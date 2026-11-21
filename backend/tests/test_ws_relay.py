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
    importlib.import_module('migrations._from_2_254.149_websocket_relay').upgrade(conn)
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


def test_writing_and_purging_raise_no_datetime_deprecation(relay_db):
    import warnings
    _, engine = relay_db
    times = [utc_now() - ws_relay.RETENTION - timedelta(minutes=1)]
    publisher = ws_relay.RelayPublisher(engine, clock=lambda: times[0])
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter('always')
        publisher.publish(ROOM, _payload(0))
        publisher.stop()
        times[0] = utc_now()
        publisher._next_purge = 0.0
        publisher.run_once()
    assert [str(w.message) for w in caught if 'datetime adapter' in str(w.message)] == []
    assert _rows(engine) == []  # written, then purged


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


def test_the_newest_id_falls_back_to_the_table_when_the_sequence_cannot_be_read():
    """On PostgreSQL a role without SELECT on the sequence still gets a cursor, from MAX(id)."""
    from contextlib import contextmanager
    from types import SimpleNamespace
    from sqlalchemy.exc import ProgrammingError

    class Result:
        def __init__(self, value):
            self.value = value

        def scalar(self):
            return self.value

    class Conn:
        dialect = SimpleNamespace(name='postgresql')
        savepoints = 0

        def execute(self, statement):
            sql = str(statement)
            if 'MAX(id)' in sql:
                return Result(41)
            if 'pg_get_serial_sequence' in sql:
                return Result('public.websocket_relay_id_seq')
            raise ProgrammingError(sql, {}, Exception('permission denied for sequence'))

        @contextmanager
        def begin_nested(self):
            self.savepoints += 1
            yield

    conn = Conn()
    assert ws_relay._newest_id(conn) == 41
    assert conn.savepoints == 1


# ---- HA: web workers publish too, and never deliver their own rows twice ----

@pytest.fixture
def ha_worker(app, monkeypatch, relay_db):
    """A web worker of an HA node without Redis: its reader and its publisher on relay_db."""
    from config.settings import Config
    _, engine = relay_db
    monkeypatch.setattr(Config, 'HA_MODE', True)
    monkeypatch.setattr(events, '_queue_in_use', False)
    monkeypatch.setattr(ws_relay, '_engine', lambda _app: engine)
    seen = []
    monkeypatch.setattr(socketio, 'emit', lambda *a, **kw: seen.append((a, kw)))
    monkeypatch.setattr(ws_relay.RelayReader, 'start', lambda self: self)  # driven by the test
    reader = ws_relay.start_reader(app)
    try:
        yield reader, ws_relay._publisher, seen, engine
    finally:
        ws_relay.stop_reader()


def test_a_reader_skips_the_rows_of_its_own_origin_only(relay_db):
    _, engine = relay_db
    mine = ws_relay.RelayPublisher(engine, origin='worker-a')
    other = ws_relay.RelayPublisher(engine, origin='worker-b')
    reader, got = _reader(engine)
    reader.skip_origin = mine.origin
    reader.run_once()
    mine.publish(ROOM, _payload(1))
    mine.stop()
    other.publish(ROOM, _payload(2))
    other.stop()
    reader.run_once()
    reader.run_once()
    assert [p['data']['n'] for _, p in got] == [2]
    assert all(ws_relay.ORIGIN_KEY not in p for _, p in got)  # the origin never reaches a browser
    assert reader.seen == _rows(engine)[-1].id  # its own row moved the cursor all the same


def test_in_ha_a_web_worker_emits_at_once_and_publishes_once(ha_worker):
    reader, publisher, seen, engine = ha_worker
    assert reader is not None and publisher is not None
    assert reader.skip_origin == publisher.origin
    reader.run_once()
    emitters.on_ca_created(5, 'ha-ca', 'ha-ca', 'system')
    assert len(seen) == 1  # its own clients: immediately, not on the next tick
    publisher.stop()
    (row,) = _rows(engine)
    assert row.room == emitters.ROOM_CAS and json.loads(row.payload)['data']['id'] == 5
    reader.run_once()
    reader.run_once()
    assert len(seen) == 1  # its own row read back: not emitted a second time


def test_in_ha_include_self_false_still_skips_the_caller_on_its_worker(ha_worker, monkeypatch):
    _, publisher, seen, engine = ha_worker
    monkeypatch.setattr(events, '_calling_sid', lambda: 'sid-1')
    events.emit_event('ca.created', {'id': 1}, room=emitters.ROOM_CAS, include_self=False)
    publisher.stop()
    assert seen[0][1] == {'to': emitters.ROOM_CAS, 'skip_sid': 'sid-1'}
    assert len(_rows(engine)) == 1  # the caller's socket lives on this worker only


def test_outside_ha_a_web_worker_does_not_publish(app, monkeypatch, relay_db):
    from config.settings import Config
    _, engine = relay_db
    monkeypatch.setattr(Config, 'HA_MODE', False)
    monkeypatch.setattr(events, '_queue_in_use', False)
    monkeypatch.setattr(ws_relay, '_engine', lambda _app: engine)
    monkeypatch.setattr(ws_relay.RelayReader, 'start', lambda self: self)
    seen = []
    monkeypatch.setattr(socketio, 'emit', lambda *a, **kw: seen.append((a, kw)))
    try:
        reader = ws_relay.start_reader(app)
        assert reader is not None and reader.skip_origin is None and ws_relay._publisher is None
        emitters.on_ca_created(5, 'single-ca', 'single-ca', 'system')
    finally:
        ws_relay.stop_reader()
    assert len(seen) == 1 and _rows(engine) == []


def test_in_ha_with_a_message_queue_the_relay_stays_off(app, monkeypatch, relay_db):
    from config.settings import Config
    _, engine = relay_db
    monkeypatch.setattr(Config, 'HA_MODE', True)
    monkeypatch.setattr(events, '_queue_in_use', True)
    monkeypatch.setattr(ws_relay, '_engine', lambda _app: engine)
    seen = []
    monkeypatch.setattr(socketio, 'emit', lambda *a, **kw: seen.append((a, kw)))
    assert ws_relay.start_reader(app) is None
    assert ws_relay._publisher is None and events._relay_publisher is None
    emitters.on_ca_created(5, 'queued-ca', 'queued-ca', 'system')
    assert len(seen) == 1 and _rows(engine) == []


def test_stopping_the_reader_stops_the_worker_publisher(ha_worker):
    _, publisher, _, _ = ha_worker
    ws_relay.stop_reader()
    assert ws_relay._publisher is None and events._relay_publisher is None
    assert publisher._stop.is_set()


class _Notify:
    def __init__(self, payload):
        self.payload = payload


class _FakeDriver:
    """psycopg connection stand-in: ``script`` is what each notifies() call does in turn."""

    def __init__(self, script):
        self.autocommit = False
        self.script = script
        self.info = type('Info', (), {'backend_pid': 42})()

    def execute(self, sql):
        return type('Cur', (), {'fetchone': lambda self: ('ucm',)})()

    def notifies(self, timeout):
        step = self.script.pop(0) if self.script else 'idle'
        if step == 'raise':
            raise OSError('server closed the connection')
        if step == 'idle':
            time.sleep(timeout)
            return iter(())
        return iter([_Notify(step)])


class _FakeRaw:
    def __init__(self, driver):
        self.driver_connection = driver
        self.closed = False

    def close(self):
        self.closed = True


class _FakeEngine:
    def __init__(self, scripts):
        self.scripts = scripts
        self.opened = []

    def raw_connection(self):
        raw = _FakeRaw(_FakeDriver(self.scripts.pop(0) if self.scripts else []))
        self.opened.append(raw)
        return raw


def _wakeup(monkeypatch, scripts):
    import services.scheduler_leader as leader
    monkeypatch.setattr(leader, '_dedicated_engine', lambda url: _FakeEngine(scripts))
    return ws_relay.PgWakeup('postgresql://unused')


def test_a_listen_connection_dropping_at_once_does_not_spin(monkeypatch, caplog):
    import threading
    wakeup = _wakeup(monkeypatch, [['raise'] for _ in range(50)])
    stop = threading.Event()
    calls, deadline = 0, time.monotonic() + 1.0
    with caplog.at_level(logging.WARNING, logger='services.ws_relay'):
        while time.monotonic() < deadline:
            wakeup.wait(2.0, stop)
            calls += 1
    assert calls <= 10
    assert sum('LISTEN connection lost' in r.getMessage() for r in caplog.records) == 1


def test_a_notification_of_another_schema_does_not_wake_the_reader(monkeypatch):
    import threading
    wakeup = _wakeup(monkeypatch, [['other_schema', 'other_schema', 'ucm']])
    stop = threading.Event()
    wakeup.wait(2.0, stop)  # opens the LISTEN connection
    assert wakeup.schema == 'ucm'
    wakeup.wait(2.0, stop)
    assert wakeup._raw.driver_connection.script == []  # returned on 'ucm', not before


def test_a_reader_outliving_its_stop_closes_the_listen_connection(monkeypatch):
    import threading
    connecting, release = threading.Event(), threading.Event()
    wakeup = _wakeup(monkeypatch, [[]])
    real = wakeup.engine.raw_connection

    def slow_connect():
        connecting.set()
        release.wait(5)  # a connect_timeout longer than stop()'s join
        return real()
    wakeup.engine.raw_connection = slow_connect

    class _Engine:
        def connect(self):
            raise OSError('down')
    reader = ws_relay.RelayReader(_Engine(), lambda room, p: None, tick=0.01, wakeup=wakeup).start()
    assert connecting.wait(5)
    reader.stop(timeout=0.05)
    release.set()
    assert wait_for(lambda: not reader._thread.is_alive())
    assert wakeup.engine.opened and all(raw.closed for raw in wakeup.engine.opened)
