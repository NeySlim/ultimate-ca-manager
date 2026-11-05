"""Migration 123 adds the pending key, the renewal lease and the renewal link to ACME client
orders, idempotently."""
import importlib
import os
import sqlite3

import pytest
from sqlalchemy import create_engine, inspect, text

from models.acme_models import AcmeClientOrder

PG_URL = os.getenv('UCM_TEST_PG_URL')
TABLE = AcmeClientOrder.__tablename__
COLUMNS = {'pending_key', 'renewal_claimed_at', 'renewal_of_order_id'}


def _migration():
    return importlib.import_module('migrations.123_acme_client_order_pending_key_lease')


def test_the_model_holds_the_columns_the_migration_adds():
    assert COLUMNS <= {c.name for c in AcmeClientOrder.__table__.columns}


def test_sqlite_adds_the_columns_and_keeps_rows():
    conn = sqlite3.connect(':memory:')
    conn.execute(f"CREATE TABLE {TABLE} (id INTEGER PRIMARY KEY, domains TEXT)")
    conn.execute(f"INSERT INTO {TABLE} (domains) VALUES ('[\"a.example\"]')")
    _migration().upgrade(conn)
    _migration().upgrade(conn)
    types = {row[1]: row[2] for row in conn.execute(f"PRAGMA table_info({TABLE})")}
    assert (types['pending_key'], types['renewal_claimed_at']) == ('TEXT', 'DATETIME')
    assert conn.execute(f"SELECT domains, pending_key, renewal_claimed_at FROM {TABLE}"
                        ).fetchall() == [('["a.example"]', None, None)]
    assert types['renewal_of_order_id'] == 'INTEGER'
    assert any(row[2] == 'renewal_of_order_id' for row in conn.execute(f"PRAGMA index_list({TABLE})")
               for row in conn.execute(f"PRAGMA index_info({row[1]})"))
    # The link goes with the order it names
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute(f"INSERT INTO {TABLE} (id, domains, renewal_of_order_id) VALUES (2, 'x', 1)")
    conn.execute(f"DELETE FROM {TABLE} WHERE id = 1")
    assert conn.execute(f"SELECT renewal_of_order_id FROM {TABLE}").fetchall() == [(None,)]


def test_sqlite_without_the_table_is_a_no_op():
    conn = sqlite3.connect(':memory:')
    _migration().upgrade(conn)
    assert conn.execute("SELECT name FROM sqlite_master").fetchall() == []


@pytest.mark.postgres
@pytest.mark.skipif(not PG_URL, reason='UCM_TEST_PG_URL not set')
def test_postgres_adds_the_columns_and_keeps_rows():
    schema = f"migtest_123_{os.getenv('PYTEST_XDIST_WORKER', 'main')}"
    engine = create_engine(PG_URL)
    conn = engine.connect()
    try:
        conn.execute(text(f"DROP SCHEMA IF EXISTS {schema} CASCADE"))
        conn.execute(text(f"CREATE SCHEMA {schema}"))
        conn.execute(text(f"SET search_path TO {schema}"))
        conn.execute(text(f"CREATE TABLE {TABLE} (id SERIAL PRIMARY KEY, domains TEXT)"))
        conn.execute(text(f"INSERT INTO {TABLE} (domains) VALUES ('[\"a.example\"]')"))
        _migration().upgrade(conn)
        _migration().upgrade(conn)
        types = {c['name']: str(c['type']) for c in inspect(conn).get_columns(TABLE, schema=schema)}
        assert (types['pending_key'], types['renewal_claimed_at']) == ('TEXT', 'TIMESTAMP')
        conn.execute(text(f"UPDATE {TABLE} SET renewal_claimed_at = now()"))
        assert conn.execute(text(f"SELECT domains, pending_key FROM {TABLE}")
                            ).fetchall() == [('["a.example"]', None)]
        assert types['renewal_of_order_id'] == 'INTEGER'
        assert any(i['column_names'] == ['renewal_of_order_id']
                   for i in inspect(conn).get_indexes(TABLE, schema=schema))
        first = conn.execute(text(f"SELECT id FROM {TABLE}")).scalar()
        conn.execute(text(f"INSERT INTO {TABLE} (domains, renewal_of_order_id) VALUES ('x', :p)"), {'p': first})
        conn.execute(text(f"DELETE FROM {TABLE} WHERE id = :p"), {'p': first})
        assert conn.execute(text(f"SELECT renewal_of_order_id FROM {TABLE}")).fetchall() == [(None,)]
    finally:
        conn.rollback()
        conn.execute(text(f"DROP SCHEMA IF EXISTS {schema} CASCADE"))
        conn.commit()
        conn.close()
        engine.dispose()


@pytest.mark.postgres
@pytest.mark.skipif(not PG_URL, reason='UCM_TEST_PG_URL not set')
def test_postgres_without_the_table_is_a_no_op():
    schema = f"migtest_123e_{os.getenv('PYTEST_XDIST_WORKER', 'main')}"
    engine = create_engine(PG_URL)
    conn = engine.connect()
    try:
        conn.execute(text(f"DROP SCHEMA IF EXISTS {schema} CASCADE"))
        conn.execute(text(f"CREATE SCHEMA {schema}"))
        conn.execute(text(f"SET search_path TO {schema}"))
        _migration().upgrade(conn)
        assert inspect(conn).get_table_names(schema=schema) == []
    finally:
        conn.rollback()
        conn.execute(text(f"DROP SCHEMA IF EXISTS {schema} CASCADE"))
        conn.commit()
        conn.close()
        engine.dispose()
