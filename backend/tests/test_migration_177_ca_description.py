"""Migration 177: the free-text description of a CA (issue #459), a nullable TEXT column added on
both backends beside the display name; a second run keeps the descriptions written since."""
import importlib
import os
import sqlite3

import pytest
from sqlalchemy import create_engine, text

from models import CA

PG_URL = os.getenv('UCM_TEST_PG_URL')
CAS = CA.__tablename__


def _migration():
    return importlib.import_module('migrations._from_2_254.177_ca_description')


def test_the_step_follows_176_in_the_upgrade():
    from migrations._from_2_254 import STEPS
    assert STEPS.index('177_ca_description') > STEPS.index('176_revoked_serial_publication')


def test_sqlite_adds_the_column_and_keeps_descriptions_on_a_second_run():
    conn = sqlite3.connect(':memory:')
    conn.execute(f"CREATE TABLE {CAS} (id INTEGER PRIMARY KEY, descr VARCHAR(255) NOT NULL)")
    conn.execute(f"INSERT INTO {CAS} VALUES (1, 'Root')")
    conn.commit()
    _migration().upgrade(conn)
    assert conn.execute(f"SELECT descr, description FROM {CAS}").fetchone() == ('Root', None)
    conn.execute(f"UPDATE {CAS} SET description = 'Keep me'")
    conn.commit()
    _migration().upgrade(conn)
    assert conn.execute(f"SELECT description FROM {CAS}").fetchone() == ('Keep me',)


def test_sqlite_without_the_table_changes_nothing():
    conn = sqlite3.connect(':memory:')
    _migration().upgrade(conn)
    assert conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'").fetchall() == []


def test_the_sqlalchemy_path_is_idempotent():
    engine = create_engine('sqlite://')
    with engine.begin() as conn:
        conn.execute(text(f"CREATE TABLE {CAS} (id INTEGER PRIMARY KEY)"))
        conn.execute(text(f"INSERT INTO {CAS} VALUES (1)"))
        _migration().upgrade(conn)
        conn.execute(text(f"UPDATE {CAS} SET description = 'Keep me'"))
        _migration().upgrade(conn)
        assert conn.execute(text(f"SELECT description FROM {CAS}")).scalar() == 'Keep me'
    engine.dispose()


@pytest.mark.postgres
@pytest.mark.skipif(not PG_URL, reason='UCM_TEST_PG_URL not set')
def test_postgres_adds_the_column_and_keeps_descriptions_on_a_second_run():
    schema = f"migtest_177_{os.getenv('PYTEST_XDIST_WORKER', 'main')}"
    engine = create_engine(PG_URL)
    conn = engine.connect()
    try:
        conn.execute(text(f"DROP SCHEMA IF EXISTS {schema} CASCADE"))
        conn.execute(text(f"CREATE SCHEMA {schema}"))
        conn.execute(text(f"SET search_path TO {schema}"))
        conn.execute(text(f"CREATE TABLE {CAS} (id INTEGER PRIMARY KEY, descr VARCHAR(255) NOT NULL)"))
        conn.execute(text(f"INSERT INTO {CAS} VALUES (1, 'Root')"))
        _migration().upgrade(conn)
        conn.execute(text(f"UPDATE {CAS} SET description = 'Keep me'"))
        _migration().upgrade(conn)
        assert conn.execute(text(f"SELECT descr, description FROM {CAS}")).fetchone() == ('Root', 'Keep me')
        assert conn.execute(text(
            "SELECT data_type, is_nullable FROM information_schema.columns "
            "WHERE table_schema = :s AND table_name = :t AND column_name = 'description'"),
            {'s': schema, 't': CAS}).fetchone() == ('text', 'YES')
    finally:
        conn.rollback()
        conn.execute(text(f"DROP SCHEMA IF EXISTS {schema} CASCADE"))
        conn.commit()
        conn.close()
        engine.dispose()


def test_the_model_column_matches_the_step():
    column = CA.__table__.c.description
    assert column.nullable and str(column.type) == 'TEXT'
