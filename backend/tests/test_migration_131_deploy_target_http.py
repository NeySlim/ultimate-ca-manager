"""Migration 131 adds the HTTP columns to deploy targets."""
import importlib
import os
import sqlite3

import pytest
from sqlalchemy import create_engine, inspect, text

TABLE = 'deploy_targets'
PG_URL = os.getenv('UCM_TEST_PG_URL')
NEW_COLUMNS = {'kind', 'url', 'http_method', 'http_headers', 'body_template', 'tls_ca_pem',
               'allow_private_key'}


def _migration():
    return importlib.import_module('migrations.131_deploy_target_http')


def test_sqlite_adds_the_columns_defaults_existing_targets_to_ssh_and_is_idempotent():
    conn = sqlite3.connect(':memory:')
    conn.execute(f"""CREATE TABLE {TABLE} (
        id INTEGER PRIMARY KEY, name VARCHAR(120) NOT NULL, host VARCHAR(255) NOT NULL,
        port INTEGER NOT NULL, username VARCHAR(120) NOT NULL, private_key TEXT NOT NULL)""")
    conn.execute(f"INSERT INTO {TABLE} VALUES (1, 'web', 'web.example.test', 22, 'deploy', 'k')")
    _migration().upgrade(conn)
    _migration().upgrade(conn)
    columns = {row[1] for row in conn.execute(f'PRAGMA table_info({TABLE})')}
    assert NEW_COLUMNS <= columns
    assert conn.execute(f"SELECT kind, allow_private_key, url FROM {TABLE}").fetchone() == ('ssh', 0, None)


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
    schema = f"migtest_131_{os.getenv('PYTEST_XDIST_WORKER', 'main')}"
    engine = create_engine(PG_URL)
    conn = engine.connect()
    try:
        conn.execute(text(f"DROP SCHEMA IF EXISTS {schema} CASCADE"))
        conn.execute(text(f"CREATE SCHEMA {schema}"))
        conn.execute(text(f"SET search_path TO {schema}"))
        conn.execute(text(f"""CREATE TABLE {TABLE} (
            id SERIAL PRIMARY KEY, name VARCHAR(120) NOT NULL, host VARCHAR(255) NOT NULL,
            port INTEGER NOT NULL, username VARCHAR(120) NOT NULL, private_key TEXT NOT NULL)"""))
        conn.execute(text(f"INSERT INTO {TABLE} (name, host, port, username, private_key) "
                          "VALUES ('web', 'web.example.test', 22, 'deploy', 'k')"))
        _migration().upgrade(conn)
        _migration().upgrade(conn)
        columns = {c['name']: c for c in inspect(conn).get_columns(TABLE, schema=schema)}
        assert NEW_COLUMNS <= set(columns)
        assert columns['kind']['type'].length == 8
        assert conn.execute(text(f"SELECT kind, allow_private_key, url FROM {TABLE}")
                            ).fetchall() == [('ssh', False, None)]
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
