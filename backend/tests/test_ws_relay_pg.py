"""WebSocket relay on PostgreSQL: two emitters and two workers reading the same table at once.

Each worker gets every event exactly once, each emitter's order is kept, and the purge
runs while the workers read.
"""
import json
import threading
import time

import pytest
from sqlalchemy import text

from services import ws_relay
from services.scheduler_leader import _dedicated_engine, application_url
from tests import pg_app_harness

pytestmark = pytest.mark.skipif(not pg_app_harness.ENABLED,
                                reason='needs UCM_TEST_APP_PG_URL (the application on PostgreSQL)')

PER_EMITTER = 150


def wait_for(predicate, timeout=20.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.05)
    return predicate()


@pytest.fixture
def engines(app):
    with app.app_context():
        url = application_url()
    made = [_dedicated_engine(url) for _ in range(4)]
    yield made
    for engine in made:
        engine.dispose()


def test_two_workers_each_get_every_event_once_in_emitter_order(engines):
    first_id = []
    with engines[0].connect() as conn:
        first_id.append(conn.execute(text("SELECT COALESCE(MAX(id), 0) FROM websocket_relay")).scalar())
    workers = []
    for engine in engines[:2]:
        got = []
        reader = ws_relay.RelayReader(engine, lambda room, payload, got=got: got.append(payload),
                                      tick=0.02, gap_grace=0.5)
        reader.run_once()  # its cursor, before anything is emitted
        workers.append((reader.start(), got))
    publishers = [ws_relay.RelayPublisher(engine, batch=7) for engine in engines[2:]]

    def emit(index, publisher):
        for n in range(PER_EMITTER):
            publisher.publish('scope:certificates',
                              {'type': 'certificate.renewed', 'data': {'e': index, 'n': n}, 'timestamp': 't'})
            if n % 10 == 0:
                time.sleep(0.005)  # interleaves the two emitters' transactions

    threads = [threading.Thread(target=emit, args=(i, p)) for i, p in enumerate(publishers)]
    try:
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        for publisher in publishers:
            publisher.stop(timeout=20)
        total = 2 * PER_EMITTER
        assert all(wait_for(lambda got=got: len(got) >= total) for _, got in workers)
        time.sleep(0.3)  # more passes: nothing arrives twice
    finally:
        for reader, _ in workers:
            reader.stop()
        with engines[0].begin() as conn:
            conn.execute(text("DELETE FROM websocket_relay WHERE id > :i"), {'i': first_id[0]})
    for _, got in workers:
        assert len(got) == 2 * PER_EMITTER
        for index in range(2):
            assert [p['data']['n'] for p in got if p['data']['e'] == index] == list(range(PER_EMITTER))


def test_an_id_committed_out_of_order_is_waited_for_then_delivered_once(engines):
    from utils.datetime_utils import utc_now
    insert = text("INSERT INTO websocket_relay (created_at, room, payload) VALUES (:t, 'r', :p) RETURNING id")

    def payload(n):
        return {'t': utc_now(), 'p': json.dumps({'type': 'x', 'data': {'n': n}})}

    now = [1000.0]
    got = []
    reader = ws_relay.RelayReader(engines[0], lambda room, p: got.append(p['data']['n']),
                                  monotonic=lambda: now[0], gap_grace=30.0)
    reader.run_once()
    slow = engines[1].connect()
    try:
        tx = slow.begin()
        low = slow.execute(insert, payload(1)).scalar()  # takes the lower id, commits last
        with engines[2].begin() as conn:
            high = conn.execute(insert, payload(2)).scalar()  # takes the higher id, commits first
        assert high > low
        reader.run_once()
        now[0] += 1
        reader.run_once()
        assert got == []  # the lower id may still commit: the higher one waits
        tx.commit()
        reader.run_once()
        reader.run_once()
        assert got == [1, 2]  # each once, in id order
    finally:
        slow.close()
        with engines[3].begin() as conn:
            conn.execute(text("DELETE FROM websocket_relay WHERE id >= :i"), {'i': low})


def test_the_first_event_after_a_purge_emptied_the_table_is_not_delayed_on_postgresql(engines):
    now = [1000.0]
    got = []
    first = ws_relay.RelayPublisher(engines[1])
    first.publish('r', {'type': 'x', 'data': {'n': 0}, 'timestamp': 't'})
    first.stop(timeout=20)
    with engines[0].begin() as conn:
        low = conn.execute(text("SELECT MIN(id) FROM websocket_relay")).scalar()
        conn.execute(text("DELETE FROM websocket_relay WHERE id >= :i"), {'i': low})
    reader = ws_relay.RelayReader(engines[2], lambda room, p: got.append(p['data']['n']),
                                  monotonic=lambda: now[0], gap_grace=30.0)
    reader.run_once()
    second = ws_relay.RelayPublisher(engines[3])
    second.publish('r', {'type': 'x', 'data': {'n': 1}, 'timestamp': 't'})
    second.stop(timeout=20)
    try:
        reader.run_once()
        assert got == [1]
    finally:
        with engines[0].begin() as conn:
            conn.execute(text("DELETE FROM websocket_relay WHERE id >= :i"), {'i': low})


def test_the_purge_keeps_recent_rows_on_postgresql(engines):
    from datetime import timedelta
    from utils.datetime_utils import utc_now
    old_at = utc_now() - ws_relay.RETENTION - timedelta(minutes=5)
    with engines[0].begin() as conn:
        old_id = conn.execute(text("INSERT INTO websocket_relay (created_at, room, payload) "
                                   "VALUES (:t, 'scope:cas', :p) RETURNING id"),
                              {'t': old_at, 'p': json.dumps({'type': 'x'})}).scalar()
    publisher = ws_relay.RelayPublisher(engines[1])
    publisher.publish('scope:cas', {'type': 'ca.created', 'data': {}, 'timestamp': 't'})
    publisher.stop(timeout=20)
    with engines[0].begin() as conn:
        ids = [r[0] for r in conn.execute(text("SELECT id FROM websocket_relay WHERE id >= :i ORDER BY id"),
                                          {'i': old_id})]
        conn.execute(text("DELETE FROM websocket_relay WHERE id >= :i"), {'i': old_id})
    assert old_id not in ids and len(ids) == 1


