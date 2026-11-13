"""Migration 158 adds who confirmed a CA's parent by hand and when, NULL on every existing CA."""
import importlib
import os
import sqlite3

import pytest
from sqlalchemy import create_engine, inspect, text

TABLE = 'certificate_authorities'
PG_URL = os.getenv('UCM_TEST_PG_URL')
NEW_COLUMNS = {'parent_confirmed_by', 'parent_confirmed_at'}


def _migration():
    return importlib.import_module('migrations._from_2_254.158_ca_parent_confirmation')


def test_the_table_is_the_model_s():
    from models import CA
    assert CA.__tablename__ == TABLE
    assert NEW_COLUMNS <= set(CA.__table__.columns.keys())


def test_sqlite_adds_the_columns_without_changing_a_ca_and_is_idempotent():
    conn = sqlite3.connect(':memory:')
    conn.execute(f"CREATE TABLE {TABLE} (id INTEGER PRIMARY KEY, caref VARCHAR(36))")
    conn.execute(f"INSERT INTO {TABLE} (caref) VALUES ('parent')")
    _migration().upgrade(conn)
    _migration().upgrade(conn)
    columns = {row[1] for row in conn.execute(f'PRAGMA table_info({TABLE})')}
    assert NEW_COLUMNS <= columns
    assert conn.execute(f"SELECT caref, parent_confirmed_by, parent_confirmed_at FROM {TABLE}"
                        ).fetchall() == [('parent', None, None)]


def test_sqlite_without_the_table_is_a_no_op():
    conn = sqlite3.connect(':memory:')
    _migration().upgrade(conn)
    assert conn.execute("SELECT count(*) FROM sqlite_master").fetchone()[0] == 0


@pytest.mark.postgres
@pytest.mark.skipif(not PG_URL, reason='UCM_TEST_PG_URL not set')
def test_postgres_adds_the_columns_without_changing_a_ca():
    from tests.conftest import pg_bench_exclusive
    with pg_bench_exclusive():
        _postgres_round()


def _postgres_round():
    schema = f"migtest_158_{os.getenv('PYTEST_XDIST_WORKER', 'main')}"
    engine = create_engine(PG_URL)
    conn = engine.connect()
    try:
        conn.execute(text(f"DROP SCHEMA IF EXISTS {schema} CASCADE"))
        conn.execute(text(f"CREATE SCHEMA {schema}"))
        conn.execute(text(f"SET search_path TO {schema}"))
        conn.execute(text(f"CREATE TABLE {TABLE} (id SERIAL PRIMARY KEY, caref VARCHAR(36))"))
        conn.execute(text(f"INSERT INTO {TABLE} (caref) VALUES ('parent')"))
        _migration().upgrade(conn)
        _migration().upgrade(conn)
        columns = {c['name']: c for c in inspect(conn).get_columns(TABLE, schema=schema)}
        assert NEW_COLUMNS <= set(columns)
        assert columns['parent_confirmed_by']['type'].length == 80
        assert conn.execute(text(f"SELECT caref, parent_confirmed_by, parent_confirmed_at FROM {TABLE}")
                            ).fetchall() == [('parent', None, None)]
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
    assert NEW_COLUMNS <= columns
