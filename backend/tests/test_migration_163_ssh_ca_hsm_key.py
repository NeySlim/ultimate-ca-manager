"""Migration 163: ssh_cas gains key_source ('software' on every row) and hsm_key_id, one SSH CA per key."""
import importlib
import os
import sqlite3

import pytest
from sqlalchemy import create_engine, inspect, text

from models import CA, HsmKey
from models.ssh import SSHCertificateAuthority

PG_URL = os.getenv('UCM_TEST_PG_URL')
TABLE = SSHCertificateAuthority.__tablename__
KEYS = HsmKey.__tablename__
INDEX = 'uq_ssh_cas_hsm_key_id'


def _migration():
    return importlib.import_module('migrations._from_2_254.163_ssh_ca_hsm_key')


def test_the_step_follows_the_tsa_step():
    from migrations._from_2_254 import STEPS
    assert STEPS.index('163_ssh_ca_hsm_key') == STEPS.index('162_tsa_ca_signer_kept') + 1


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


# --- X.509: one CA per HSM key ------------------------------------------------------------------

X509 = CA.__tablename__
X509_INDEX = 'uq_ca_hsm_key_id'


def test_the_model_declares_the_x509_index():
    assert {i.name: (i.unique, [c.name for c in i.columns]) for i in CA.__table__.indexes}[X509_INDEX] \
        == (True, ['hsm_key_id'])


def _sqlite_x509(index_of_2x=False):
    conn = _sqlite()
    conn.execute(f"CREATE TABLE {X509} (id INTEGER PRIMARY KEY, descr VARCHAR(255), "
                 f"hsm_key_id INTEGER REFERENCES {KEYS} (id))")
    conn.execute(f"ALTER TABLE {KEYS} ADD COLUMN label VARCHAR(255)")
    conn.execute(f"UPDATE {KEYS} SET label = 'token-key'")
    conn.execute(f"INSERT INTO {KEYS} (id, label) VALUES (2, 'other-key')")
    if index_of_2x:
        conn.execute(f"CREATE UNIQUE INDEX {X509_INDEX} ON {X509}(hsm_key_id) WHERE hsm_key_id IS NOT NULL")
    conn.execute(f"INSERT INTO {X509} (id, descr, hsm_key_id) VALUES (1, 'on key', 1), (2, 'local', NULL), "
                 f"(3, 'local too', NULL)")
    conn.commit()
    return conn


def _sqlite_indexes(conn, table):
    return conn.execute("SELECT name, sql FROM sqlite_master WHERE type = 'index' AND tbl_name = ?",
                        (table,)).fetchall()


@pytest.mark.parametrize('index_of_2x', [False, True])
def test_sqlite_one_x509_ca_per_key_under_one_name(index_of_2x):
    conn = _sqlite_x509(index_of_2x)
    for _ in range(2):
        _migration().upgrade(conn)
    assert _sqlite_indexes(conn, X509) == [
        (X509_INDEX, f'CREATE UNIQUE INDEX {X509_INDEX} ON {X509} (hsm_key_id)')]
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(f"UPDATE {X509} SET hsm_key_id = 1 WHERE id = 2")
    conn.execute(f"UPDATE {X509} SET hsm_key_id = 2 WHERE id = 2")


def test_sqlite_two_x509_cas_on_one_key_are_refused_unchanged():
    conn = _sqlite_x509()
    conn.execute(f"UPDATE {X509} SET hsm_key_id = 1 WHERE id = 3")
    conn.commit()
    message = _migration().refusal(conn)
    assert message.startswith("Upgrade refused: HSM key 'token-key' (#1) backs 2 X.509 CAs: "
                              "'on key' (#1), 'local too' (#3)."), message
    assert 'Nothing was changed: 2.254 still starts on this database.' in message
    before = conn.execute("SELECT sql FROM sqlite_master ORDER BY name").fetchall()
    with pytest.raises(RuntimeError) as refused:
        _migration().upgrade(conn)
    assert str(refused.value) == message
    assert conn.execute("SELECT sql FROM sqlite_master ORDER BY name").fetchall() == before


def test_sqlite_without_duplicates_nothing_is_refused():
    assert _migration().refusal(_sqlite_x509()) is None


@pytest.mark.postgres
@pytest.mark.skipif(not PG_URL, reason='UCM_TEST_PG_URL not set')
@pytest.mark.parametrize('index_of_2x', [False, True])
def test_postgres_one_x509_ca_per_key_and_duplicates_refused(index_of_2x):
    from sqlalchemy.exc import IntegrityError
    schema = f"migtest_163x_{os.getenv('PYTEST_XDIST_WORKER', 'main')}"
    engine = create_engine(PG_URL)
    conn = engine.connect()
    try:
        conn.execute(text(f"DROP SCHEMA IF EXISTS {schema} CASCADE"))
        conn.execute(text(f"CREATE SCHEMA {schema}"))
        conn.execute(text(f"SET search_path TO {schema}"))
        conn.execute(text(f"CREATE TABLE {KEYS} (id SERIAL PRIMARY KEY, label VARCHAR(255))"))
        conn.execute(text(f"CREATE TABLE {X509} (id SERIAL PRIMARY KEY, descr VARCHAR(255), "
                          f"hsm_key_id INTEGER REFERENCES {KEYS} (id))"))
        conn.execute(text(f"INSERT INTO {KEYS} (id, label) VALUES (1, 'token-key'), (2, 'other-key')"))
        conn.execute(text(f"INSERT INTO {X509} (id, descr, hsm_key_id) VALUES (1, 'on key', 1), "
                          f"(2, 'local', NULL), (3, 'local too', 1)"))
        assert _migration().refusal(conn).startswith(
            "Upgrade refused: HSM key 'token-key' (#1) backs 2 X.509 CAs: 'on key' (#1), 'local too' (#3).")
        with pytest.raises(RuntimeError):
            _migration().upgrade(conn)
        conn.execute(text(f"UPDATE {X509} SET hsm_key_id = NULL WHERE id = 3"))
        if index_of_2x:
            conn.execute(text(f"CREATE UNIQUE INDEX {X509_INDEX} ON {X509}(hsm_key_id) "
                              f"WHERE hsm_key_id IS NOT NULL"))
        for _ in range(2):
            _migration().upgrade(conn)
        assert conn.execute(text("SELECT indexdef FROM pg_indexes WHERE schemaname = :s AND tablename = :t "
                                 "AND indexname = :i"), {'s': schema, 't': X509, 'i': X509_INDEX}).scalar() \
            == f'CREATE UNIQUE INDEX {X509_INDEX} ON {schema}.{X509} USING btree (hsm_key_id)'
        with pytest.raises(IntegrityError):
            conn.execute(text(f"UPDATE {X509} SET hsm_key_id = 1 WHERE id = 2"))
    finally:
        conn.rollback()
        conn.execute(text(f"DROP SCHEMA IF EXISTS {schema} CASCADE"))
        conn.commit()
        conn.close()
        engine.dispose()
