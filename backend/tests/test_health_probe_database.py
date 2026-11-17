"""Probes and a database that does not answer: /health/live reads nothing from it, /health/ready
answers 503 within READY_DATABASE_TIMEOUT_SECONDS and reads nothing else once SELECT 1 failed."""
import threading
import time
from contextlib import contextmanager

import pytest
from sqlalchemy import event

from config.settings import Config

LIVE = ['/health/live', '/api/health/live', '/api/v2/health/live']
READY = ['/health/ready', '/api/health/ready', '/api/v2/health/ready']


@contextmanager
def database_use(app):
    """Every pool checkout and statement of the application engine while the block runs."""
    from models import db
    with app.app_context():
        engine = db.engine
    seen = []

    def checkout(*_):
        seen.append('checkout')

    def statement(conn, cursor, sql, *_):
        seen.append(sql)
    event.listen(engine.pool, 'checkout', checkout)
    event.listen(engine, 'before_cursor_execute', statement)
    try:
        yield seen
    finally:
        event.remove(engine.pool, 'checkout', checkout)
        event.remove(engine, 'before_cursor_execute', statement)


@pytest.fixture
def ha(app, monkeypatch):
    from services import cluster_maintenance
    monkeypatch.setattr(Config, 'HA_MODE', True)
    monkeypatch.setattr(Config, 'NODE_ID', 'probe-node')
    # The maintenance view due for a read, as it is every OBSERVE_TTL_SECONDS
    monkeypatch.setattr(cluster_maintenance.view_of(app), 'observed', None)


@pytest.mark.parametrize('path', LIVE)
def test_liveness_touches_no_database(app, client, ha, path):
    with database_use(app) as seen:
        r = client.get(path)
    assert r.status_code == 200 and r.get_json()['status'] == 'alive'
    assert seen == []


@pytest.mark.parametrize('path', LIVE + READY)
def test_a_session_key_reload_due_waits_for_another_request(app, client, ha, monkeypatch, path):
    import api.health_routes as hr
    from security import session_key
    monkeypatch.setattr(hr, '_select_1', lambda _app: None)
    monkeypatch.setattr(hr, '_check_cluster', lambda: {'status': 'ok'})
    state = app.extensions.setdefault(session_key._STATE, {})
    monkeypatch.setitem(state, 'retry', (time.monotonic() - 1, 1))
    loads = []
    monkeypatch.setattr(session_key, 'load_keys', lambda *a, **k: loads.append(a))
    assert client.get(path).status_code == 200
    assert loads == []


@pytest.mark.parametrize('path', READY)
def test_readiness_reads_nothing_more_once_select_1_failed(app, client, ha, monkeypatch, path):
    import api.health_routes as hr

    def refused(_app):
        raise OSError('connection refused')
    monkeypatch.setattr(hr, '_select_1', refused)
    with database_use(app) as seen:
        r = client.get(path)
    assert r.status_code == 503
    body = r.get_json()
    assert body['checks']['database'] == {'status': 'error', 'message': 'Database connection failed'}
    assert body['checks']['cluster']['status'] == 'error'
    assert seen == []


def test_readiness_gives_up_on_a_database_that_does_not_answer(app, client, ha, monkeypatch):
    import api.health_routes as hr
    release = threading.Event()
    calls = []

    def hangs(_app):
        calls.append(1)
        release.wait(30)
    monkeypatch.setattr(hr, '_select_1', hangs)
    monkeypatch.setattr(hr, 'READY_DATABASE_TIMEOUT_SECONDS', 0.5)
    try:
        began = time.monotonic()
        first = client.get('/health/ready')
        took = time.monotonic() - began
        assert first.status_code == 503 and 0.4 < took < 3, took
        assert first.get_json()['checks']['database']['status'] == 'error'
        # The check still pending: the next probe answers at once and starts no other one
        began = time.monotonic()
        second = client.get('/health/ready')
        assert second.status_code == 503 and time.monotonic() - began < 0.4
        assert calls == [1]
    finally:
        release.set()
    hr.wait_for_pending_check(5)
    monkeypatch.undo()
    assert client.get('/health/ready').status_code == 200