def _payload(node, n):
    return {'type': 'certificate.renewed', 'data': {'node': node, 'n': n}, 'timestamp': 't'}


@pytest.fixture
def wakeups(app):
    with app.app_context():
        url = application_url()
    made = []

    def make():
        made.append(ws_relay.PgWakeup(url))
        return made[-1]
    yield make
    for wakeup in made:
        wakeup.close()
        wakeup.engine.dispose()


@pytest.fixture
def first_id(engines):
    with engines[0].connect() as conn:
        start = ws_relay._newest_id(conn)
    yield start
    with engines[0].begin() as conn:
        conn.execute(text("DELETE FROM websocket_relay WHERE id > :i"), {'i': start})


def test_a_notify_wakes_the_reader_long_before_its_tick(engines, wakeups, first_id):
    got = []
    reader = ws_relay.RelayReader(engines[0], lambda room, p: got.append(p['data']['n']),
                                  tick=60.0, wakeup=wakeups())
    reader.start()
    try:
        assert wait_for(lambda: reader.wakeup.backend_pid is not None and reader.seen is not None)
        time.sleep(0.2)  # the reader is now waiting on LISTEN, not reading
        publisher = ws_relay.RelayPublisher(engines[1])
        publisher.publish('r', _payload('a', 1))
        publisher.stop(timeout=20)
        assert wait_for(lambda: got == [1], timeout=5.0)
    finally:
        reader.stop(timeout=70)


def test_a_lost_listen_connection_is_reopened(engines, wakeups, first_id):
    got = []
    reader = ws_relay.RelayReader(engines[0], lambda room, p: got.append(p['data']['n']),
                                  tick=60.0, wakeup=wakeups())
    reader.start()
    try:
        assert wait_for(lambda: reader.wakeup.backend_pid is not None and reader.seen is not None)
        lost = reader.wakeup.backend_pid
        with engines[2].connect() as conn:
            assert conn.execute(text("SELECT pg_terminate_backend(:p)"), {'p': lost}).scalar()
        assert wait_for(lambda: reader.wakeup.backend_pid not in (None, lost), timeout=10.0)
        time.sleep(0.2)
        publisher = ws_relay.RelayPublisher(engines[1])
        publisher.publish('r', _payload('a', 2))
        publisher.stop(timeout=20)
        assert wait_for(lambda: got == [2], timeout=5.0)
    finally:
        reader.stop(timeout=70)


def test_an_event_of_node_a_reaches_each_node_client_once(app, engines, monkeypatch, first_id):
    from websocket import emitters, events, socketio
    a_clients, b_clients = [], []
    monkeypatch.setattr(socketio, 'emit', lambda name, payload, **kw: a_clients.append(payload))
    publisher = ws_relay.RelayPublisher(engines[1], origin='node-a-worker')
    node_a = ws_relay.RelayReader(engines[0], lambda room, p: a_clients.append(p),
                                  skip_origin=publisher.origin, gap_grace=0.5)
    node_b = ws_relay.RelayReader(engines[2], lambda room, p: b_clients.append(p), gap_grace=0.5)
    node_a.run_once()
    node_b.run_once()
    monkeypatch.setattr(events, '_queue_in_use', False)
    events.relay_through(publisher, emit_here=True)
    try:
        emitters.on_ca_created(41, 'ha-ca', 'ha-ca', 'system')  # what an API request on A emits
    finally:
        events.relay_through(None)
    assert len(a_clients) == 1  # at once, before any read
    publisher.stop(timeout=20)
    for _ in range(3):
        node_a.run_once()
        node_b.run_once()
    assert [p['data']['id'] for p in a_clients] == [41]
    assert [p['data']['id'] for p in b_clients] == [41]
    assert ws_relay.ORIGIN_KEY not in b_clients[0]


def test_two_nodes_writing_at_once_lose_and_double_nothing(engines, wakeups, first_id):
    nodes = []
    for index, name in enumerate(('a', 'b')):
        got = []
        publisher = ws_relay.RelayPublisher(engines[2 + index], batch=5, origin=f'origin-{name}')
        reader = ws_relay.RelayReader(engines[index], lambda room, p, got=got: got.append(p['data']),
                                      tick=0.5, gap_grace=0.5, skip_origin=publisher.origin,
                                      wakeup=wakeups())
        reader.run_once()
        nodes.append((name, publisher, reader.start(), got))

    def emit(name, publisher):
        for n in range(PER_EMITTER):
            publisher.publish('scope:certificates', _payload(name, n))
            if n % 10 == 0:
                time.sleep(0.005)

    threads = [threading.Thread(target=emit, args=(name, publisher)) for name, publisher, _, _ in nodes]
    try:
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        for _, publisher, _, _ in nodes:
            publisher.stop(timeout=20)
        assert all(wait_for(lambda got=got: len(got) >= PER_EMITTER) for *_, got in nodes)
        time.sleep(1.2)  # more passes: nothing arrives twice
    finally:
        for _, _, reader, _ in nodes:
            reader.stop()
    for name, _, _, got in nodes:
        other = 'b' if name == 'a' else 'a'
        assert [d['n'] for d in got if d['node'] == other] == list(range(PER_EMITTER))
        assert not [d for d in got if d['node'] == name]
