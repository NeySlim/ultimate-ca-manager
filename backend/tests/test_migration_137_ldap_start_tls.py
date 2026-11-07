"""Migration 137 adds pro_sso_providers.ldap_start_tls, off for existing providers."""
import importlib
import os
import sqlite3

import pytest
from sqlalchemy import create_engine, inspect, text

TABLE = 'pro_sso_providers'
PG_URL = os.getenv('UCM_TEST_PG_URL')


def _migration():
    return importlib.import_module('migrations.137_ldap_start_tls')


def test_sqlite_adds_the_column_off_and_is_idempotent():
    conn = sqlite3.connect(':memory:')
    conn.execute(f"CREATE TABLE {TABLE} (id INTEGER PRIMARY KEY, name VARCHAR(100), "
                 "provider_type VARCHAR(50), ldap_use_ssl BOOLEAN)")
    conn.execute(f"INSERT INTO {TABLE} VALUES (1, 'dir', 'ldap', 0)")
    _migration().upgrade(conn)
    _migration().upgrade(conn)
    assert conn.execute(f"SELECT ldap_start_tls FROM {TABLE}").fetchone() == (0,)


def test_sqlite_turns_a_missing_or_unknown_default_role_into_viewer():
    """Before this release a NULL or unknown default role meant viewer."""
    conn = sqlite3.connect(':memory:')
    conn.execute(f"CREATE TABLE {TABLE} (id INTEGER PRIMARY KEY, name VARCHAR(100), "
                 "provider_type VARCHAR(50), ldap_use_ssl BOOLEAN, default_role VARCHAR(50))")
    conn.executemany(f"INSERT INTO {TABLE} VALUES (?, ?, 'oauth2', 0, ?)",
                     [(1, 'a', None), (2, 'b', 'root'), (3, 'c', 'auditor'), (4, 'd', '')])
    _migration().upgrade(conn)
    rows = conn.execute(f"SELECT id, default_role FROM {TABLE} ORDER BY id").fetchall()
    assert rows == [(1, 'viewer'), (2, 'viewer'), (3, 'auditor'), (4, 'viewer')]
    conn.execute(f"UPDATE {TABLE} SET default_role = NULL WHERE id = 3")
    _migration().upgrade(conn)  # a later explicit choice survives a rerun
    assert conn.execute(f"SELECT default_role FROM {TABLE} WHERE id = 3").fetchone() == (None,)


def test_sqlite_without_the_table_is_a_no_op():
    conn = sqlite3.connect(':memory:')
    _migration().upgrade(conn)
    assert conn.execute("SELECT count(*) FROM sqlite_master").fetchone()[0] == 0


@pytest.mark.postgres
@pytest.mark.skipif(not PG_URL, reason='UCM_TEST_PG_URL not set')
def test_postgres_adds_the_column_and_keeps_rows():
    from tests.conftest import pg_bench_exclusive
    with pg_bench_exclusive():
        _postgres_round()


def _postgres_round():
    schema = f"migtest_137_{os.getenv('PYTEST_XDIST_WORKER', 'main')}"
    engine = create_engine(PG_URL)
    conn = engine.connect()
    try:
        conn.execute(text(f"DROP SCHEMA IF EXISTS {schema} CASCADE"))
        conn.execute(text(f"CREATE SCHEMA {schema}"))
        conn.execute(text(f"SET search_path TO {schema}"))
        conn.execute(text(f"CREATE TABLE {TABLE} (id SERIAL PRIMARY KEY, name VARCHAR(100), "
                          "provider_type VARCHAR(50), ldap_use_ssl BOOLEAN, default_role VARCHAR(50))"))
        conn.execute(text(f"INSERT INTO {TABLE} (name, provider_type, ldap_use_ssl, default_role) "
                          "VALUES ('dir', 'ldap', FALSE, NULL), ('x', 'ldap', FALSE, 'root'), "
                          "('y', 'ldap', FALSE, 'auditor')"))
        _migration().upgrade(conn)
        _migration().upgrade(conn)
        columns = {c['name']: c for c in inspect(conn).get_columns(TABLE, schema=schema)}
        assert columns['ldap_start_tls']['nullable'] is False
        assert conn.execute(text(f"SELECT ldap_start_tls, default_role FROM {TABLE} ORDER BY id")
                            ).fetchall() == [(False, 'viewer'), (False, 'viewer'), (False, 'auditor')]
    finally:
        conn.rollback()
        conn.execute(text(f"DROP SCHEMA IF EXISTS {schema} CASCADE"))
        conn.commit()
        conn.close()
        engine.dispose()


def test_the_app_schema_carries_the_column(app):
    from models import db
    with app.app_context():
        columns = {c['name'] for c in inspect(db.engine).get_columns(TABLE)}
    assert 'ldap_start_tls' in columns
