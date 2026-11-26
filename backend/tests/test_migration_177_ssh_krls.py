"""Migration 177: the published KRL of each SSH CA (issue #451), one table on both backends,
created once; a second run keeps its rows."""
import importlib
import os
import sqlite3

import pytest
from sqlalchemy import create_engine, inspect, text

from models import SSHKRL

PG_URL = os.getenv('UCM_TEST_PG_URL')
TABLE = SSHKRL.__tablename__


def _migration():
    return importlib.import_module('migrations._from_2_254.177_ssh_krls')


def test_the_step_follows_176_in_the_upgrade():
    from migrations._from_2_254 import STEPS
    assert STEPS.index('177_ssh_krls') > STEPS.index('176_revoked_serial_publication')


def test_sqlite_creates_the_table_and_keeps_rows_on_a_second_run():
    conn = sqlite3.connect(':memory:')
    conn.execute("CREATE TABLE ssh_cas (id INTEGER PRIMARY KEY)")
    conn.execute("INSERT INTO ssh_cas VALUES (1)")
    _migration().upgrade(conn)
    conn.execute(f"INSERT INTO {TABLE} VALUES (1, 1764000000000, 'ab', x'00', '2026-11-26 10:00:00')")
    conn.commit()
    _migration().upgrade(conn)
    assert conn.execute(f"SELECT ssh_ca_id, version, digest FROM {TABLE}").fetchall() == [(1, 1764000000000, 'ab')]


def test_the_sqlalchemy_path_is_idempotent():
    engine = create_engine('sqlite://')
    with engine.begin() as conn:
        conn.execute(text("CREATE TABLE ssh_cas (id INTEGER PRIMARY KEY)"))
        _migration().upgrade(conn)
        _migration().upgrade(conn)
        columns = {c['name'] for c in inspect(conn).get_columns(TABLE)}
    engine.dispose()
    assert columns == {c.name for c in SSHKRL.__table__.columns}


@pytest.mark.postgres
@pytest.mark.skipif(not PG_URL, reason='UCM_TEST_PG_URL not set')
def test_postgres_creates_the_table_once():
    schema = f"migtest_177_{os.getenv('PYTEST_XDIST_WORKER', 'main')}"
    engine = create_engine(PG_URL)
    conn = engine.connect()
    try:
        conn.execute(text(f"DROP SCHEMA IF EXISTS {schema} CASCADE"))
        conn.execute(text(f"CREATE SCHEMA {schema}"))
        conn.execute(text(f"SET search_path TO {schema}"))
        conn.execute(text("CREATE TABLE ssh_cas (id INTEGER PRIMARY KEY)"))
        conn.execute(text("INSERT INTO ssh_cas VALUES (1)"))
        _migration().upgrade(conn)
        conn.execute(text(f"INSERT INTO {TABLE} VALUES (1, 1764000000000, 'ab', '\\x00', now())"))
        _migration().upgrade(conn)
        assert conn.execute(text(f"SELECT version FROM {TABLE}")).scalar() == 1764000000000
        types = dict(conn.execute(text(
            "SELECT column_name, data_type FROM information_schema.columns "
            "WHERE table_schema = :s AND table_name = :t"), {'s': schema, 't': TABLE}).fetchall())
        assert types == {'ssh_ca_id': 'integer', 'version': 'bigint', 'digest': 'character varying',
                         'data': 'bytea', 'updated_at': 'timestamp without time zone'}
        # The CA deleted, its KRL goes with it
        conn.execute(text("DELETE FROM ssh_cas"))
        assert conn.execute(text(f"SELECT count(*) FROM {TABLE}")).scalar() == 0
    finally:
        conn.rollback()
        conn.execute(text(f"DROP SCHEMA IF EXISTS {schema} CASCADE"))
        conn.commit()
        conn.close()
        engine.dispose()
