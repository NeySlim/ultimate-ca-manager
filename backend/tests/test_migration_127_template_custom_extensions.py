"""Migration 127 adds the custom extensions column to templates, idempotently."""
import importlib
import os
import sqlite3

import pytest
from sqlalchemy import create_engine, inspect, text

from models.certificate_template import CertificateTemplate

PG_URL = os.getenv('UCM_TEST_PG_URL')
TABLE = CertificateTemplate.__tablename__


def _migration():
    return importlib.import_module('migrations.127_certificate_template_custom_extensions')


def test_the_model_holds_the_column():
    assert 'custom_extensions' in {c.name for c in CertificateTemplate.__table__.columns}


def test_sqlite_adds_the_column_and_keeps_rows():
    conn = sqlite3.connect(':memory:')
    conn.execute(f"CREATE TABLE {TABLE} (id INTEGER PRIMARY KEY, name TEXT)")
    conn.execute(f"INSERT INTO {TABLE} (name) VALUES ('web')")
    _migration().upgrade(conn)
    _migration().upgrade(conn)
    types = {row[1]: row[2] for row in conn.execute(f"PRAGMA table_info({TABLE})")}
    assert types['custom_extensions'] == 'TEXT'
    assert conn.execute(f"SELECT name, custom_extensions FROM {TABLE}").fetchall() == [('web', None)]


def test_sqlite_without_the_table_is_a_no_op():
    conn = sqlite3.connect(':memory:')
    _migration().upgrade(conn)
    assert conn.execute("SELECT name FROM sqlite_master").fetchall() == []


def _pg_schema(suffix):
    schema = f"migtest_127{suffix}_{os.getenv('PYTEST_XDIST_WORKER', 'main')}"
    engine = create_engine(PG_URL)
    conn = engine.connect()
    conn.execute(text(f"DROP SCHEMA IF EXISTS {schema} CASCADE"))
    conn.execute(text(f"CREATE SCHEMA {schema}"))
    conn.execute(text(f"SET search_path TO {schema}"))
    return schema, engine, conn


def _pg_drop(schema, engine, conn):
    conn.rollback()
    conn.execute(text(f"DROP SCHEMA IF EXISTS {schema} CASCADE"))
    conn.commit()
    conn.close()
    engine.dispose()


@pytest.mark.postgres
@pytest.mark.skipif(not PG_URL, reason='UCM_TEST_PG_URL not set')
def test_postgres_adds_the_column_and_keeps_rows():
    schema, engine, conn = _pg_schema('')
    try:
        conn.execute(text(f"CREATE TABLE {TABLE} (id SERIAL PRIMARY KEY, name TEXT)"))
        conn.execute(text(f"INSERT INTO {TABLE} (name) VALUES ('web')"))
        _migration().upgrade(conn)
        _migration().upgrade(conn)
        types = {c['name']: str(c['type']) for c in inspect(conn).get_columns(TABLE, schema=schema)}
        assert types['custom_extensions'] == 'TEXT'
        assert conn.execute(text(f"SELECT name, custom_extensions FROM {TABLE}")).fetchall() == [('web', None)]
    finally:
        _pg_drop(schema, engine, conn)


@pytest.mark.postgres
@pytest.mark.skipif(not PG_URL, reason='UCM_TEST_PG_URL not set')
def test_postgres_without_the_table_is_a_no_op():
    schema, engine, conn = _pg_schema('e')
    try:
        _migration().upgrade(conn)
        assert inspect(conn).get_table_names(schema=schema) == []
    finally:
        _pg_drop(schema, engine, conn)
