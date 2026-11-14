"""Migration 145: AuthnRequest rows get a next_path column, both backends."""
import importlib.util
import os
import sqlite3
import uuid

import pytest

TABLE = ('CREATE TABLE pro_sso_saml_message_ids (id INTEGER PRIMARY KEY, kind VARCHAR(16) NOT NULL, '
         'message_id VARCHAR(256) NOT NULL, provider_id INTEGER NOT NULL, expires_at TIMESTAMP NOT NULL)')
ROW = ("INSERT INTO pro_sso_saml_message_ids (id, kind, message_id, provider_id, expires_at) "
       "VALUES (1, 'request', '_r1', 1, '2030-01-01 00:00:00')")


def _migration():
    path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                        'migrations', '_from_2_254', '145_saml_request_next_path.py')
    spec = importlib.util.spec_from_file_location('m145', path)
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
    assert conn.execute('SELECT message_id, next_path FROM pro_sso_saml_message_ids').fetchall() == [('_r1', None)]
    conn.execute("UPDATE pro_sso_saml_message_ids SET next_path = '/certificates'")


def test_sqlite_without_the_table_is_a_no_op():
    conn = sqlite3.connect(':memory:')
    _migration().upgrade(conn)
    assert conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall() == []


@pytest.mark.postgres
@pytest.mark.skipif(not os.getenv('UCM_TEST_PG_URL'), reason='UCM_TEST_PG_URL not set')
def test_postgresql_upgrade_adds_the_column_once():
    from sqlalchemy import create_engine, text
    schema = f"m145_{os.getenv('PYTEST_XDIST_WORKER', 'main')}_{uuid.uuid4().hex[:6]}"
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
            assert conn.execute(text('SELECT next_path FROM pro_sso_saml_message_ids')).scalar() is None
            conn.execute(text("UPDATE pro_sso_saml_message_ids SET next_path = :p"), {'p': '/c' * 256})
    finally:
        with engine.begin() as conn:
            conn.execute(text(f'DROP SCHEMA IF EXISTS {schema} CASCADE'))
        engine.dispose()
