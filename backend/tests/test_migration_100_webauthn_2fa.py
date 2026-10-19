"""Migration 100 on both backends: existing accounts get the switch off."""
import importlib
import os
import sqlite3

import pytest
from sqlalchemy import create_engine, text

PG_URL = os.getenv('UCM_TEST_PG_URL')


def _migration():
    return importlib.import_module('migrations.100_user_webauthn_second_factor')


def test_sqlite_adds_the_switch_off_and_runs_twice():
    connection = sqlite3.connect(':memory:')
    connection.execute("CREATE TABLE users (id INTEGER PRIMARY KEY, username TEXT)")
    connection.execute("INSERT INTO users (username) VALUES ('existing')")
    _migration().upgrade(connection)
    _migration().upgrade(connection)
    assert connection.execute("SELECT webauthn_2fa FROM users").fetchone() == (0,)


@pytest.mark.postgres
@pytest.mark.skipif(not PG_URL, reason='UCM_TEST_PG_URL not set')
def test_postgresql_adds_the_switch_off_and_runs_twice():
    from tests.test_restore_reference_resolution_pg import _a_schema_of_our_own
    with _a_schema_of_our_own('migration_100') as url:
        engine = create_engine(url)
        try:
            with engine.begin() as connection:
                connection.execute(text("CREATE TABLE users (id SERIAL PRIMARY KEY, username VARCHAR(80))"))
                connection.execute(text("INSERT INTO users (username) VALUES ('existing')"))
                _migration().upgrade(connection)
                _migration().upgrade(connection)
                assert connection.execute(text("SELECT webauthn_2fa FROM users")).scalar() is False
        finally:
            engine.dispose()
