"""Migration 163: ssh_cas gains key_source ('software' on every row) and hsm_key_id, one SSH CA per key."""
import importlib
import os
import sqlite3

import pytest
from sqlalchemy import create_engine, inspect, text

from models import HsmKey
from models.ssh import SSHCertificateAuthority

PG_URL = os.getenv('UCM_TEST_PG_URL')
TABLE = SSHCertificateAuthority.__tablename__
KEYS = HsmKey.__tablename__
INDEX = 'uq_ssh_cas_hsm_key_id'


def _migration():
    return importlib.import_module('migrations._from_2_254.163_ssh_ca_hsm_key')


def test_the_step_is_the_last_of_the_upgrade():
    from migrations._from_2_254 import STEPS
    assert STEPS[-1] == '163_ssh_ca_hsm_key'


def test_the_model_declares_what_the_step_writes():
    columns = SSHCertificateAuthority.__table__.columns
    assert {'key_source', 'hsm_key_id'} <= set(columns.keys())
    assert [fk.target_fullname for fk in columns['hsm_key_id'].foreign_keys] == [f'{KEYS}.id']
    assert {i.name: i.unique for i in SSHCertificateAuthority.__table__.indexes}[INDEX] is True


def _sqlite():
    conn = sqlite3.connect(':memory:')
    conn.execute(f"CREATE TABLE {KEYS} (id INTEGER PRIMARY KEY)")
    conn.execute(f"CREATE TABLE {TABLE} (id INTEGER PRIMARY KEY, descr VARCHAR(255))")
    conn.execute(f"INSERT INTO {KEYS} (id) VALUES (1)")
    conn.execute(f"INSERT INTO {TABLE} (descr) VALUES ('kept'), ('kept too')")
    conn.commit()
    return conn


def test_sqlite_adds_the_columns_and_is_idempotent():
    conn = _sqlite()
    for _ in range(2):
        _migration().upgrade(conn)
    cols = {r[1]: r for r in conn.execute(f"PRAGMA table_info({TABLE})")}
    assert cols['key_source'][3] == 1 and cols['key_source'][4] == "'software'"
    assert [(r[2], r[3], r[4]) for r in conn.execute(f"PRAGMA foreign_key_list({TABLE})")] \
        == [(KEYS, 'hsm_key_id', 'id')]
    assert conn.execute(f"SELECT descr, key_source, hsm_key_id FROM {TABLE} ORDER BY id").fetchall() \
        == [('kept', 'software', None), ('kept too', 'software', None)]


def test_sqlite_one_ssh_ca_per_key():
    conn = _sqlite()
    _migration().upgrade(conn)
    conn.execute(f"UPDATE {TABLE} SET key_source = 'hsm', hsm_key_id = 1 WHERE descr = 'kept'")
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(f"UPDATE {TABLE} SET key_source = 'hsm', hsm_key_id = 1 WHERE descr = 'kept too'")


def test_sqlite_without_the_table_is_a_no_op():
    conn = sqlite3.connect(':memory:')
    _migration().upgrade(conn)
    assert conn.execute("SELECT count(*) FROM sqlite_master").fetchone()[0] == 0


@pytest.mark.postgres
@pytest.mark.skipif(not PG_URL, reason='UCM_TEST_PG_URL not set')
def test_postgres_adds_the_columns_one_ssh_ca_per_key():
    from sqlalchemy.exc import IntegrityError
    schema = f"migtest_163_{os.getenv('PYTEST_XDIST_WORKER', 'main')}"
    engine = create_engine(PG_URL)
    conn = engine.connect()
    try:
        conn.execute(text(f"DROP SCHEMA IF EXISTS {schema} CASCADE"))
        conn.execute(text(f"CREATE SCHEMA {schema}"))
        conn.execute(text(f"SET search_path TO {schema}"))
        conn.execute(text(f"CREATE TABLE {KEYS} (id SERIAL PRIMARY KEY)"))
        conn.execute(text(f"CREATE TABLE {TABLE} (id SERIAL PRIMARY KEY, descr VARCHAR(255))"))
        conn.execute(text(f"INSERT INTO {KEYS} (id) VALUES (1)"))
        conn.execute(text(f"INSERT INTO {TABLE} (descr) VALUES ('kept'), ('kept too')"))
        for _ in range(2):
            _migration().upgrade(conn)
        insp = inspect(conn)
        cols = {c['name']: c for c in insp.get_columns(TABLE, schema=schema)}
        assert cols['key_source']['nullable'] is False and 'software' in cols['key_source']['default']
        assert [(fk['constrained_columns'], fk['referred_table']) for fk in insp.get_foreign_keys(TABLE, schema=schema)] \
            == [(['hsm_key_id'], KEYS)]
        assert conn.execute(text(f"SELECT descr, key_source, hsm_key_id FROM {TABLE} ORDER BY id")).fetchall() \
            == [('kept', 'software', None), ('kept too', 'software', None)]
        conn.execute(text(f"UPDATE {TABLE} SET key_source = 'hsm', hsm_key_id = 1 WHERE descr = 'kept'"))
        with pytest.raises(IntegrityError):
            conn.execute(text(f"UPDATE {TABLE} SET hsm_key_id = 1 WHERE descr = 'kept too'"))
    finally:
        conn.rollback()
        conn.execute(text(f"DROP SCHEMA IF EXISTS {schema} CASCADE"))
        conn.commit()
        conn.close()
        engine.dispose()
