"""Migration 125 adds the key digest of revocation records and the revocations an ACME order is
owed, idempotently."""
import importlib
import os
import sqlite3

import pytest
from sqlalchemy import create_engine, inspect, text

from models.acme_models import AcmeClientOrder
from models.revoked_serial import RevokedSerial

PG_URL = os.getenv('UCM_TEST_PG_URL')
SERIALS, ORDERS = RevokedSerial.__tablename__, AcmeClientOrder.__tablename__


def _migration():
    return importlib.import_module('migrations.125_revoked_key_digest_upstream_revocations')


def test_the_models_hold_the_columns_the_migration_adds():
    assert 'public_key_sha256' in {c.name for c in RevokedSerial.__table__.columns}
    assert 'upstream_revocations' in {c.name for c in AcmeClientOrder.__table__.columns}


def test_sqlite_adds_the_columns_and_keeps_rows():
    conn = sqlite3.connect(':memory:')
    conn.execute(f"CREATE TABLE {SERIALS} (id INTEGER PRIMARY KEY, serial_number TEXT)")
    conn.execute(f"CREATE TABLE {ORDERS} (id INTEGER PRIMARY KEY, domains TEXT)")
    conn.execute(f"INSERT INTO {SERIALS} (serial_number) VALUES ('42')")
    conn.execute(f"INSERT INTO {ORDERS} (domains) VALUES ('[]')")
    _migration().upgrade(conn)
    _migration().upgrade(conn)
    serials = {row[1]: row[2] for row in conn.execute(f"PRAGMA table_info({SERIALS})")}
    orders = {row[1]: row[2] for row in conn.execute(f"PRAGMA table_info({ORDERS})")}
    assert serials['public_key_sha256'] == 'VARCHAR(64)' and orders['upstream_revocations'] == 'TEXT'
    assert conn.execute(f"SELECT serial_number, public_key_sha256 FROM {SERIALS}").fetchall() == [('42', None)]
    assert conn.execute(f"SELECT domains, upstream_revocations FROM {ORDERS}").fetchall() == [('[]', None)]
    assert any(row[2] == 'public_key_sha256' for idx in conn.execute(f"PRAGMA index_list({SERIALS})")
               for row in conn.execute(f"PRAGMA index_info({idx[1]})"))


def test_sqlite_without_the_tables_is_a_no_op():
    conn = sqlite3.connect(':memory:')
    _migration().upgrade(conn)
    assert conn.execute("SELECT name FROM sqlite_master").fetchall() == []


@pytest.mark.postgres
@pytest.mark.skipif(not PG_URL, reason='UCM_TEST_PG_URL not set')
@pytest.mark.parametrize('with_tables', [True, False])
def test_postgres_adds_the_columns_and_keeps_rows(with_tables):
    schema = f"migtest_125{'' if with_tables else 'e'}_{os.getenv('PYTEST_XDIST_WORKER', 'main')}"
    engine = create_engine(PG_URL)
    conn = engine.connect()
    try:
        conn.execute(text(f"DROP SCHEMA IF EXISTS {schema} CASCADE"))
        conn.execute(text(f"CREATE SCHEMA {schema}"))
        conn.execute(text(f"SET search_path TO {schema}"))
        if not with_tables:
            _migration().upgrade(conn)
            assert inspect(conn).get_table_names(schema=schema) == []
            return
        conn.execute(text(f"CREATE TABLE {SERIALS} (id SERIAL PRIMARY KEY, serial_number TEXT)"))
        conn.execute(text(f"CREATE TABLE {ORDERS} (id SERIAL PRIMARY KEY, domains TEXT)"))
        conn.execute(text(f"INSERT INTO {SERIALS} (serial_number) VALUES ('42')"))
        conn.execute(text(f"INSERT INTO {ORDERS} (domains) VALUES ('[]')"))
        _migration().upgrade(conn)
        _migration().upgrade(conn)
        serials = {c['name']: str(c['type']) for c in inspect(conn).get_columns(SERIALS, schema=schema)}
        orders = {c['name']: str(c['type']) for c in inspect(conn).get_columns(ORDERS, schema=schema)}
        assert serials['public_key_sha256'] == 'VARCHAR(64)' and orders['upstream_revocations'] == 'TEXT'
        assert conn.execute(text(f"SELECT serial_number, public_key_sha256 FROM {SERIALS}")
                            ).fetchall() == [('42', None)]
        assert any(i['column_names'] == ['public_key_sha256']
                   for i in inspect(conn).get_indexes(SERIALS, schema=schema))
    finally:
        conn.rollback()
        conn.execute(text(f"DROP SCHEMA IF EXISTS {schema} CASCADE"))
        conn.commit()
        conn.close()
        engine.dispose()
