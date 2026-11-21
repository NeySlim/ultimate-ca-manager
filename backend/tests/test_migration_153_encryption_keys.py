"""Migration 153: encryption_keys, both backends, idempotent."""
import importlib
import os
import sqlite3

import pytest
from sqlalchemy import create_engine, inspect, text

PG_URL = os.getenv('UCM_TEST_PG_URL')
NODES_143 = ("CREATE TABLE cluster_nodes (node_id VARCHAR(255) NOT NULL PRIMARY KEY, "
             "started_at TIMESTAMP NOT NULL, heartbeat_at TIMESTAMP NOT NULL, "
             "is_leader BOOLEAN NOT NULL, version VARCHAR(32), pid INTEGER, "
             "command_seen INTEGER, restart_seen INTEGER)")


def _m153():
    return importlib.import_module('migrations._from_2_254.153_encryption_keys')


def test_sqlite_creates_the_table_and_is_idempotent():
    conn = sqlite3.connect(':memory:')
    conn.execute(NODES_143)
    conn.execute("INSERT INTO cluster_nodes VALUES ('n1', '2026-01-01', '2026-01-01', 1, '3.0', 42, 7, NULL)")
    for _ in range(2):
        _m153().upgrade(conn)
    conn.execute("INSERT INTO encryption_keys VALUES (2, 'active', 'abcdef0123456789', '1:x', "
                 "'2026-01-01', NULL)")
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute("INSERT INTO encryption_keys VALUES (2, 'previous', 'abcdef0123456789', NULL, "
                     "'2026-01-01', '2026-01-08')")
    assert conn.execute("SELECT command_seen FROM cluster_nodes").fetchall() == [(7,)]


def test_sqlite_creates_the_key_table_alone():
    conn = sqlite3.connect(':memory:')
    _m153().upgrade(conn)
    names = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
    assert 'encryption_keys' in names and 'cluster_nodes' not in names


@pytest.mark.postgres
@pytest.mark.skipif(not PG_URL, reason='UCM_TEST_PG_URL not set')
def test_postgres_creates_the_table_and_is_idempotent():
    from tests.conftest import pg_bench_exclusive
    with pg_bench_exclusive():
        _postgres_round()


def _postgres_round():
    schema = f"migtest_153_{os.getenv('PYTEST_XDIST_WORKER', 'main')}"
    engine = create_engine(PG_URL)
    conn = engine.connect()
    try:
        conn.execute(text(f"DROP SCHEMA IF EXISTS {schema} CASCADE"))
        conn.execute(text(f"CREATE SCHEMA {schema}"))
        conn.execute(text(f"SET search_path TO {schema}"))
        conn.execute(text(NODES_143))
        conn.execute(text("INSERT INTO cluster_nodes VALUES ('n1', now(), now(), TRUE, '3.0', 42, 7, NULL)"))
        for _ in range(2):
            _m153().upgrade(conn)
        conn.execute(text("INSERT INTO encryption_keys VALUES (1, 'previous', 'abcdef0123456789', "
                          "NULL, now(), now())"))
        assert conn.execute(text("SELECT command_seen FROM cluster_nodes")).fetchall() == [(7,)]
        cols = {c['name']: c for c in inspect(conn).get_columns('encryption_keys', schema=schema)}
        assert cols['wrapped']['nullable'] is True and cols['kek_id']['nullable'] is False
        assert cols['retire_after']['nullable'] is True
    finally:
        conn.rollback()
        conn.execute(text(f"DROP SCHEMA IF EXISTS {schema} CASCADE"))
        conn.commit()
        conn.close()
        engine.dispose()


def test_the_app_schema_matches_the_migrations(app):
    from models import db
    with app.app_context():
        insp = inspect(db.engine)
        assert {'version', 'state', 'kek_id', 'wrapped', 'created_at', 'retire_after'} == {
            c['name'] for c in insp.get_columns('encryption_keys')}
