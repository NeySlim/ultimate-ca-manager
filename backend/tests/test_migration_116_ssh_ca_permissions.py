"""Migration 116 grants X:ssh_cas wherever X:ssh is stored, idempotently."""
import importlib
import json
import os
import sqlite3

import pytest
from sqlalchemy import create_engine, text

from models.api_key import APIKey
from models.group import Group
from models.rbac import CustomRole

PG_URL = os.getenv('UCM_TEST_PG_URL')
TABLES = (CustomRole.__tablename__, Group.__tablename__, APIKey.__tablename__)

# (stored permissions, what they read as after the upgrade)
CASES = [
    (['read:ssh'], ['read:ssh', 'read:ssh_cas']),
    (['read:certificates', 'write:ssh', 'delete:ssh'],
     ['read:certificates', 'write:ssh', 'write:ssh_cas', 'delete:ssh', 'delete:ssh_cas']),
    (['write:ssh', 'write:ssh_cas'], ['write:ssh', 'write:ssh_cas']),
    (['read:ssh_cas'], ['read:ssh_cas']),
    (['*'], ['*']),
    (['read:*', 'write:*'], ['read:*', 'write:*']),
    ([], []),
]


def _migration():
    return importlib.import_module('migrations.116_ssh_ca_permissions')


def _read(raw):
    return json.loads(raw) if isinstance(raw, str) else raw


def test_the_migration_names_the_model_tables():
    assert set(_migration().TABLES) == set(TABLES)


def test_sqlite_widens_every_table_and_runs_twice():
    conn = sqlite3.connect(':memory:')
    for table in TABLES:
        conn.execute(f"CREATE TABLE {table} (id INTEGER PRIMARY KEY, permissions TEXT)")
        conn.executemany(f"INSERT INTO {table} (id, permissions) VALUES (?, ?)",
                         [(i, json.dumps(stored)) for i, (stored, _) in enumerate(CASES, 1)])
        conn.execute(f"INSERT INTO {table} (id, permissions) VALUES (99, NULL)")
    # A group stored as JSON text of JSON text before migration 104
    conn.execute(f"INSERT INTO {Group.__tablename__} (id, permissions) VALUES (98, ?)",
                 (json.dumps(json.dumps(['read:ssh'])),))
    _migration().upgrade(conn)
    _migration().upgrade(conn)
    for table in TABLES:
        rows = dict(conn.execute(f"SELECT id, permissions FROM {table}"))
        for i, (_, wanted) in enumerate(CASES, 1):
            assert _read(rows[i]) == wanted, (table, i)
        assert rows[99] is None
    assert _read(conn.execute(f"SELECT permissions FROM {Group.__tablename__} WHERE id = 98")
                 .fetchone()[0]) == ['read:ssh', 'read:ssh_cas']


def test_sqlite_without_the_tables_does_nothing():
    conn = sqlite3.connect(':memory:')
    _migration().upgrade(conn)


@pytest.mark.postgres
@pytest.mark.skipif(not PG_URL, reason='UCM_TEST_PG_URL not set')
def test_postgres_widens_json_and_text_columns_and_runs_twice():
    schema = f"migtest_116_{os.getenv('PYTEST_XDIST_WORKER', 'main')}"
    engine = create_engine(PG_URL)
    conn = engine.connect()
    column = {CustomRole.__tablename__: 'JSON', Group.__tablename__: 'JSONB', APIKey.__tablename__: 'TEXT'}
    try:
        conn.execute(text(f"DROP SCHEMA IF EXISTS {schema} CASCADE"))
        conn.execute(text(f"CREATE SCHEMA {schema}"))
        conn.execute(text(f"SET search_path TO {schema}"))
        for table in TABLES:
            conn.execute(text(f"CREATE TABLE {table} (id INTEGER PRIMARY KEY, "
                              f"permissions {column[table]})"))
            cast = f"CAST(:p AS {column[table]})" if column[table] != 'TEXT' else ':p'
            for i, (stored, _) in enumerate(CASES, 1):
                conn.execute(text(f"INSERT INTO {table} (id, permissions) VALUES (:i, {cast})"),
                             {'i': i, 'p': json.dumps(stored)})
        _migration().upgrade(conn)
        _migration().upgrade(conn)
        for table in TABLES:
            rows = dict(conn.execute(text(f"SELECT id, permissions FROM {table}")).fetchall())
            for i, (_, wanted) in enumerate(CASES, 1):
                assert _read(rows[i]) == wanted, (table, i)
    finally:
        conn.rollback()
        conn.execute(text(f"DROP SCHEMA IF EXISTS {schema} CASCADE"))
        conn.commit()
        conn.close()
        engine.dispose()
