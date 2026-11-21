"""Migration 151 adds the left-behind state to deploy bindings."""
import importlib
import os
import sqlite3

import pytest
from sqlalchemy import create_engine, inspect, text

TABLE = 'deploy_bindings'
PG_URL = os.getenv('UCM_TEST_PG_URL')
NEW_COLUMNS = {'attention_reason', 'attention_successor_id'}


def _migration():
    return importlib.import_module('migrations._from_2_254.151_deploy_binding_attention')


def test_sqlite_adds_the_columns_keeps_rows_unflagged_and_is_idempotent():
    conn = sqlite3.connect(':memory:')
    conn.execute(f"""CREATE TABLE {TABLE} (
        id INTEGER PRIMARY KEY, target_id INTEGER NOT NULL, certificate_id INTEGER NOT NULL)""")
    conn.execute(f"INSERT INTO {TABLE} VALUES (1, 2, 3)")
    _migration().upgrade(conn)
    _migration().upgrade(conn)
    columns = {row[1] for row in conn.execute(f'PRAGMA table_info({TABLE})')}
    assert NEW_COLUMNS <= columns
    assert conn.execute(f"SELECT attention_reason, attention_successor_id FROM {TABLE}").fetchone() == (None, None)
    indexes = {row[1] for row in conn.execute(f'PRAGMA index_list({TABLE})')}
    assert 'ix_deploy_bindings_attention_successor_id' in indexes


def test_sqlite_without_the_table_is_a_no_op():
    conn = sqlite3.connect(':memory:')
    _migration().upgrade(conn)
    assert conn.execute("SELECT count(*) FROM sqlite_master").fetchone()[0] == 0


@pytest.mark.postgres
@pytest.mark.skipif(not PG_URL, reason='UCM_TEST_PG_URL not set')
def test_postgres_adds_the_columns_and_keeps_rows():
    from tests.conftest import pg_bench_exclusive
    with pg_bench_exclusive():
        _postgres_round()


def _postgres_round():
    schema = f"migtest_151_{os.getenv('PYTEST_XDIST_WORKER', 'main')}"
    engine = create_engine(PG_URL)
    conn = engine.connect()
    try:
        conn.execute(text(f"DROP SCHEMA IF EXISTS {schema} CASCADE"))
        conn.execute(text(f"CREATE SCHEMA {schema}"))
        conn.execute(text(f"SET search_path TO {schema}"))
        conn.execute(text(f"""CREATE TABLE {TABLE} (
            id SERIAL PRIMARY KEY, target_id INTEGER NOT NULL, certificate_id INTEGER NOT NULL)"""))
        conn.execute(text(f"INSERT INTO {TABLE} (target_id, certificate_id) VALUES (2, 3)"))
        _migration().upgrade(conn)
        _migration().upgrade(conn)
        columns = {c['name']: c for c in inspect(conn).get_columns(TABLE, schema=schema)}
        assert NEW_COLUMNS <= set(columns)
        assert columns['attention_reason']['type'].length == 40
        assert conn.execute(text(f"SELECT attention_reason, attention_successor_id FROM {TABLE}")
                            ).fetchall() == [(None, None)]
        indexes = {i['name'] for i in inspect(conn).get_indexes(TABLE, schema=schema)}
        assert 'ix_deploy_bindings_attention_successor_id' in indexes
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
