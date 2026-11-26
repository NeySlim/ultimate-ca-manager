"""Migration 176: whether a revocation record was published (issue #450), a nullable BOOLEAN added
on both backends, NULL (unknown) for the records already there; a second run keeps the values."""
import importlib
import os
import sqlite3

import pytest
from sqlalchemy import create_engine, text

from models import RevokedSerial

PG_URL = os.getenv('UCM_TEST_PG_URL')
RECORDS = RevokedSerial.__tablename__


def _migration():
    return importlib.import_module('migrations._from_2_254.176_revoked_serial_publication')


def test_the_step_follows_175_in_the_upgrade():
    from migrations._from_2_254 import STEPS
    assert STEPS.index('176_revoked_serial_publication') > STEPS.index('175_certificate_comment')


def test_sqlite_adds_the_column_unknown_and_keeps_values_on_a_second_run():
    conn = sqlite3.connect(':memory:')
    conn.execute(f"CREATE TABLE {RECORDS} (id INTEGER PRIMARY KEY, serial_number VARCHAR(100) NOT NULL)")
    conn.execute(f"INSERT INTO {RECORDS} VALUES (1, '42')")
    conn.commit()
    _migration().upgrade(conn)
    assert conn.execute(f"SELECT serial_number, published FROM {RECORDS}").fetchone() == ('42', None)
    conn.execute(f"UPDATE {RECORDS} SET published = 0")
    conn.commit()
    _migration().upgrade(conn)
    assert conn.execute(f"SELECT published FROM {RECORDS}").fetchone() == (0,)


def test_sqlite_without_the_table_changes_nothing():
    conn = sqlite3.connect(':memory:')
    _migration().upgrade(conn)
    assert conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'").fetchall() == []


def test_the_sqlalchemy_path_is_idempotent():
    engine = create_engine('sqlite://')
    with engine.begin() as conn:
        conn.execute(text(f"CREATE TABLE {RECORDS} (id INTEGER PRIMARY KEY)"))
        conn.execute(text(f"INSERT INTO {RECORDS} VALUES (1)"))
        _migration().upgrade(conn)
        conn.execute(text(f"UPDATE {RECORDS} SET published = 1"))
        _migration().upgrade(conn)
        assert conn.execute(text(f"SELECT published FROM {RECORDS}")).scalar() == 1
    engine.dispose()


@pytest.mark.postgres
@pytest.mark.skipif(not PG_URL, reason='UCM_TEST_PG_URL not set')
def test_postgres_adds_the_column_unknown_and_keeps_values_on_a_second_run():
    schema = f"migtest_176_{os.getenv('PYTEST_XDIST_WORKER', 'main')}"
    engine = create_engine(PG_URL)
    conn = engine.connect()
    try:
        conn.execute(text(f"DROP SCHEMA IF EXISTS {schema} CASCADE"))
        conn.execute(text(f"CREATE SCHEMA {schema}"))
        conn.execute(text(f"SET search_path TO {schema}"))
        conn.execute(text(f"CREATE TABLE {RECORDS} (id INTEGER PRIMARY KEY, serial_number VARCHAR(100) NOT NULL)"))
        conn.execute(text(f"INSERT INTO {RECORDS} VALUES (1, '42'), (2, '43')"))
        _migration().upgrade(conn)
        assert conn.execute(text(f"SELECT count(*) FROM {RECORDS} WHERE published IS NULL")).scalar() == 2
        conn.execute(text(f"UPDATE {RECORDS} SET published = false WHERE id = 1"))
        _migration().upgrade(conn)
        assert conn.execute(text(f"SELECT published FROM {RECORDS} ORDER BY id")).fetchall() == [(False,), (None,)]
        assert conn.execute(text(
            "SELECT data_type, is_nullable FROM information_schema.columns "
            "WHERE table_schema = :s AND table_name = :t AND column_name = 'published'"),
            {'s': schema, 't': RECORDS}).fetchone() == ('boolean', 'YES')
    finally:
        conn.rollback()
        conn.execute(text(f"DROP SCHEMA IF EXISTS {schema} CASCADE"))
        conn.commit()
        conn.close()
        engine.dispose()


def test_the_model_column_matches_the_step():
    column = RevokedSerial.__table__.c.published
    assert column.nullable and str(column.type) == 'BOOLEAN'
