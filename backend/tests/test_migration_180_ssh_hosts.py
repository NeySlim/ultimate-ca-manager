"""Migration 180: enrolled SSH hosts and their enrollment tokens (issue #451), two tables on both
backends, created once with the columns of the models; a second run keeps their rows."""
import importlib
import os
import sqlite3

import pytest
from sqlalchemy import create_engine, inspect, text

from models import SSHHost, SSHHostEnrollmentToken

PG_URL = os.getenv('UCM_TEST_PG_URL')
TABLES = (SSHHost.__table__, SSHHostEnrollmentToken.__table__)


def _migration():
    return importlib.import_module('migrations._from_2_254.180_ssh_hosts')


def _base(conn):
    conn.execute("CREATE TABLE ssh_cas (id INTEGER PRIMARY KEY)")
    conn.execute("CREATE TABLE ssh_certificates (id INTEGER PRIMARY KEY)")


def test_the_step_runs_in_number_order():
    from migrations._from_2_254 import STEPS
    own = STEPS.index('180_ssh_hosts')
    # Lower numbers run before it, higher ones after: no step is assumed to be the last
    assert all((int(s[:3]) < 180) == (i < own) for i, s in enumerate(STEPS) if i != own)


def test_sqlite_creates_both_tables_and_keeps_rows_on_a_second_run():
    conn = sqlite3.connect(':memory:')
    _base(conn)
    _migration().upgrade(conn)
    conn.execute("INSERT INTO ssh_hosts (refid, ssh_ca_id, name, principals, public_key, key_type, fingerprint, "
                 "enrolled_at) VALUES ('r', 1, 'web01', '[]', 'k', 'ed25519', 'f', '2026-11-26 10:00:00')")
    conn.commit()
    _migration().upgrade(conn)
    assert conn.execute("SELECT name, auto_renew, renew_percent FROM ssh_hosts").fetchall() == [('web01', 1, 30)]


def test_the_columns_are_those_of_the_models():
    engine = create_engine('sqlite://')
    with engine.begin() as conn:
        conn.execute(text("CREATE TABLE ssh_cas (id INTEGER PRIMARY KEY)"))
        conn.execute(text("CREATE TABLE ssh_certificates (id INTEGER PRIMARY KEY)"))
        _migration().upgrade(conn)
        _migration().upgrade(conn)
        for table in TABLES:
            assert {c['name'] for c in inspect(conn).get_columns(table.name)} == {c.name for c in table.columns}
            assert {i['name'] for i in inspect(conn).get_indexes(table.name)} >= {
                i.name for i in table.indexes}
    engine.dispose()


@pytest.mark.postgres
@pytest.mark.skipif(not PG_URL, reason='UCM_TEST_PG_URL not set')
def test_postgres_creates_both_tables_once():
    schema = f"migtest_180_{os.getenv('PYTEST_XDIST_WORKER', 'main')}"
    engine = create_engine(PG_URL)
    conn = engine.connect()
    try:
        conn.execute(text(f"DROP SCHEMA IF EXISTS {schema} CASCADE"))
        conn.execute(text(f"CREATE SCHEMA {schema}"))
        conn.execute(text(f"SET search_path TO {schema}"))
        conn.execute(text("CREATE TABLE ssh_cas (id INTEGER PRIMARY KEY)"))
        conn.execute(text("CREATE TABLE ssh_certificates (id INTEGER PRIMARY KEY)"))
        conn.execute(text("INSERT INTO ssh_cas VALUES (1)"))
        conn.execute(text("INSERT INTO ssh_certificates VALUES (7)"))
        _migration().upgrade(conn)
        conn.execute(text("INSERT INTO ssh_hosts (refid, ssh_ca_id, name, principals, public_key, key_type, "
                          "fingerprint, enrolled_at, certificate_id) VALUES ('r', 1, 'web01', '[]', 'k', 'ed25519', "
                          "'f', now(), 7)"))
        conn.execute(text("INSERT INTO ssh_host_enrollment_tokens (ssh_ca_id, token_hash, token_prefix, principals, "
                          "expires_at, created_at) VALUES (1, 'h', 'ucmh_x', '[]', now(), now())"))
        _migration().upgrade(conn)
        assert conn.execute(text("SELECT auto_renew, renew_percent FROM ssh_hosts")).fetchone() == (True, 30)
        for table in TABLES:
            columns = {r[0] for r in conn.execute(text(
                "SELECT column_name FROM information_schema.columns WHERE table_schema = :s AND table_name = :t"),
                {'s': schema, 't': table.name})}
            assert columns == {c.name for c in table.columns}
        # A deleted certificate leaves its host; a deleted CA takes its hosts and tokens
        conn.execute(text("DELETE FROM ssh_certificates"))
        assert conn.execute(text("SELECT certificate_id FROM ssh_hosts")).scalar() is None
        conn.execute(text("DELETE FROM ssh_cas"))
        assert conn.execute(text("SELECT count(*) FROM ssh_hosts")).scalar() == 0
        assert conn.execute(text("SELECT count(*) FROM ssh_host_enrollment_tokens")).scalar() == 0
    finally:
        conn.rollback()
        conn.execute(text(f"DROP SCHEMA IF EXISTS {schema} CASCADE"))
        conn.commit()
        conn.close()
        engine.dispose()
