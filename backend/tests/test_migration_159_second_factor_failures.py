"""Migration 159: second_factor_failures on both backends, idempotent, matching the model."""
import importlib
import os
import sqlite3

import pytest
from sqlalchemy import create_engine, inspect, text

from models import SecondFactorFailure

PG_URL = os.getenv('UCM_TEST_PG_URL')
TABLE = SecondFactorFailure.__tablename__
COLUMNS = {'kind', 'target', 'failures', 'locked_until', 'updated_at'}
# Serves the purge run before each reservation: an expired lock, or an idle count
PURGE_INDEX = {'ix_second_factor_failures_purge': ['locked_until', 'updated_at']}


def _migration():
    return importlib.import_module('migrations._from_2_254.159_second_factor_failures')


def test_the_step_is_part_of_the_upgrade():
    from migrations._from_2_254 import STEPS
    assert STEPS[-1] == '159_second_factor_failures'


def test_sqlite_creates_the_table_and_is_idempotent():
    conn = sqlite3.connect(':memory:')
    _migration().upgrade(conn)
    _migration().upgrade(conn)
    insert = (f"INSERT INTO {TABLE} (kind, target, failures, updated_at) "
              "VALUES ('webauthn', 'alice', 1, '2026-01-01 00:00:00')")
    conn.execute(insert)
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(insert)
    conn.execute(f"INSERT INTO {TABLE} (kind, target, failures, updated_at) "
                 "VALUES ('2fa', 'alice', 1, '2026-01-01 00:00:00')")
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(f"INSERT INTO {TABLE} (kind, target, failures) VALUES ('2fa', 'bob', 1)")
    indexes = {row[1]: [c[2] for c in conn.execute(f"PRAGMA index_info({row[1]})")]
               for row in conn.execute(f"PRAGMA index_list({TABLE})") if row[3] == 'c'}
    assert indexes == PURGE_INDEX
    plan = ' '.join(str(r) for r in conn.execute(
        f"EXPLAIN QUERY PLAN DELETE FROM {TABLE} WHERE locked_until <= '2026-01-01' OR "
        "(locked_until IS NULL AND updated_at < '2026-01-01')"))
    assert 'ix_second_factor_failures_purge' in plan and 'SCAN' not in plan, plan


@pytest.mark.postgres
@pytest.mark.skipif(not PG_URL, reason='UCM_TEST_PG_URL not set')
def test_postgres_creates_the_table_and_is_idempotent():
    schema = f"migtest_159_{os.getenv('PYTEST_XDIST_WORKER', 'main')}"
    engine = create_engine(PG_URL)
    conn = engine.connect()
    try:
        conn.execute(text(f"DROP SCHEMA IF EXISTS {schema} CASCADE"))
        conn.execute(text(f"CREATE SCHEMA {schema}"))
        conn.execute(text(f"SET search_path TO {schema}"))
        _migration().upgrade(conn)
        _migration().upgrade(conn)
        conn.execute(text(f"INSERT INTO {TABLE} (kind, target, failures, updated_at) "
                          "VALUES ('webauthn', 'alice', 1, now())"))
        insp = inspect(conn)
        cols = {c['name']: c for c in insp.get_columns(TABLE, schema=schema)}
        assert set(cols) == COLUMNS
        assert cols['locked_until']['nullable'] is True and cols['failures']['nullable'] is False
        assert insp.get_pk_constraint(TABLE, schema=schema)['constrained_columns'] == ['kind', 'target']
        assert {i['name']: i['column_names'] for i in insp.get_indexes(TABLE, schema=schema)} \
            == PURGE_INDEX
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
        assert COLUMNS == {c['name'] for c in insp.get_columns(TABLE)}
        assert {i['name']: i['column_names'] for i in insp.get_indexes(TABLE)} == PURGE_INDEX
