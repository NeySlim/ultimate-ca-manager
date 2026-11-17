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
