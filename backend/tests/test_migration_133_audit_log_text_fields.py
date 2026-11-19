"""Migration 133 turns the free-text audit columns into TEXT on PostgreSQL."""
import importlib
import os
import sqlite3

import pytest
from sqlalchemy import Text, create_engine, inspect, text

TABLE = 'audit_logs'
PG_URL = os.getenv('UCM_TEST_PG_URL')
COLUMNS = {'username', 'resource_id', 'resource_name', 'user_agent'}


def _migration():
    return importlib.import_module('migrations.133_audit_log_text_fields')


def test_sqlite_is_left_alone():
    conn = sqlite3.connect(':memory:')
    conn.execute(f"CREATE TABLE {TABLE} (id INTEGER PRIMARY KEY, user_agent VARCHAR(255))")
    conn.execute(f"INSERT INTO {TABLE} VALUES (1, 'ua')")
    _migration().upgrade(conn)
    assert conn.execute(f"SELECT user_agent FROM {TABLE}").fetchone() == ('ua',)


@pytest.mark.postgres
@pytest.mark.skipif(not PG_URL, reason='UCM_TEST_PG_URL not set')
def test_postgres_widens_the_columns_and_keeps_rows():
    from tests.conftest import pg_bench_exclusive
    with pg_bench_exclusive():
        _postgres_round()


def _postgres_round():
    schema = f"migtest_133_{os.getenv('PYTEST_XDIST_WORKER', 'main')}"
    engine = create_engine(PG_URL)
    conn = engine.connect()
    try:
        conn.execute(text(f"DROP SCHEMA IF EXISTS {schema} CASCADE"))
        conn.execute(text(f"CREATE SCHEMA {schema}"))
        conn.execute(text(f"SET search_path TO {schema}"))
        conn.execute(text(f"""CREATE TABLE {TABLE} (
            id SERIAL PRIMARY KEY, username VARCHAR(80), action VARCHAR(100) NOT NULL,
            resource_id VARCHAR(100), resource_name VARCHAR(255), user_agent VARCHAR(255))"""))
        conn.execute(text(f"CREATE INDEX ix_{TABLE}_username ON {TABLE} (username)"))
        conn.execute(text(f"INSERT INTO {TABLE} (username, action) VALUES ('admin', 'login')"))
        _migration().upgrade(conn)
        _migration().upgrade(conn)
        columns = {c['name']: c for c in inspect(conn).get_columns(TABLE, schema=schema)}
        for name in COLUMNS:
            assert isinstance(columns[name]['type'], Text), name
        assert columns['action']['type'].length == 100
        conn.execute(text(f"INSERT INTO {TABLE} (username, action, user_agent, resource_id) "
                          f"VALUES ('admin', 'long', '{'u' * 300}', '{'1,' * 75}')"))
        assert conn.execute(text(f"SELECT count(*) FROM {TABLE}")).scalar() == 2
        assert 'ix_audit_logs_username' in {i['name'] for i in inspect(conn).get_indexes(TABLE, schema=schema)}
    finally:
        conn.rollback()
        conn.execute(text(f"DROP SCHEMA IF EXISTS {schema} CASCADE"))
        conn.commit()
        conn.close()
        engine.dispose()


def test_the_app_schema_has_text_columns_on_postgresql(app):
    from models import db
    with app.app_context():
        if db.engine.dialect.name != 'postgresql':
            pytest.skip('SQLite does not enforce VARCHAR lengths')
        columns = {c['name']: c for c in inspect(db.engine).get_columns(TABLE)}
    for name in COLUMNS:
        assert isinstance(columns[name]['type'], Text), name
