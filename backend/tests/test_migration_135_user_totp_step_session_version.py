"""Migration 135 on both backends: existing accounts keep their sessions and codes."""
import importlib
import os
import sqlite3

import pytest
from sqlalchemy import create_engine, text

from models import User

PG_URL = os.getenv('UCM_TEST_PG_URL')
TABLE = User.__tablename__


def _migration():
    return importlib.import_module('migrations.135_user_totp_step_session_version')


def test_sqlite_adds_both_columns_and_runs_twice():
    connection = sqlite3.connect(':memory:')
    connection.execute(f"CREATE TABLE {TABLE} (id INTEGER PRIMARY KEY, username TEXT)")
    connection.execute(f"INSERT INTO {TABLE} (username) VALUES ('existing')")
    _migration().upgrade(connection)
    _migration().upgrade(connection)
    assert connection.execute(
        f"SELECT totp_last_step, session_version FROM {TABLE}").fetchone() == (None, 0)


@pytest.mark.postgres
@pytest.mark.skipif(not PG_URL, reason='UCM_TEST_PG_URL not set')
def test_postgresql_adds_both_columns_and_runs_twice():
    from tests.test_restore_reference_resolution_pg import _a_schema_of_our_own
    with _a_schema_of_our_own('migration_135') as url:
        engine = create_engine(url)
        try:
            with engine.begin() as connection:
                connection.execute(text(f"CREATE TABLE {TABLE} (id SERIAL PRIMARY KEY, username VARCHAR(80))"))
                connection.execute(text(f"INSERT INTO {TABLE} (username) VALUES ('existing')"))
                _migration().upgrade(connection)
                _migration().upgrade(connection)
                row = connection.execute(text(f"SELECT totp_last_step, session_version FROM {TABLE}")).one()
                assert tuple(row) == (None, 0)
        finally:
            engine.dispose()
