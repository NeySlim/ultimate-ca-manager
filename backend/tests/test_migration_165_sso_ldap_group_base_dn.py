"""Migration 165: LDAP providers get an optional group search base, both backends."""
import importlib
import os
import sqlite3

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.exc import IntegrityError

from models.sso import SSOProvider

PG_URL = os.getenv('UCM_TEST_PG_URL')
TABLE = SSOProvider.__tablename__
CREATE = (f"CREATE TABLE {TABLE} (id {{pk}}, name VARCHAR(100) NOT NULL, provider_type VARCHAR(50) NOT NULL, "
          "ldap_base_dn VARCHAR(500))")
ROW = f"INSERT INTO {TABLE} (name, provider_type, ldap_base_dn) VALUES ('corp', 'ldap', 'dc=example,dc=com')"


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


def test_sqlite_holds_one_provider_per_type_once_upgraded():
    conn = sqlite3.connect(':memory:')
    conn.execute(f"CREATE TABLE {TABLE} (id INTEGER PRIMARY KEY, name VARCHAR(100) NOT NULL, "
                 "provider_type VARCHAR(50) NOT NULL, ldap_base_dn VARCHAR(500))")
    conn.execute(f"INSERT INTO {TABLE} (name, provider_type) VALUES ('corp', 'oauth2')")
    conn.commit()
    _migration().upgrade(conn)
    _migration().upgrade(conn)
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(f"INSERT INTO {TABLE} (name, provider_type) VALUES ('okta', 'oauth2')")
    conn.execute(f"INSERT INTO {TABLE} (name, provider_type) VALUES ('dir', 'ldap')")


def test_the_refusal_names_each_provider_of_a_shared_type():
    conn = sqlite3.connect(':memory:')
    conn.execute(f"CREATE TABLE {TABLE} (id INTEGER PRIMARY KEY, name VARCHAR(100) NOT NULL, "
                 "provider_type VARCHAR(50) NOT NULL)")
    conn.executemany(f"INSERT INTO {TABLE} (id, name, provider_type) VALUES (?, ?, ?)",
                     [(2, 'a', 'saml'), (3, 'b', 'saml'), (4, 'c', 'ldap'), (5, 'd', 'saml')])
    message = _migration().refusal(conn)
    assert message.startswith("Upgrade refused: 3 SSO providers of type saml: 'a' (#2), 'b' (#3), 'd' (#5).")
    assert message.endswith("Nothing was changed: 2.254 still starts on this database.")
    with pytest.raises(RuntimeError, match='Upgrade refused'):
        _migration().upgrade(conn)
    assert conn.execute("SELECT count(*) FROM sqlite_master WHERE type = 'index'").fetchone()[0] == 0


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
            conn.commit()
            with pytest.raises(IntegrityError):
                conn.execute(text(f"INSERT INTO {TABLE} (name, provider_type) VALUES ('dir2', 'ldap')"))
            conn.rollback()
        else:
            assert conn.execute(text("SELECT count(*) FROM information_schema.tables "
                                     "WHERE table_schema = :s"), {'s': schema}).scalar() == 0
    finally:
        conn.rollback()
        conn.execute(text(f"DROP SCHEMA IF EXISTS {schema} CASCADE"))
        conn.commit()
        conn.close()
        engine.dispose()


# A blank name (2.254 let a provider be renamed so) becomes its type, or its type with a number
# when another provider holds that name already
BLANK_ROWS = [(2, '', 'ldap'), (3, '   ', 'saml'), (4, 'saml', 'oauth2')]
NAMED = [(2, 'ldap'), (3, 'saml (2)'), (4, 'saml')]


def test_sqlite_names_a_blank_provider_after_its_type_once():
    conn = sqlite3.connect(':memory:')
    conn.execute(CREATE.format(pk='INTEGER PRIMARY KEY'))
    conn.executemany(f"INSERT INTO {TABLE} (id, name, provider_type) VALUES (?, ?, ?)", BLANK_ROWS)
    conn.commit()
    for _ in range(2):
        _migration().upgrade(conn)
        assert conn.execute(f"SELECT id, name FROM {TABLE} ORDER BY id").fetchall() == NAMED


@pytest.mark.postgres
@pytest.mark.skipif(not PG_URL, reason='UCM_TEST_PG_URL not set')
def test_postgres_names_a_blank_provider_after_its_type_once():
    schema = f"migtest_165b_{os.getenv('PYTEST_XDIST_WORKER', 'main')}"
    engine = create_engine(PG_URL)
    conn = engine.connect()
    try:
        conn.execute(text(f"DROP SCHEMA IF EXISTS {schema} CASCADE"))
        conn.execute(text(f"CREATE SCHEMA {schema}"))
        conn.execute(text(f"SET search_path TO {schema}"))
        conn.execute(text(CREATE.format(pk='SERIAL PRIMARY KEY')))
        for row in BLANK_ROWS:
            conn.execute(text(f"INSERT INTO {TABLE} (id, name, provider_type) VALUES (:i, :n, :t)"),
                         {'i': row[0], 'n': row[1], 't': row[2]})
        for _ in range(2):
            _migration().upgrade(conn)
            assert [tuple(r) for r in conn.execute(
                text(f"SELECT id, name FROM {TABLE} ORDER BY id"))] == NAMED
    finally:
        conn.rollback()
        conn.execute(text(f"DROP SCHEMA IF EXISTS {schema} CASCADE"))
        conn.commit()
        conn.close()
        engine.dispose()
