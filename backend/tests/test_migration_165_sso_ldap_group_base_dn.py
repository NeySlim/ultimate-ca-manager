"""Migration 165: LDAP providers get an optional group search base, both backends."""
import importlib
import os
import sqlite3

import pytest
from sqlalchemy import create_engine, text

from models.sso import SSOProvider

PG_URL = os.getenv('UCM_TEST_PG_URL')
TABLE = SSOProvider.__tablename__
CREATE = f"CREATE TABLE {TABLE} (id {{pk}}, name VARCHAR(100) NOT NULL, ldap_base_dn VARCHAR(500))"
ROW = f"INSERT INTO {TABLE} (name, ldap_base_dn) VALUES ('corp', 'dc=example,dc=com')"


def _migration():
    return importlib.import_module('migrations._from_2_254.165_sso_ldap_group_base_dn')


def test_the_step_follows_164_in_the_upgrade():
    from migrations._from_2_254 import STEPS
    assert STEPS.index('165_sso_ldap_group_base_dn') == STEPS.index('164_file_removals') + 1


def test_sqlite_adds_the_column_once_and_keeps_the_rows():
    conn = sqlite3.connect(':memory:')
    conn.execute(CREATE.format(pk='INTEGER PRIMARY KEY'))
    conn.execute(ROW)
    conn.commit()
    for _ in range(2):
        _migration().upgrade(conn)
        assert conn.execute(f"SELECT name, ldap_base_dn, ldap_group_base_dn FROM {TABLE}").fetchall() \
            == [('corp', 'dc=example,dc=com', None)]


def test_sqlite_without_the_table_is_a_no_op():
    conn = sqlite3.connect(':memory:')
    _migration().upgrade(conn)
    assert conn.execute("SELECT count(*) FROM sqlite_master").fetchone()[0] == 0


@pytest.mark.postgres
@pytest.mark.skipif(not PG_URL, reason='UCM_TEST_PG_URL not set')
@pytest.mark.parametrize('with_table', [True, False], ids=['table', 'no_table'])
def test_postgres(with_table):
    schema = f"migtest_165_{os.getenv('PYTEST_XDIST_WORKER', 'main')}"
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
            assert conn.execute(text(f"SELECT name, ldap_base_dn, ldap_group_base_dn FROM {TABLE}")) \
                .fetchall() == [('corp', 'dc=example,dc=com', None)]
        else:
            assert conn.execute(text("SELECT count(*) FROM information_schema.tables "
                                     "WHERE table_schema = :s"), {'s': schema}).scalar() == 0
    finally:
        conn.rollback()
        conn.execute(text(f"DROP SCHEMA IF EXISTS {schema} CASCADE"))
        conn.commit()
        conn.close()
        engine.dispose()
