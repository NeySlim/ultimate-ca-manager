"""Migration 173: OIDC providers get optional lists of accepted Entra tenants and of tenants whose
roles are honoured, and identity rows an expected tenant, both backends."""
import importlib
import os
import sqlite3

import pytest
from sqlalchemy import create_engine, inspect, text

from models.sso import SSOProvider
from models.user import UserSSOIdentity

PG_URL = os.getenv('UCM_TEST_PG_URL')
TABLE = SSOProvider.__tablename__
CREATE = (f"CREATE TABLE {TABLE} (id {{pk}}, name VARCHAR(100) NOT NULL, "
          "provider_type VARCHAR(50) NOT NULL, oauth2_issuer VARCHAR(500))")
ROW = (f"INSERT INTO {TABLE} (name, provider_type, oauth2_issuer) "
       "VALUES ('entra', 'oauth2', 'https://idp.example/one')")
IDENTITIES = UserSSOIdentity.__tablename__
CREATE_IDENTITIES = f"CREATE TABLE {IDENTITIES} (id {{pk}}, user_id INTEGER NOT NULL, external_id VARCHAR(255))"
IDENTITY = f"INSERT INTO {IDENTITIES} (user_id, external_id) VALUES (7, 'sub-1')"
READ = f"SELECT name, oauth2_issuer, oauth2_tenants, oauth2_role_tenants FROM {TABLE}"
READ_IDENTITIES = f"SELECT user_id, external_id, expected_tenant FROM {IDENTITIES}"
KEPT = [('entra', 'https://idp.example/one', None, None)]
KEPT_IDENTITIES = [(7, 'sub-1', None)]


def _migration():
    return importlib.import_module('migrations._from_2_254.173_sso_oauth2_tenants')


def test_the_step_comes_after_172_in_the_upgrade():
    from migrations._from_2_254 import STEPS
    assert STEPS.index('173_sso_oauth2_tenants') == STEPS.index('172_sso_ldap_nested_groups') + 1


def test_the_model_declares_the_columns_the_step_adds():
    models = {SSOProvider.__tablename__: SSOProvider, IDENTITIES: UserSSOIdentity}
    assert {(t, c) for t, c, _k in _migration().COLUMNS} == {
        (TABLE, 'oauth2_tenants'), (TABLE, 'oauth2_role_tenants'), (IDENTITIES, 'expected_tenant')}
    for table, column, _kind in _migration().COLUMNS:
        assert column in models[table].__table__.columns


def test_sqlite_adds_the_columns_once_and_keeps_the_rows():
    conn = sqlite3.connect(':memory:')
    conn.execute(CREATE.format(pk='INTEGER PRIMARY KEY'))
    conn.execute(ROW)
    conn.execute(CREATE_IDENTITIES.format(pk='INTEGER PRIMARY KEY'))
    conn.execute(IDENTITY)
    conn.commit()
    for _ in range(2):
        _migration().upgrade(conn)
        assert conn.execute(READ).fetchall() == KEPT
        assert conn.execute(READ_IDENTITIES).fetchall() == KEPT_IDENTITIES


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
            conn.execute(text(CREATE_IDENTITIES.format(pk='SERIAL PRIMARY KEY')))
            conn.execute(text(IDENTITY))
        for _ in range(2):
            _migration().upgrade(conn)
        if with_table:
            assert conn.execute(text(READ)).fetchall() == KEPT
            assert conn.execute(text(READ_IDENTITIES)).fetchall() == KEPT_IDENTITIES
            for table, name, _kind in _migration().COLUMNS:
                column = next(c for c in inspect(conn).get_columns(table, schema=schema)
                              if c['name'] == name)
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
