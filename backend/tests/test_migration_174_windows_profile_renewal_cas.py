"""Migration 174: each Windows enrollment profile lists the former CAs whose certificates renew,
initialized from the certificates it holds so that a profile whose CA changed keeps renewing them
(both backends, idempotent, a list already set is kept)."""
import importlib
import json
import os
import sqlite3

import pytest
from sqlalchemy import create_engine, text

from models import CA, Certificate, WindowsEnrollmentProfile

PG_URL = os.getenv('UCM_TEST_PG_URL')
PROFILES, CERTS, CAS = (WindowsEnrollmentProfile.__tablename__, Certificate.__tablename__,
                        CA.__tablename__)
TABLES = (
    f"CREATE TABLE {PROFILES} (id INTEGER PRIMARY KEY, name VARCHAR(100), is_default BOOLEAN, "
    "issuing_ca_refid VARCHAR(36))",
    f"CREATE TABLE {CAS} (id INTEGER PRIMARY KEY, refid VARCHAR(36))",
    f"CREATE TABLE {CERTS} (id INTEGER PRIMARY KEY, caref VARCHAR(36), source VARCHAR(50), "
    "windows_profile_id INTEGER)",
)
ROWS = (
    f"INSERT INTO {CAS} (id, refid) VALUES (1, 'ca-now'), (2, 'ca-before'), (3, 'ca-older'), (4, 'ca-other')",
    # p1 (default) moved twice; p2 never moved; p3 holds a certificate of a CA deleted since
    f"INSERT INTO {PROFILES} (id, name, is_default, issuing_ca_refid) VALUES "
    "(1, 'p1', TRUE, 'ca-now'), (2, 'p2', FALSE, 'ca-other'), (3, 'p3', FALSE, 'ca-now')",
    f"INSERT INTO {CERTS} (id, caref, source, windows_profile_id) VALUES "
    "(1, 'ca-now', 'wstep', 1), (2, 'ca-before', 'wstep', 1), (3, 'ca-older', 'wstep', NULL), "
    "(4, 'ca-other', 'wstep', 2), (5, 'ca-other', 'manual', NULL), (6, 'ca-gone', 'wstep', 3), "
    "(7, 'ca-older', 'wstep', 2), (8, NULL, 'wstep', 1)",
)
EXPECTED = {'p1': ['ca-before', 'ca-older'], 'p2': ['ca-older'], 'p3': []}


def _migration():
    return importlib.import_module('migrations._from_2_254.174_windows_profile_renewal_cas')


def test_the_step_is_part_of_the_upgrade_after_171():
    from migrations._from_2_254 import STEPS
    assert STEPS.index('174_windows_profile_renewal_cas') > STEPS.index('171_acme_purge_indexes')
    assert STEPS[-1] == '174_windows_profile_renewal_cas'


def _lists(rows):
    return {name: json.loads(value) for name, value in rows}


def test_sqlite_lists_the_former_cas_of_each_profile_and_is_idempotent():
    conn = sqlite3.connect(':memory:')
    for ddl in (*TABLES, *ROWS):
        conn.execute(ddl)
    conn.commit()
    _migration().upgrade(conn)
    assert _lists(conn.execute(f"SELECT name, renewal_ca_refids FROM {PROFILES}")) == EXPECTED
    # An operator's list is never recomputed by a second run
    conn.execute(f"UPDATE {PROFILES} SET renewal_ca_refids = '[]' WHERE name = 'p1'")
    conn.commit()
    _migration().upgrade(conn)
    assert _lists(conn.execute(f"SELECT name, renewal_ca_refids FROM {PROFILES}")) == {**EXPECTED, 'p1': []}


def test_sqlite_without_the_profiles_table_changes_nothing():
    conn = sqlite3.connect(':memory:')
    _migration().upgrade(conn)
    assert conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'").fetchall() == []


@pytest.mark.postgres
@pytest.mark.skipif(not PG_URL, reason='UCM_TEST_PG_URL not set')
def test_postgres_lists_the_former_cas_of_each_profile_and_is_idempotent():
    schema = f"migtest_174_{os.getenv('PYTEST_XDIST_WORKER', 'main')}"
    engine = create_engine(PG_URL)
    conn = engine.connect()
    try:
        conn.execute(text(f"DROP SCHEMA IF EXISTS {schema} CASCADE"))
        conn.execute(text(f"CREATE SCHEMA {schema}"))
        conn.execute(text(f"SET search_path TO {schema}"))
        for ddl in (*TABLES, *ROWS):
            conn.execute(text(ddl))
        _migration().upgrade(conn)
        _migration().upgrade(conn)
        assert _lists(conn.execute(text(f"SELECT name, renewal_ca_refids FROM {PROFILES}"))) == EXPECTED
    finally:
        conn.rollback()
        conn.execute(text(f"DROP SCHEMA IF EXISTS {schema} CASCADE"))
        conn.commit()
        conn.close()
        engine.dispose()


def test_the_model_column_matches_the_step():
    column = WindowsEnrollmentProfile.__table__.c.renewal_ca_refids
    assert column.nullable and str(column.type) == 'TEXT'
