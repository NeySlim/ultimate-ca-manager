"""Migration 112 adds acme_client_orders.deactivated_authz_urls (#422), idempotently."""
import importlib
import os
import sqlite3

import pytest
from sqlalchemy import create_engine, inspect, text

PG_URL = os.getenv('UCM_TEST_PG_URL')


def _migration():
    return importlib.import_module('migrations.112_acme_proxy_authz_deactivation')


def test_sqlite_adds_the_column_and_keeps_rows():
    conn = sqlite3.connect(':memory:')
    conn.execute("CREATE TABLE acme_client_orders (id INTEGER PRIMARY KEY, domains TEXT)")
    conn.execute("INSERT INTO acme_client_orders (domains) VALUES ('[\"a.example\"]')")
    _migration().upgrade(conn)
    _migration().upgrade(conn)
    columns = {row[1] for row in conn.execute("PRAGMA table_info(acme_client_orders)")}
    assert 'deactivated_authz_urls' in columns
    assert conn.execute("SELECT domains, deactivated_authz_urls FROM acme_client_orders"
                        ).fetchall() == [('["a.example"]', None)]


def test_sqlite_without_the_table_is_a_no_op():
    conn = sqlite3.connect(':memory:')
    _migration().upgrade(conn)
    assert conn.execute("SELECT name FROM sqlite_master").fetchall() == []


@pytest.mark.postgres
@pytest.mark.skipif(not PG_URL, reason='UCM_TEST_PG_URL not set')
def test_postgres_adds_the_column_and_keeps_rows():
    schema = f"migtest_112_{os.getenv('PYTEST_XDIST_WORKER', 'main')}"
    engine = create_engine(PG_URL)
    conn = engine.connect()
    try:
        conn.execute(text(f"DROP SCHEMA IF EXISTS {schema} CASCADE"))
        conn.execute(text(f"CREATE SCHEMA {schema}"))
        conn.execute(text(f"SET search_path TO {schema}"))
        conn.execute(text("CREATE TABLE acme_client_orders (id SERIAL PRIMARY KEY, domains TEXT)"))
        conn.execute(text("INSERT INTO acme_client_orders (domains) VALUES ('[\"a.example\"]')"))
        _migration().upgrade(conn)
        _migration().upgrade(conn)
        columns = {c['name'] for c in inspect(conn).get_columns('acme_client_orders', schema=schema)}
        assert 'deactivated_authz_urls' in columns
        assert conn.execute(text("SELECT domains, deactivated_authz_urls FROM acme_client_orders")
                            ).fetchall() == [('["a.example"]', None)]
    finally:
        conn.rollback()
        conn.execute(text(f"DROP SCHEMA IF EXISTS {schema} CASCADE"))
        conn.commit()
        conn.close()
        engine.dispose()
