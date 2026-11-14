"""Migration 146: ACME client orders get a replaced_certificates column, both backends."""
import importlib.util
import os
import sqlite3
import uuid

import pytest

TABLE = ('CREATE TABLE acme_client_orders (id INTEGER PRIMARY KEY, domains TEXT NOT NULL, '
         'certificate_id INTEGER)')
ROW = "INSERT INTO acme_client_orders (id, domains, certificate_id) VALUES (1, '[\"a.example\"]', 7)"
VALUE = '[{"certificate_id": 7, "serial": "12"}]'


def _migration():
    path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                        'migrations', '_from_2_254', '146_acme_order_replaced_certificates.py')
    spec = importlib.util.spec_from_file_location('m146', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_sqlite_upgrade_adds_the_column_once():
    migration = _migration()
    assert migration.pg_compatible is True
    conn = sqlite3.connect(':memory:')
    conn.execute(TABLE)
    conn.execute(ROW)
    migration.upgrade(conn)
    migration.upgrade(conn)
    assert conn.execute('SELECT certificate_id, replaced_certificates FROM acme_client_orders'
                        ).fetchall() == [(7, None)]
    conn.execute('UPDATE acme_client_orders SET replaced_certificates = ?', (VALUE,))


def test_sqlite_without_the_table_is_a_no_op():
    conn = sqlite3.connect(':memory:')
    _migration().upgrade(conn)
    assert conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall() == []


@pytest.mark.postgres
@pytest.mark.skipif(not os.getenv('UCM_TEST_PG_URL'), reason='UCM_TEST_PG_URL not set')
def test_postgresql_upgrade_adds_the_column_once():
    from sqlalchemy import create_engine, text
    schema = f"m146_{os.getenv('PYTEST_XDIST_WORKER', 'main')}_{uuid.uuid4().hex[:6]}"
    engine = create_engine(os.environ['UCM_TEST_PG_URL'])
    migration = _migration()
    try:
        with engine.begin() as conn:
            conn.execute(text(f'CREATE SCHEMA {schema}'))
            conn.execute(text(f'SET search_path TO {schema}'))
            conn.execute(text(TABLE))
            conn.execute(text(ROW))
        for _ in range(2):
            with engine.begin() as conn:
                conn.execute(text(f'SET search_path TO {schema}'))
                migration.upgrade(conn)
        with engine.begin() as conn:
            conn.execute(text(f'SET search_path TO {schema}'))
            assert conn.execute(text('SELECT replaced_certificates FROM acme_client_orders')).scalar() is None
            conn.execute(text('UPDATE acme_client_orders SET replaced_certificates = :v'), {'v': VALUE * 200})
    finally:
        with engine.begin() as conn:
            conn.execute(text(f'DROP SCHEMA IF EXISTS {schema} CASCADE'))
        engine.dispose()
