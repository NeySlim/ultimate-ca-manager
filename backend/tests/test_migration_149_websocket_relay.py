"""Migration 149: websocket_relay on both backends, idempotent, ids never reused."""
import importlib
import os
import sqlite3

import pytest
from sqlalchemy import create_engine, inspect, text

PG_URL = os.getenv('UCM_TEST_PG_URL')
INSERT = "INSERT INTO websocket_relay (created_at, room, payload) VALUES ('2026-01-01', 'scope:cas', '{}')"


def _migration():
    return importlib.import_module('migrations._from_2_254.149_websocket_relay')


def test_sqlite_creates_the_table_and_is_idempotent():
    conn = sqlite3.connect(':memory:')
    _migration().upgrade(conn)
    _migration().upgrade(conn)
    conn.execute(INSERT)
    conn.execute(INSERT)
    conn.execute("DELETE FROM websocket_relay")
    conn.execute(INSERT)
    # A reader's cursor stays valid after a purge empties the table
    assert conn.execute("SELECT id FROM websocket_relay").fetchall() == [(3,)]
    indexes = {r[1] for r in conn.execute("PRAGMA index_list(websocket_relay)")}
    assert 'ix_websocket_relay_created_at' in indexes


@pytest.mark.postgres
@pytest.mark.skipif(not PG_URL, reason='UCM_TEST_PG_URL not set')
def test_postgres_creates_the_table_and_is_idempotent():
    from tests.conftest import pg_bench_exclusive
    with pg_bench_exclusive():
        _postgres_round()


def _postgres_round():
    schema = f"migtest_149_{os.getenv('PYTEST_XDIST_WORKER', 'main')}"
    engine = create_engine(PG_URL)
    conn = engine.connect()
    try:
        conn.execute(text(f"DROP SCHEMA IF EXISTS {schema} CASCADE"))
        conn.execute(text(f"CREATE SCHEMA {schema}"))
        conn.execute(text(f"SET search_path TO {schema}"))
        _migration().upgrade(conn)
        _migration().upgrade(conn)
        conn.execute(text(INSERT))
        conn.execute(text("DELETE FROM websocket_relay"))
        assert conn.execute(text(INSERT + " RETURNING id")).scalar() == 2
        cols = {c['name']: c for c in inspect(conn).get_columns('websocket_relay', schema=schema)}
        assert cols['room']['nullable'] is False and cols['payload']['nullable'] is False
        assert str(cols['id']['type']) == 'BIGINT'
        indexes = {i['name'] for i in inspect(conn).get_indexes('websocket_relay', schema=schema)}
        assert 'ix_websocket_relay_created_at' in indexes
    finally:
        conn.rollback()
        conn.execute(text(f"DROP SCHEMA IF EXISTS {schema} CASCADE"))
        conn.commit()
        conn.close()
        engine.dispose()


def test_the_app_schema_matches_the_migration(app):
    from models import WebsocketRelayEvent, db
    table = WebsocketRelayEvent.__tablename__
    with app.app_context():
        assert {'id', 'created_at', 'room', 'payload'} <= {
            c['name'] for c in inspect(db.engine).get_columns(table)}
        with db.engine.begin() as conn:
            first = conn.execute(text(INSERT + " RETURNING id")).scalar()
            conn.execute(text(f"DELETE FROM {table} WHERE id >= :i"), {'i': first})
            second = conn.execute(text(INSERT + " RETURNING id")).scalar()
            conn.execute(text(f"DELETE FROM {table} WHERE id = :i"), {'i': second})
        # The highest id deleted is not handed out again (SQLite AUTOINCREMENT, PostgreSQL sequence)
        assert second > first