def test_readiness_still_answers_200_with_the_database(app, client, ha, monkeypatch):
    import api.health_routes as hr
    monkeypatch.setattr(hr, '_check_cluster', lambda: {'status': 'ok'})
    with database_use(app) as seen:
        r = client.get('/health/ready')
    assert r.status_code == 200, r.get_json()
    assert 'SELECT 1' in seen


def _concurrent_checks(app, hr, monkeypatch, read, callers, spacing=0.05):
    """`callers` database checks started `spacing` apart: their results, durations, the reads
    made and the most reads in flight at once."""
    state = {'reads': 0, 'inflight': 0, 'peak': 0}
    lock = threading.Lock()

    def select_1(_app):
        with lock:
            state['reads'] += 1
            state['inflight'] += 1
            state['peak'] = max(state['peak'], state['inflight'])
        try:
            read()
        finally:
            with lock:
                state['inflight'] -= 1
    monkeypatch.setattr(hr, '_select_1', select_1)
    results = [None] * callers

    def call(i):
        with app.app_context():
            began = time.monotonic()
            outcome = hr._check_database()
            results[i] = (outcome['status'], time.monotonic() - began, time.monotonic())
    threads = []
    for i in range(callers):
        threads.append(threading.Thread(target=call, args=(i,)))
        threads[-1].start()
        time.sleep(spacing)
    for t in threads:
        t.join(10)
    return results, state


@pytest.mark.parametrize('callers', [1, 2, 5])
def test_probes_during_a_slow_healthy_check_share_its_success(app, ha, monkeypatch, callers):
    import api.health_routes as hr
    monkeypatch.setattr(hr, 'READY_DATABASE_TIMEOUT_SECONDS', 2.0)
    results, state = _concurrent_checks(app, hr, monkeypatch, lambda: time.sleep(0.4), callers)
    assert [r[0] for r in results] == ['ok'] * callers
    assert state['reads'] == 1 and state['peak'] == 1
    assert all(took < 0.9 for _, took, _ in results), results


@pytest.mark.parametrize('callers', [1, 2, 5])
def test_probes_during_a_silent_check_give_up_at_its_deadline(app, ha, monkeypatch, callers):
    import api.health_routes as hr
    release = threading.Event()
    monkeypatch.setattr(hr, 'READY_DATABASE_TIMEOUT_SECONDS', 0.6)
    try:
        began = time.monotonic()
        results, state = _concurrent_checks(app, hr, monkeypatch, lambda: release.wait(30), callers)
    finally:
        release.set()
    hr.wait_for_pending_check(5)
    assert [r[0] for r in results] == ['error'] * callers
    assert state['reads'] == 1 and state['peak'] == 1
    # Every caller waits for the one check until its deadline, none past it
    ends = [end - began for _, _, end in results]
    assert all(0.5 < end < 1.0 for end in ends), ends


@pytest.mark.parametrize('callers', [1, 2, 5])
def test_probes_against_a_failing_database_fail_one_read_at_a_time(app, ha, monkeypatch, callers):
    import api.health_routes as hr

    def refused():
        time.sleep(0.01)
        raise OSError('connection refused')
    results, state = _concurrent_checks(app, hr, monkeypatch, refused, callers, spacing=0.002)
    assert [r[0] for r in results] == ['error'] * callers
    assert 1 <= state['reads'] <= callers and state['peak'] == 1
    assert all(took < 0.5 for _, took, _ in results), results


def test_a_probe_sharing_a_failed_check_logs_it(app, ha, monkeypatch, caplog):
    import api.health_routes as hr
    monkeypatch.setattr(hr, 'READY_DATABASE_TIMEOUT_SECONDS', 2.0)

    def refused():
        time.sleep(0.3)
        raise OSError('connection refused')
    with caplog.at_level('ERROR'):
        results, _ = _concurrent_checks(app, hr, monkeypatch, refused, 2)
    assert [r[0] for r in results] == ['error', 'error']
    assert sum('Database health check failed' in r.getMessage() for r in caplog.records) == 2
