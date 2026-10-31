"""Migration 115 adds the related certificate pair columns and their index, idempotently."""
import importlib
import os
import sqlite3

import pytest
from sqlalchemy import create_engine, inspect, text

from models import Certificate

PG_URL = os.getenv('UCM_TEST_PG_URL')
TABLE = Certificate.__tablename__
INDEX = f'ix_{TABLE}_related_certificate_id'


def _migration():
    return importlib.import_module('migrations.115_related_certificates')


def test_the_index_name_is_the_one_the_model_creates():
    names = {index.name for index in Certificate.__table__.indexes}
    assert INDEX in names


def test_sqlite_adds_the_columns_and_the_index_and_keeps_rows():
    conn = sqlite3.connect(':memory:')
    conn.execute(f"CREATE TABLE {TABLE} (id INTEGER PRIMARY KEY, descr TEXT)")
    conn.execute(f"INSERT INTO {TABLE} (descr) VALUES ('a')")
    _migration().upgrade(conn)
    _migration().upgrade(conn)
    columns = {row[1]: row[2] for row in conn.execute(f"PRAGMA table_info({TABLE})")}
    assert columns['related_certificate_id'] == 'INTEGER'
    assert columns['hybrid_role'] == 'VARCHAR(16)'
    indexes = {row[1] for row in conn.execute(f"PRAGMA index_list({TABLE})")}
    assert INDEX in indexes
    assert conn.execute(f"SELECT descr, related_certificate_id, hybrid_role FROM {TABLE}"
                        ).fetchall() == [('a', None, None)]


def test_sqlite_without_the_table_is_a_no_op():
    conn = sqlite3.connect(':memory:')
    _migration().upgrade(conn)
    assert conn.execute("SELECT name FROM sqlite_master").fetchall() == []


@pytest.mark.postgres
@pytest.mark.skipif(not PG_URL, reason='UCM_TEST_PG_URL not set')
def test_postgres_adds_the_columns_and_the_index_and_keeps_rows():
    from tests.conftest import pg_bench_exclusive
    with pg_bench_exclusive():
        _postgres_round()


def _postgres_round():
    schema = f"migtest_115_{os.getenv('PYTEST_XDIST_WORKER', 'main')}"
    engine = create_engine(PG_URL)
    conn = engine.connect()
    try:
        conn.execute(text(f"DROP SCHEMA IF EXISTS {schema} CASCADE"))
        conn.execute(text(f"CREATE SCHEMA {schema}"))
        conn.execute(text(f"SET search_path TO {schema}"))
        conn.execute(text(f"CREATE TABLE {TABLE} (id SERIAL PRIMARY KEY, descr TEXT)"))
        conn.execute(text(f"INSERT INTO {TABLE} (descr) VALUES ('a')"))
        _migration().upgrade(conn)
        _migration().upgrade(conn)
        inspector = inspect(conn)
        columns = {c['name']: c for c in inspector.get_columns(TABLE, schema=schema)}
        assert str(columns['related_certificate_id']['type']) == 'INTEGER'
        assert columns['hybrid_role']['type'].length == 16
        assert INDEX in {i['name'] for i in inspector.get_indexes(TABLE, schema=schema)}
        assert conn.execute(text(f"SELECT descr, related_certificate_id, hybrid_role FROM {TABLE}")
                            ).fetchall() == [('a', None, None)]
    finally:
        conn.rollback()
        conn.execute(text(f"DROP SCHEMA IF EXISTS {schema} CASCADE"))
        conn.commit()
        conn.close()
        engine.dispose()


def test_the_app_schema_carries_the_columns(app):
    from models import db
    with app.app_context():
        columns = {c['name'] for c in inspect(db.engine).get_columns(TABLE)}
    assert {'related_certificate_id', 'hybrid_role'} <= columns
