"""In HA the per-name DNS TXT lock is a PostgreSQL advisory lock, shared by every node.

Another node is a second PostgreSQL session holding the name's key: a flock on
this node's DATA_DIR would never see it.
"""
import os
import threading
import time

import pytest
from sqlalchemy import create_engine, text

from models import db
from services.acme import dns_txt_lock
from services.acme.dns_txt_lock import txt_record_lock

_PG_URL = os.environ.get('UCM_TEST_PG_URL')
NAME = '_acme-challenge.example.com'


@pytest.fixture
def ha(monkeypatch):
    from utils import ha as ha_mod
    monkeypatch.setattr(ha_mod, 'ha_enabled', lambda: True)


@pytest.fixture
def on_postgresql(app):
    """db.engine bound to the PostgreSQL bench; the lock needs no schema."""
    if not _PG_URL:
        pytest.skip('UCM_TEST_PG_URL not set')
    engine = create_engine(_PG_URL, pool_pre_ping=True)
    engines = db._app_engines[app]
    original = engines[None]
    with app.app_context():
        engines[None] = engine
        db.session.remove()
        try:
            yield engine
        finally:
            engines[None] = original
            db.session.remove()
            engine.dispose()


@pytest.fixture
def other_node(on_postgresql):
    conn = on_postgresql.connect().execution_options(isolation_level='AUTOCOMMIT')
    try:
        yield conn
    finally:
        conn.close()


def _enter_in_thread(app, name, entered, release):
    def run():
        with app.app_context(), txt_record_lock(name):
            entered.set()
            release.wait(10)
    thread = threading.Thread(target=run, daemon=True)
    thread.start()
    return thread


@pytest.mark.postgres
def test_a_name_held_by_another_node_waits_for_it(app, ha, other_node):
    key = dns_txt_lock.advisory_key(NAME)
    other_node.execute(text('SELECT pg_advisory_lock(:k)'), {'k': key})
    entered, release = threading.Event(), threading.Event()
    thread = _enter_in_thread(app, NAME, entered, release)
    try:
        assert not entered.wait(0.5), 'entered while another node held the name'
        other_node.execute(text('SELECT pg_advisory_unlock(:k)'), {'k': key})
        assert entered.wait(5), 'never entered once the other node released the name'
        # Now this node holds it: the other node cannot take it
        assert other_node.execute(text('SELECT pg_try_advisory_lock(:k)'), {'k': key}).scalar() is False
    finally:
        release.set()
        thread.join(5)
    assert other_node.execute(text('SELECT pg_try_advisory_lock(:k)'), {'k': key}).scalar() is True
    other_node.execute(text('SELECT pg_advisory_unlock(:k)'), {'k': key})


@pytest.mark.postgres
def test_the_key_is_the_name_whatever_its_case(app, ha, other_node):
    assert dns_txt_lock.advisory_key(NAME.upper()) == dns_txt_lock.advisory_key(NAME)
    assert dns_txt_lock.advisory_key('_acme-challenge.other.example') != dns_txt_lock.advisory_key(NAME)


@pytest.mark.postgres
def test_another_name_is_not_held_up(app, ha, other_node):
    key = dns_txt_lock.advisory_key(NAME)
    other_node.execute(text('SELECT pg_advisory_lock(:k)'), {'k': key})
    entered, release = threading.Event(), threading.Event()
    thread = _enter_in_thread(app, '_acme-challenge.other.example', entered, release)
    try:
        assert entered.wait(5)
    finally:
        release.set()
        thread.join(5)
        other_node.execute(text('SELECT pg_advisory_unlock(:k)'), {'k': key})


@pytest.mark.postgres
def test_past_the_wait_it_goes_on_unprotected(app, ha, other_node, monkeypatch):
    monkeypatch.setattr(dns_txt_lock, 'LOCK_WAIT_SECONDS', 0.3)
    key = dns_txt_lock.advisory_key(NAME)
    other_node.execute(text('SELECT pg_advisory_lock(:k)'), {'k': key})
    try:
        started = time.monotonic()
        with txt_record_lock(NAME):
            assert time.monotonic() - started >= 0.3
    finally:
        other_node.execute(text('SELECT pg_advisory_unlock(:k)'), {'k': key})


def test_without_ha_the_lock_is_the_host_lock(app, monkeypatch):
    calls = []
    real = dns_txt_lock.process_lock
    monkeypatch.setattr(dns_txt_lock, 'process_lock', lambda *a, **k: calls.append(a[0]) or real(*a, **k))
    with app.app_context(), txt_record_lock(NAME):
        pass
    assert len(calls) == 1


def test_in_ha_on_sqlite_the_lock_is_the_host_lock(app, ha, monkeypatch):
    calls = []
    real = dns_txt_lock.process_lock
    monkeypatch.setattr(dns_txt_lock, 'process_lock', lambda *a, **k: calls.append(a[0]) or real(*a, **k))
    with app.app_context():
        if db.engine.dialect.name != 'sqlite':
            pytest.skip('the application runs on PostgreSQL in this job')
        with txt_record_lock(NAME):
            pass
    assert len(calls) == 1
