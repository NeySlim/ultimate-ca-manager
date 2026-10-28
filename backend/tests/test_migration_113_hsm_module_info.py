"""Migration 113 adds hsm_providers.module_info, idempotently."""
import importlib
import os
import sqlite3

import pytest
from sqlalchemy import create_engine, inspect, text

PG_URL = os.getenv('UCM_TEST_PG_URL')


def _migration():
    return importlib.import_module('migrations.113_hsm_module_info')


def test_sqlite_adds_the_column_and_keeps_rows():
    conn = sqlite3.connect(':memory:')
    conn.execute("CREATE TABLE hsm_providers (id INTEGER PRIMARY KEY, name TEXT)")
    conn.execute("INSERT INTO hsm_providers (name) VALUES ('p11')")
    _migration().upgrade(conn)
    _migration().upgrade(conn)
    columns = {row[1] for row in conn.execute("PRAGMA table_info(hsm_providers)")}
    assert 'module_info' in columns
    assert conn.execute("SELECT name, module_info FROM hsm_providers"
                        ).fetchall() == [('p11', None)]


def test_sqlite_without_the_table_is_a_no_op():
    conn = sqlite3.connect(':memory:')
    _migration().upgrade(conn)
    assert conn.execute("SELECT name FROM sqlite_master").fetchall() == []


@pytest.mark.postgres
@pytest.mark.skipif(not PG_URL, reason='UCM_TEST_PG_URL not set')
def test_postgres_adds_the_column_and_keeps_rows():
    schema = f"migtest_113_{os.getenv('PYTEST_XDIST_WORKER', 'main')}"
    engine = create_engine(PG_URL)
    conn = engine.connect()
    try:
        conn.execute(text(f"DROP SCHEMA IF EXISTS {schema} CASCADE"))
        conn.execute(text(f"CREATE SCHEMA {schema}"))
        conn.execute(text(f"SET search_path TO {schema}"))
        conn.execute(text("CREATE TABLE hsm_providers (id SERIAL PRIMARY KEY, name TEXT)"))
        conn.execute(text("INSERT INTO hsm_providers (name) VALUES ('p11')"))
        _migration().upgrade(conn)
        _migration().upgrade(conn)
        columns = {c['name'] for c in inspect(conn).get_columns('hsm_providers', schema=schema)}
        assert 'module_info' in columns
        assert conn.execute(text("SELECT name, module_info FROM hsm_providers")
                            ).fetchall() == [('p11', None)]
    finally:
        conn.rollback()
        conn.execute(text(f"DROP SCHEMA IF EXISTS {schema} CASCADE"))
        conn.commit()
        conn.close()
        engine.dispose()
