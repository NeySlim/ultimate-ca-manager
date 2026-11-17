"""Migration 170: pro_sso_sign_in_tests on both backends, idempotent, matching the model."""
import importlib
import os
import sqlite3

import pytest
from sqlalchemy import create_engine, inspect, text

from models.sso import SSOSignInTest

PG_URL = os.getenv('UCM_TEST_PG_URL')
TABLE = SSOSignInTest.__tablename__
COLUMNS = {
    'id', 'token', 'provider_id', 'user_id', 'protocol', 'transaction_hash', 'browser_hash',
    'secret', 'state', 'report', 'created_at', 'expires_at', 'finished_at',
}
INSERT = (f"INSERT INTO {TABLE} (token, provider_id, user_id, protocol, transaction_hash, "
          "browser_hash, state, created_at, expires_at) VALUES ('{token}', 1, 1, 'oauth2', "
          "'{tx}', 'b', 'pending', '2026-11-17 00:00:00', '2026-11-17 00:10:00')")


def _migration():
    return importlib.import_module('migrations._from_2_254.170_sso_sign_in_tests')


def test_the_step_is_part_of_the_upgrade_after_169():
    from migrations._from_2_254 import STEPS
    assert STEPS.index('170_sso_sign_in_tests') == STEPS.index('169_background_jobs') + 1


def _token_and_transaction_are_unique(execute, integrity_error):
    execute(INSERT.format(token='t1', tx='x1'))
    with pytest.raises(integrity_error):
        execute(INSERT.format(token='t1', tx='x2'))
    with pytest.raises(integrity_error):
        execute(INSERT.format(token='t2', tx='x1'))
    execute(INSERT.format(token='t2', tx='x2'))


def test_sqlite_creates_the_table_and_is_idempotent():
    conn = sqlite3.connect(':memory:')
    _migration().upgrade(conn)
    _migration().upgrade(conn)
    assert {row[1] for row in conn.execute(f"PRAGMA table_info({TABLE})")} == COLUMNS
    _token_and_transaction_are_unique(conn.execute, sqlite3.IntegrityError)


@pytest.mark.postgres
@pytest.mark.skipif(not PG_URL, reason='UCM_TEST_PG_URL not set')
def test_postgres_creates_the_table_and_is_idempotent():
    from sqlalchemy.exc import IntegrityError
    schema = f"migtest_170_{os.getenv('PYTEST_XDIST_WORKER', 'main')}"
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
            with conn.begin_nested():
                conn.execute(text(sql))
        _token_and_transaction_are_unique(execute, IntegrityError)
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
        assert 'ix_pro_sso_sign_in_tests_expires_at' in {
            i['name'] for i in inspect(db.engine).get_indexes(TABLE)}
