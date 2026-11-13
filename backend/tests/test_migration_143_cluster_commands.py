"""Migration 143: cluster_commands and cluster_nodes.command_seen on both backends, idempotent."""
import importlib
import os
import sqlite3

import pytest
from sqlalchemy import create_engine, inspect, text

PG_URL = os.getenv('UCM_TEST_PG_URL')
NODES_141 = ("CREATE TABLE cluster_nodes (node_id VARCHAR(255) NOT NULL PRIMARY KEY, "
             "started_at TIMESTAMP NOT NULL, heartbeat_at TIMESTAMP NOT NULL, "
             "is_leader BOOLEAN NOT NULL, version VARCHAR(32), pid INTEGER)")


def _migration():
    return importlib.import_module('migrations._from_2_254.143_cluster_commands')


def test_sqlite_creates_the_table_and_column_and_is_idempotent():
    conn = sqlite3.connect(':memory:')
    conn.execute(NODES_141)
    conn.execute("INSERT INTO cluster_nodes VALUES ('n1', '2026-01-01', '2026-01-01', 1, '3.0', 42)")
    _migration().upgrade(conn)
    _migration().upgrade(conn)
    conn.execute("INSERT INTO cluster_commands (kind, payload, created_at, created_by) "
                 "VALUES ('restart', NULL, '2026-01-01', 'n1')")
    assert conn.execute("SELECT id, node_id FROM cluster_commands").fetchall() == [(1, None)]
    assert conn.execute("SELECT command_seen, restart_seen FROM cluster_nodes").fetchall() == [(None, None)]


def test_sqlite_without_the_registry_still_creates_the_commands():
    conn = sqlite3.connect(':memory:')
    _migration().upgrade(conn)
    names = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
    assert 'cluster_commands' in names and 'cluster_nodes' not in names


@pytest.mark.postgres
@pytest.mark.skipif(not PG_URL, reason='UCM_TEST_PG_URL not set')
def test_postgres_creates_the_table_and_column_and_is_idempotent():
    from tests.conftest import pg_bench_exclusive
    with pg_bench_exclusive():
        _postgres_round()


def _postgres_round():
    schema = f"migtest_143_{os.getenv('PYTEST_XDIST_WORKER', 'main')}"
    engine = create_engine(PG_URL)
    conn = engine.connect()
    try:
        conn.execute(text(f"DROP SCHEMA IF EXISTS {schema} CASCADE"))
        conn.execute(text(f"CREATE SCHEMA {schema}"))
        conn.execute(text(f"SET search_path TO {schema}"))
        conn.execute(text(NODES_141))
        conn.execute(text("INSERT INTO cluster_nodes VALUES ('n1', now(), now(), TRUE, '3.0', 42)"))
        _migration().upgrade(conn)
        _migration().upgrade(conn)
        new_id = conn.execute(text("INSERT INTO cluster_commands (kind, created_at) "
                                   "VALUES ('restart', now()) RETURNING id")).scalar()
        assert new_id == 1
        assert conn.execute(text("SELECT command_seen, restart_seen FROM cluster_nodes")).fetchall() \
            == [(None, None)]
        cols = {c['name']: c for c in inspect(conn).get_columns('cluster_commands', schema=schema)}
        assert cols['kind']['nullable'] is False and cols['node_id']['nullable'] is True
    finally:
        conn.rollback()
        conn.execute(text(f"DROP SCHEMA IF EXISTS {schema} CASCADE"))
        conn.commit()
        conn.close()
        engine.dispose()


def test_the_app_schema_matches_the_migration(app):
    from models import db
    with app.app_context():
        insp = inspect(db.engine)
        assert {'id', 'kind', 'payload', 'created_at', 'created_by', 'node_id'} <= {
            c['name'] for c in insp.get_columns('cluster_commands')}
        assert {'command_seen', 'restart_seen'} <= {c['name'] for c in insp.get_columns('cluster_nodes')}
