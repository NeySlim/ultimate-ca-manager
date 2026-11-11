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
