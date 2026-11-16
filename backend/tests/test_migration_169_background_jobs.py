"""Migration 169: background_jobs on both backends, idempotent, one active job per slot."""
import importlib
import os
import sqlite3

import pytest
from sqlalchemy import create_engine, inspect, text

from models import BackgroundJob

PG_URL = os.getenv('UCM_TEST_PG_URL')
TABLE = BackgroundJob.__tablename__
COLUMNS = {
    'id', 'kind', 'slot', 'state', 'reason', 'node_id', 'executor', 'requested_by_id',
    'requested_by_name', 'requested_ip', 'params', 'secret', 'file_name', 'progress_done',
    'progress_total', 'phase', 'cancel_requested', 'result', 'steps', 'created_at',
    'started_at', 'finished_at', 'lease_expires_at',
}
INSERT = (f"INSERT INTO {TABLE} (id, kind, slot, state, cancel_requested, created_at) "
          "VALUES ('{id}', 'audit_verify', '{slot}', '{state}', {false}, '2026-11-16 00:00:00')")


def _migration():
    return importlib.import_module('migrations._from_2_254.169_background_jobs')


def test_the_step_is_part_of_the_upgrade_after_167():
    from migrations._from_2_254 import STEPS
    assert STEPS.index('169_background_jobs') == STEPS.index('167_user_sso_identities') + 1
    assert not any(name.startswith('168') for name in STEPS)


def _active_slot_is_unique(execute, integrity_error, false):
    execute(INSERT.format(id='a', slot='backup', state='running', false=false))
    with pytest.raises(integrity_error):
        execute(INSERT.format(id='b', slot='backup', state='pending', false=false))
    # Finished jobs of a slot are kept side by side; another slot is free
    execute(INSERT.format(id='c', slot='backup', state='failed', false=false))
    execute(INSERT.format(id='d', slot='backup', state='succeeded', false=false))
    execute(INSERT.format(id='e', slot='audit_verify', state='pending', false=false))


def test_sqlite_creates_the_table_and_is_idempotent():
    conn = sqlite3.connect(':memory:')
    _migration().upgrade(conn)
    _migration().upgrade(conn)
    assert {row[1] for row in conn.execute(f"PRAGMA table_info({TABLE})")} == COLUMNS
    _active_slot_is_unique(conn.execute, sqlite3.IntegrityError, 0)


@pytest.mark.postgres
@pytest.mark.skipif(not PG_URL, reason='UCM_TEST_PG_URL not set')
def test_postgres_creates_the_table_and_is_idempotent():
    from sqlalchemy.exc import IntegrityError
    schema = f"migtest_169_{os.getenv('PYTEST_XDIST_WORKER', 'main')}"
    engine = create_engine(PG_URL)
    conn = engine.connect()
    try:
        conn.execute(text(f"DROP SCHEMA IF EXISTS {schema} CASCADE"))
        conn.execute(text(f"CREATE SCHEMA {schema}"))
        conn.execute(text(f"SET search_path TO {schema}"))
        _migration().upgrade(conn)
        _migration().upgrade(conn)
        assert {c['name'] for c in inspect(conn).get_columns(TABLE, schema=schema)} == COLUMNS
        conn.commit()
        conn.execute(text(f"SET search_path TO {schema}"))

        def execute(sql):
            try:
                with conn.begin_nested():
                    conn.execute(text(sql))
            except IntegrityError:
                raise
        _active_slot_is_unique(execute, IntegrityError, 'false')
    finally:
        conn.rollback()
        conn.execute(text(f"DROP SCHEMA IF EXISTS {schema} CASCADE"))
        conn.commit()
        conn.close()
        engine.dispose()


def test_the_app_schema_matches_the_migration(app):
    from models import db
    with app.app_context():
        assert {c['name'] for c in inspect(db.engine).get_columns(TABLE)} == COLUMNS
        indexes = {i['name']: i for i in inspect(db.engine).get_indexes(TABLE)}
        assert indexes['uq_background_jobs_active_slot']['unique']
