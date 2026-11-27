"""Migration 181: key recovery requests carry requested_by_id and decided_by_id, nullable INTEGERs
added on both backends, NULL for the requests already there; a second run keeps the values."""
import importlib
import os
import sqlite3

import pytest
from sqlalchemy import create_engine, text

from models.key_recovery import KeyRecoveryRequest

PG_URL = os.getenv('UCM_TEST_PG_URL')
REQUESTS = KeyRecoveryRequest.__tablename__
TABLE = f"CREATE TABLE {REQUESTS} (id INTEGER PRIMARY KEY, requested_by VARCHAR(120) NOT NULL)"


def _migration():
    return importlib.import_module('migrations._from_2_254.181_key_recovery_user_ids')


def test_the_step_follows_every_lower_numbered_step():
    from migrations._from_2_254 import STEPS
    mine = STEPS.index('181_key_recovery_user_ids')
    assert all(int(s.split('_')[0]) < 181 for s in STEPS[:mine])
    assert all(int(s.split('_')[0]) > 181 for s in STEPS[mine + 1:])


def test_sqlite_adds_both_columns_empty_and_keeps_values_on_a_second_run():
    conn = sqlite3.connect(':memory:')
    conn.execute(TABLE)
    conn.execute(f"INSERT INTO {REQUESTS} VALUES (1, 'alice')")
    conn.commit()
    _migration().upgrade(conn)
    assert conn.execute(f"SELECT requested_by, requested_by_id, decided_by_id FROM {REQUESTS}").fetchone() \
        == ('alice', None, None)
    conn.execute(f"UPDATE {REQUESTS} SET requested_by_id = 7, decided_by_id = 3")
    conn.commit()
    _migration().upgrade(conn)
    assert conn.execute(f"SELECT requested_by_id, decided_by_id FROM {REQUESTS}").fetchone() == (7, 3)


def test_sqlite_without_the_table_changes_nothing():
    conn = sqlite3.connect(':memory:')
    _migration().upgrade(conn)
    assert conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'").fetchall() == []


def test_the_sqlalchemy_path_is_idempotent():
    engine = create_engine('sqlite://')
    with engine.begin() as conn:
        conn.execute(text(TABLE))
        conn.execute(text(f"INSERT INTO {REQUESTS} VALUES (1, 'alice')"))
        _migration().upgrade(conn)
        conn.execute(text(f"UPDATE {REQUESTS} SET requested_by_id = 7"))
        _migration().upgrade(conn)
        assert conn.execute(text(f"SELECT requested_by_id, decided_by_id FROM {REQUESTS}")).fetchone() == (7, None)
    engine.dispose()


@pytest.mark.postgres
@pytest.mark.skipif(not PG_URL, reason='UCM_TEST_PG_URL not set')
def test_postgres_adds_both_columns_empty_and_keeps_values_on_a_second_run():
    schema = f"migtest_181_{os.getenv('PYTEST_XDIST_WORKER', 'main')}"
    engine = create_engine(PG_URL)
    conn = engine.connect()
    try:
        conn.execute(text(f"DROP SCHEMA IF EXISTS {schema} CASCADE"))
        conn.execute(text(f"CREATE SCHEMA {schema}"))
        conn.execute(text(f"SET search_path TO {schema}"))
        conn.execute(text(TABLE))
        conn.execute(text(f"INSERT INTO {REQUESTS} VALUES (1, 'alice'), (2, 'bob')"))
        _migration().upgrade(conn)
        assert conn.execute(text(
            f"SELECT count(*) FROM {REQUESTS} WHERE requested_by_id IS NULL AND decided_by_id IS NULL")).scalar() == 2
        conn.execute(text(f"UPDATE {REQUESTS} SET requested_by_id = 9 WHERE id = 2"))
        _migration().upgrade(conn)
        assert conn.execute(text(f"SELECT requested_by_id FROM {REQUESTS} ORDER BY id")).fetchall() == [(None,), (9,)]
        assert conn.execute(text(
            "SELECT column_name, data_type, is_nullable FROM information_schema.columns "
            "WHERE table_schema = :s AND table_name = :t AND column_name LIKE '%%_by_id' ORDER BY column_name"),
            {'s': schema, 't': REQUESTS}).fetchall() == [
                ('decided_by_id', 'integer', 'YES'), ('requested_by_id', 'integer', 'YES')]
    finally:
        conn.rollback()
        conn.execute(text(f"DROP SCHEMA IF EXISTS {schema} CASCADE"))
        conn.commit()
        conn.close()
        engine.dispose()


def test_the_model_columns_match_the_step():
    for name in ('requested_by_id', 'decided_by_id'):
        column = KeyRecoveryRequest.__table__.c[name]
        assert column.nullable and str(column.type) == 'INTEGER'
