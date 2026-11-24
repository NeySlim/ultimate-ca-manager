"""Migration 175: the optional comment of a certificate (issue #454), a nullable TEXT column added
on both backends; a second run keeps the comments written since."""
import importlib
import os
import sqlite3

import pytest
from sqlalchemy import create_engine, text

from models import Certificate

PG_URL = os.getenv('UCM_TEST_PG_URL')
CERTS = Certificate.__tablename__


def _migration():
    return importlib.import_module('migrations._from_2_254.175_certificate_comment')


def test_the_step_is_the_last_of_the_upgrade():
    from migrations._from_2_254 import STEPS
    assert STEPS[-1] == '175_certificate_comment'
    assert STEPS.index('175_certificate_comment') > STEPS.index('174_windows_profile_renewal_cas')


def test_sqlite_adds_the_column_and_keeps_comments_on_a_second_run():
    conn = sqlite3.connect(':memory:')
    conn.execute(f"CREATE TABLE {CERTS} (id INTEGER PRIMARY KEY, descr VARCHAR(255) NOT NULL)")
    conn.execute(f"INSERT INTO {CERTS} VALUES (1, 'Server')")
    conn.commit()
    _migration().upgrade(conn)
    assert conn.execute(f"SELECT descr, comment FROM {CERTS}").fetchone() == ('Server', None)
    conn.execute(f"UPDATE {CERTS} SET comment = 'Keep me'")
    conn.commit()
    _migration().upgrade(conn)
    assert conn.execute(f"SELECT comment FROM {CERTS}").fetchone() == ('Keep me',)


def test_sqlite_without_the_table_changes_nothing():
    conn = sqlite3.connect(':memory:')
    _migration().upgrade(conn)
    assert conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'").fetchall() == []


def test_the_sqlalchemy_path_is_idempotent():
    engine = create_engine('sqlite://')
    with engine.begin() as conn:
        conn.execute(text(f"CREATE TABLE {CERTS} (id INTEGER PRIMARY KEY)"))
        conn.execute(text(f"INSERT INTO {CERTS} VALUES (1)"))
        _migration().upgrade(conn)
        conn.execute(text(f"UPDATE {CERTS} SET comment = 'Keep me'"))
        _migration().upgrade(conn)
        assert conn.execute(text(f"SELECT comment FROM {CERTS}")).scalar() == 'Keep me'
    engine.dispose()


@pytest.mark.postgres
@pytest.mark.skipif(not PG_URL, reason='UCM_TEST_PG_URL not set')
def test_postgres_adds_the_column_and_keeps_comments_on_a_second_run():
    schema = f"migtest_175_{os.getenv('PYTEST_XDIST_WORKER', 'main')}"
    engine = create_engine(PG_URL)
    conn = engine.connect()
    try:
        conn.execute(text(f"DROP SCHEMA IF EXISTS {schema} CASCADE"))
        conn.execute(text(f"CREATE SCHEMA {schema}"))
        conn.execute(text(f"SET search_path TO {schema}"))
        conn.execute(text(f"CREATE TABLE {CERTS} (id INTEGER PRIMARY KEY, descr VARCHAR(255) NOT NULL)"))
        conn.execute(text(f"INSERT INTO {CERTS} VALUES (1, 'Server')"))
        _migration().upgrade(conn)
        conn.execute(text(f"UPDATE {CERTS} SET comment = 'Keep me'"))
        _migration().upgrade(conn)
        assert conn.execute(text(f"SELECT descr, comment FROM {CERTS}")).fetchone() == ('Server', 'Keep me')
        assert conn.execute(text(
            "SELECT data_type, is_nullable FROM information_schema.columns "
            "WHERE table_schema = :s AND table_name = :t AND column_name = 'comment'"),
            {'s': schema, 't': CERTS}).fetchone() == ('text', 'YES')
    finally:
        conn.rollback()
        conn.execute(text(f"DROP SCHEMA IF EXISTS {schema} CASCADE"))
        conn.commit()
        conn.close()
        engine.dispose()


def test_the_model_column_matches_the_step():
    column = Certificate.__table__.c.comment
    assert column.nullable and str(column.type) == 'TEXT'
