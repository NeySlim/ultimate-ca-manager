"""Migration 102 deletes the settings nothing reads any more, on both backends."""
import importlib
import os
import sqlite3

import pytest
from sqlalchemy import create_engine, text

PG_URL = os.getenv('UCM_TEST_PG_URL')
KEPT = ('session_timeout', 'acme.enabled')


def _migration():
    return importlib.import_module('migrations.102_dead_settings')


def test_sqlite_deletes_only_the_dead_keys():
    m = _migration()
    conn = sqlite3.connect(':memory:')
    conn.execute("CREATE TABLE system_config (key TEXT PRIMARY KEY, value TEXT)")
    conn.executemany("INSERT INTO system_config VALUES (?, 'x')", [(k,) for k in m.DEAD_KEYS + KEPT])
    m.upgrade(conn)
    m.upgrade(conn)
    left = {r[0] for r in conn.execute("SELECT key FROM system_config")}
    assert left == set(KEPT)


@pytest.mark.postgres
@pytest.mark.skipif(not PG_URL, reason='UCM_TEST_PG_URL not set')
def test_postgres_deletes_only_the_dead_keys():
    m = _migration()
    schema = f"migtest_102_{os.getenv('PYTEST_XDIST_WORKER', 'main')}"
    engine = create_engine(PG_URL)
    conn = engine.connect()
    try:
        conn.execute(text(f"DROP SCHEMA IF EXISTS {schema} CASCADE"))
        conn.execute(text(f"CREATE SCHEMA {schema}"))
        conn.execute(text(f"SET search_path TO {schema}"))
        conn.execute(text("CREATE TABLE system_config (key VARCHAR(255) PRIMARY KEY, value TEXT)"))
        for k in m.DEAD_KEYS + KEPT:
            conn.execute(text("INSERT INTO system_config VALUES (:k, 'x')"), {'k': k})
        m.upgrade(conn)
        m.upgrade(conn)
        left = {r[0] for r in conn.execute(text("SELECT key FROM system_config"))}
        assert left == set(KEPT)
    finally:
        conn.rollback()
        conn.execute(text(f"DROP SCHEMA IF EXISTS {schema} CASCADE"))
        conn.commit()
        conn.close()
        engine.dispose()
