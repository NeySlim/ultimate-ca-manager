"""Migration 173: OIDC providers get an optional list of accepted Entra tenants, both backends."""
import importlib
import os
import sqlite3

import pytest
from sqlalchemy import create_engine, inspect, text

from models.sso import SSOProvider

PG_URL = os.getenv('UCM_TEST_PG_URL')
TABLE = SSOProvider.__tablename__
CREATE = (f"CREATE TABLE {TABLE} (id {{pk}}, name VARCHAR(100) NOT NULL, "
          "provider_type VARCHAR(50) NOT NULL, oauth2_issuer VARCHAR(500))")
ROW = (f"INSERT INTO {TABLE} (name, provider_type, oauth2_issuer) "
       "VALUES ('entra', 'oauth2', 'https://idp.example/one')")


def _migration():
    return importlib.import_module('migrations._from_2_254.173_sso_oauth2_tenants')


def test_the_step_comes_after_172_in_the_upgrade():
    from migrations._from_2_254 import STEPS
    assert STEPS.index('173_sso_oauth2_tenants') == STEPS.index('172_sso_ldap_nested_groups') + 1


def test_the_model_declares_the_column_the_step_adds():
    assert _migration().COLUMN in SSOProvider.__table__.columns


def test_sqlite_adds_the_column_once_and_keeps_the_rows():
    conn = sqlite3.connect(':memory:')
    conn.execute(CREATE.format(pk='INTEGER PRIMARY KEY'))
    conn.execute(ROW)
    conn.commit()
    for _ in range(2):
        _migration().upgrade(conn)
        assert conn.execute(f"SELECT name, oauth2_issuer, oauth2_tenants FROM {TABLE}").fetchall() \
            == [('entra', 'https://idp.example/one', None)]


def test_sqlite_without_the_table_is_a_no_op():
    conn = sqlite3.connect(':memory:')
    _migration().upgrade(conn)
    assert conn.execute("SELECT count(*) FROM sqlite_master").fetchone()[0] == 0


@pytest.mark.postgres
@pytest.mark.skipif(not PG_URL, reason='UCM_TEST_PG_URL not set')
@pytest.mark.parametrize('with_table', [True, False], ids=['table', 'no_table'])
def test_postgres(with_table):
    schema = f"migtest_173_{os.getenv('PYTEST_XDIST_WORKER', 'main')}"
    engine = create_engine(PG_URL)
    conn = engine.connect()
    try:
        conn.execute(text(f"DROP SCHEMA IF EXISTS {schema} CASCADE"))
        conn.execute(text(f"CREATE SCHEMA {schema}"))
        conn.execute(text(f"SET search_path TO {schema}"))
        if with_table:
            conn.execute(text(CREATE.format(pk='SERIAL PRIMARY KEY')))
            conn.execute(text(ROW))
        for _ in range(2):
            _migration().upgrade(conn)
        if with_table:
            assert conn.execute(text(f"SELECT name, oauth2_issuer, oauth2_tenants FROM {TABLE}")) \
                .fetchall() == [('entra', 'https://idp.example/one', None)]
            column = next(c for c in inspect(conn).get_columns(TABLE, schema=schema)
                          if c['name'] == 'oauth2_tenants')
            assert column['nullable'] is True
        else:
            assert conn.execute(text("SELECT count(*) FROM information_schema.tables "
                                     "WHERE table_schema = :s"), {'s': schema}).scalar() == 0
    finally:
        conn.rollback()
        conn.execute(text(f"DROP SCHEMA IF EXISTS {schema} CASCADE"))
        conn.commit()
        conn.close()
        engine.dispose()
