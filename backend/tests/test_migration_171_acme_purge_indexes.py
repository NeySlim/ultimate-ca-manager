"""Migration 171: the ACME purge finds an order's authorizations and an authorization's
challenges by index, on both backends, idempotent, matching the model."""
import importlib
import os
import sqlite3

import pytest
from sqlalchemy import create_engine, inspect, text

PG_URL = os.getenv('UCM_TEST_PG_URL')
INDEXES = {('acme_authorizations', 'ix_acme_authorizations_order_id', 'order_id'),
           ('acme_challenges', 'ix_acme_challenges_authorization_id', 'authorization_id')}
# The 2.254 tables, reduced to the columns the step reads
TABLES = ("CREATE TABLE acme_authorizations (id INTEGER PRIMARY KEY, "
          "authorization_id VARCHAR(64), order_id VARCHAR(64))",
          "CREATE TABLE acme_challenges (id INTEGER PRIMARY KEY, authorization_id VARCHAR(64))")


def _migration():
    return importlib.import_module('migrations._from_2_254.171_acme_purge_indexes')


def test_the_step_is_part_of_the_upgrade_after_170():
    from migrations._from_2_254 import STEPS
    assert STEPS.index('171_acme_purge_indexes') == STEPS.index('170_sso_sign_in_tests') + 1


def _sqlite_indexes(conn):
    return {(table, name, conn.execute(f"PRAGMA index_info({name})").fetchone()[2])
            for name, table in conn.execute(
                "SELECT name, tbl_name FROM sqlite_master WHERE type = 'index' "
                "AND tbl_name LIKE 'acme_%' AND name LIKE 'ix_%'")}


def test_sqlite_creates_both_indexes_and_is_idempotent():
    conn = sqlite3.connect(':memory:')
    for ddl in TABLES:
        conn.execute(ddl)
    _migration().upgrade(conn)
    _migration().upgrade(conn)
    assert _sqlite_indexes(conn) == INDEXES


def test_sqlite_without_the_tables_changes_nothing():
    conn = sqlite3.connect(':memory:')
    _migration().upgrade(conn)
    assert _sqlite_indexes(conn) == set()


@pytest.mark.postgres
@pytest.mark.skipif(not PG_URL, reason='UCM_TEST_PG_URL not set')
def test_postgres_creates_both_indexes_and_is_idempotent():
    schema = f"migtest_171_{os.getenv('PYTEST_XDIST_WORKER', 'main')}"
    engine = create_engine(PG_URL)
    conn = engine.connect()
    try:
        conn.execute(text(f"DROP SCHEMA IF EXISTS {schema} CASCADE"))
        conn.execute(text(f"CREATE SCHEMA {schema}"))
        conn.execute(text(f"SET search_path TO {schema}"))
        for ddl in TABLES:
            conn.execute(text(ddl))
        _migration().upgrade(conn)
        _migration().upgrade(conn)
        found = {(table, i['name'], i['column_names'][0])
                 for table in ('acme_authorizations', 'acme_challenges')
                 for i in inspect(conn).get_indexes(table, schema=schema)}
        assert found == INDEXES
    finally:
        conn.rollback()
        conn.execute(text(f"DROP SCHEMA IF EXISTS {schema} CASCADE"))
        conn.commit()
        conn.close()
        engine.dispose()


def test_the_purge_lookups_search_the_app_schema_by_index(app):
    """On the model's schema, the purge's lookups are index searches, not table scans:
    a scan per row held the SQLite write lock for 19 s at 66 000 orders."""
    from models import db
    with app.app_context():
        with db.engine.connect() as conn:
            found = {(t, i['name'], i['column_names'][0])
                     for t in ('acme_authorizations', 'acme_challenges')
                     for i in inspect(conn).get_indexes(t)}
            assert INDEXES <= found
            if conn.dialect.name == 'sqlite':
                for table, _name, column in INDEXES:
                    plan = conn.execute(text(
                        f"EXPLAIN QUERY PLAN SELECT * FROM {table} WHERE {column} = 'x'")).all()
                    assert any('USING INDEX' in row[-1] for row in plan), plan
