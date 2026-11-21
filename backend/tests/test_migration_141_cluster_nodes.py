"""Migration 141: cluster_nodes (with kek_fingerprint and instance_token), scheduler_requests and
discovery_scan_runs.node_id, on both backends and idempotent (the tables stay unused outside HA)."""
import importlib
import os
import sqlite3

import pytest
from sqlalchemy import create_engine, inspect, text

PG_URL = os.getenv('UCM_TEST_PG_URL')
RUNS = 'discovery_scan_runs'


def _migration():
    return importlib.import_module('migrations._from_2_254.141_cluster_nodes')


def test_sqlite_creates_the_tables_and_column_and_is_idempotent():
    conn = sqlite3.connect(':memory:')
    conn.execute(f"CREATE TABLE {RUNS} (id INTEGER PRIMARY KEY, status VARCHAR(32))")
    conn.execute(f"INSERT INTO {RUNS} (status) VALUES ('running')")
    _migration().upgrade(conn)
    _migration().upgrade(conn)
    conn.execute("INSERT INTO cluster_nodes (node_id, started_at, heartbeat_at, is_leader, version, pid, "
                 "package_family) VALUES ('n1', '2026-01-01', '2026-01-01', 1, '3.0', 42, 'rpm-el9')")
    assert conn.execute("SELECT kek_fingerprint, instance_token FROM cluster_nodes").fetchall() == [
        (None, None)]
    conn.execute("INSERT INTO scheduler_requests (task_name, requested_at, requested_by) "
                 "VALUES ('t', '2026-01-01', 'n1')")
    assert conn.execute(f"SELECT status, node_id FROM {RUNS}").fetchall() == [('running', None)]
    assert conn.execute("SELECT taken_at FROM scheduler_requests").fetchall() == [(None,)]


def test_sqlite_adds_the_package_family_to_a_registry_created_without_it():
    conn = sqlite3.connect(':memory:')
    conn.execute("CREATE TABLE cluster_nodes (node_id VARCHAR(255) NOT NULL PRIMARY KEY, "
                 "started_at TIMESTAMP NOT NULL, heartbeat_at TIMESTAMP NOT NULL, "
                 "is_leader BOOLEAN NOT NULL DEFAULT 0, version VARCHAR(32), pid INTEGER)")
    conn.execute("INSERT INTO cluster_nodes (node_id, started_at, heartbeat_at) VALUES ('n1', 'x', 'x')")
    _migration().upgrade(conn)
    _migration().upgrade(conn)
    assert conn.execute("SELECT node_id, package_family, kek_fingerprint, instance_token "
                        "FROM cluster_nodes").fetchall() == [('n1', None, None, None)]


def test_sqlite_without_the_scan_table_still_creates_the_registry():
    conn = sqlite3.connect(':memory:')
    _migration().upgrade(conn)
    names = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
    assert {'cluster_nodes', 'scheduler_requests'} <= names and RUNS not in names


@pytest.mark.postgres
@pytest.mark.skipif(not PG_URL, reason='UCM_TEST_PG_URL not set')
def test_postgres_creates_the_tables_and_column_and_is_idempotent():
    from tests.conftest import pg_bench_exclusive
    with pg_bench_exclusive():
        _postgres_round()


def _postgres_round():
    schema = f"migtest_141_{os.getenv('PYTEST_XDIST_WORKER', 'main')}"
    engine = create_engine(PG_URL)
    conn = engine.connect()
    try:
        conn.execute(text(f"DROP SCHEMA IF EXISTS {schema} CASCADE"))
        conn.execute(text(f"CREATE SCHEMA {schema}"))
        conn.execute(text(f"SET search_path TO {schema}"))
        conn.execute(text(f"CREATE TABLE {RUNS} (id SERIAL PRIMARY KEY, status VARCHAR(32))"))
        conn.execute(text(f"INSERT INTO {RUNS} (status) VALUES ('running')"))
        # A registry created before the column existed gets it
        conn.execute(text("CREATE TABLE cluster_nodes (node_id VARCHAR(255) NOT NULL PRIMARY KEY, "
                          "started_at TIMESTAMP NOT NULL, heartbeat_at TIMESTAMP NOT NULL, "
                          "is_leader BOOLEAN NOT NULL DEFAULT FALSE, version VARCHAR(32), pid INTEGER)"))
        _migration().upgrade(conn)
        _migration().upgrade(conn)
        conn.execute(text("INSERT INTO cluster_nodes (node_id, started_at, heartbeat_at, is_leader, "
                          "version, pid, package_family) VALUES ('n1', now(), now(), TRUE, '3.0', 42, 'deb')"))
        conn.execute(text("INSERT INTO scheduler_requests (task_name, requested_at, requested_by) "
                          "VALUES ('t', now(), 'n1')"))
        assert conn.execute(text(f"SELECT status, node_id FROM {RUNS}")).fetchall() == [('running', None)]
        nodes = {c['name']: c for c in inspect(conn).get_columns('cluster_nodes', schema=schema)}
        assert nodes['is_leader']['nullable'] is False
        assert nodes['kek_fingerprint']['nullable'] is True
        assert nodes['instance_token']['nullable'] is True
        assert conn.execute(text("SELECT taken_at FROM scheduler_requests")).fetchall() == [(None,)]
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
        assert {'node_id', 'started_at', 'heartbeat_at', 'is_leader', 'version', 'pid', 'package_family',
                'kek_fingerprint', 'instance_token'} <= {
            c['name'] for c in insp.get_columns('cluster_nodes')}
        assert {'id', 'task_name', 'requested_at', 'requested_by', 'taken_at'} <= {
            c['name'] for c in insp.get_columns('scheduler_requests')}
        assert 'node_id' in {c['name'] for c in insp.get_columns(RUNS)}
