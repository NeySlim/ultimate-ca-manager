"""Migration 177: the source networks an API key is limited to (#403), a nullable TEXT added on
both backends, NULL (any address) for the keys already there; a second run keeps the values."""
import importlib
import os
import sqlite3

import pytest
from sqlalchemy import create_engine, text

from models.api_key import APIKey

PG_URL = os.getenv('UCM_TEST_PG_URL')
KEYS = APIKey.__tablename__


def _migration():
    return importlib.import_module('migrations._from_2_254.177_api_key_allowed_networks')


def test_the_step_is_the_last_of_the_upgrade():
    from migrations._from_2_254 import STEPS
    assert STEPS[-1] == '177_api_key_allowed_networks'
    assert STEPS.index('177_api_key_allowed_networks') > STEPS.index('176_revoked_serial_publication')


def test_sqlite_adds_the_column_open_and_keeps_values_on_a_second_run():
    conn = sqlite3.connect(':memory:')
    conn.execute(f"CREATE TABLE {KEYS} (id INTEGER PRIMARY KEY, name VARCHAR(100) NOT NULL)")
    conn.execute(f"INSERT INTO {KEYS} VALUES (1, 'ci')")
    conn.commit()
    _migration().upgrade(conn)
    assert conn.execute(f"SELECT name, allowed_networks FROM {KEYS}").fetchone() == ('ci', None)
    conn.execute(f"UPDATE {KEYS} SET allowed_networks = '[\"10.0.0.0/8\"]'")
    conn.commit()
    _migration().upgrade(conn)
    assert conn.execute(f"SELECT allowed_networks FROM {KEYS}").fetchone() == ('["10.0.0.0/8"]',)


def test_sqlite_without_the_table_changes_nothing():
    conn = sqlite3.connect(':memory:')
    _migration().upgrade(conn)
    assert conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'").fetchall() == []


def test_the_sqlalchemy_path_is_idempotent():
    engine = create_engine('sqlite://')
    with engine.begin() as conn:
        conn.execute(text(f"CREATE TABLE {KEYS} (id INTEGER PRIMARY KEY)"))
        conn.execute(text(f"INSERT INTO {KEYS} VALUES (1)"))
        _migration().upgrade(conn)
        conn.execute(text(f"UPDATE {KEYS} SET allowed_networks = '[]'"))
        _migration().upgrade(conn)
        assert conn.execute(text(f"SELECT allowed_networks FROM {KEYS}")).scalar() == '[]'
    engine.dispose()


@pytest.mark.postgres
@pytest.mark.skipif(not PG_URL, reason='UCM_TEST_PG_URL not set')
def test_postgres_adds_the_column_open_and_keeps_values_on_a_second_run():
    schema = f"migtest_177_{os.getenv('PYTEST_XDIST_WORKER', 'main')}"
    engine = create_engine(PG_URL)
    conn = engine.connect()
    try:
        conn.execute(text(f"DROP SCHEMA IF EXISTS {schema} CASCADE"))
        conn.execute(text(f"CREATE SCHEMA {schema}"))
        conn.execute(text(f"SET search_path TO {schema}"))
        conn.execute(text(f"CREATE TABLE {KEYS} (id INTEGER PRIMARY KEY, name VARCHAR(100) NOT NULL)"))
        conn.execute(text(f"INSERT INTO {KEYS} VALUES (1, 'ci'), (2, 'console')"))
        _migration().upgrade(conn)
        assert conn.execute(text(f"SELECT count(*) FROM {KEYS} WHERE allowed_networks IS NULL")).scalar() == 2
        conn.execute(text(f"UPDATE {KEYS} SET allowed_networks = '[\"192.0.2.0/24\"]' WHERE id = 2"))
        _migration().upgrade(conn)
        assert conn.execute(text(f"SELECT allowed_networks FROM {KEYS} ORDER BY id")).fetchall() == [
            (None,), ('["192.0.2.0/24"]',)]
        assert conn.execute(text(
            "SELECT data_type, is_nullable FROM information_schema.columns "
            "WHERE table_schema = :s AND table_name = :t AND column_name = 'allowed_networks'"),
            {'s': schema, 't': KEYS}).fetchone() == ('text', 'YES')
    finally:
        conn.rollback()
        conn.execute(text(f"DROP SCHEMA IF EXISTS {schema} CASCADE"))
        conn.commit()
        conn.close()
        engine.dispose()


def test_the_model_column_matches_the_step():
    column = APIKey.__table__.c.allowed_networks
    assert column.nullable and str(column.type) == 'TEXT'
