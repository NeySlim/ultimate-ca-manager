"""Migration 162: a 2.x TSA that signs with its CA keeps doing so, explicitly; nothing else is written."""
import importlib
import os
import sqlite3

import pytest
from sqlalchemy import create_engine, text

from models import CA, SystemConfig

PG_URL = os.getenv('UCM_TEST_PG_URL')
SETTINGS = SystemConfig.__tablename__
CAS = CA.__tablename__
KEY = 'tsa_require_dedicated_cert'
CA_REFID = 'tsa-ca-0001'

# (case, settings before, rows after): the compatibility case writes false, every other leaves the table as it was
CASES = [
    ('ca_signs_enabled_by_default', {'tsa_ca_refid': CA_REFID},
     {'tsa_ca_refid': CA_REFID, KEY: 'false'}),
    ('ca_signs_enabled_explicitly', {'tsa_enabled': 'true', 'tsa_ca_refid': CA_REFID, 'tsa_signer_cert_refid': ''},
     {'tsa_enabled': 'true', 'tsa_ca_refid': CA_REFID, 'tsa_signer_cert_refid': '', KEY: 'false'}),
    ('dedicated_signer', {'tsa_ca_refid': CA_REFID, 'tsa_signer_cert_refid': 'cert-1'}, None),
    ('tsa_disabled', {'tsa_enabled': 'false', 'tsa_ca_refid': CA_REFID}, None),
    ('tsa_enabled_not_the_exact_word', {'tsa_enabled': 'yes', 'tsa_ca_refid': CA_REFID}, None),
    ('already_true', {'tsa_ca_refid': CA_REFID, KEY: 'true'}, None),
    ('already_false', {'tsa_ca_refid': CA_REFID, KEY: 'false'}, None),
    ('no_ca_configured', {'tsa_enabled': 'true', 'tsa_ca_refid': ''}, None),
    ('ca_gone', {'tsa_ca_refid': 'tsa-ca-deleted'}, None),
    ('fresh', {}, None),
    # 2.x read tsa_enabled as "no row, or str(value).lower() == 'true'": these rows were off
    ('tsa_enabled_null', {'tsa_enabled': None, 'tsa_ca_refid': CA_REFID}, None),
    ('tsa_enabled_padded', {'tsa_enabled': ' true', 'tsa_ca_refid': CA_REFID}, None),
    ('tsa_enabled_upper_case', {'tsa_enabled': 'TRUE', 'tsa_ca_refid': CA_REFID},
     {'tsa_enabled': 'TRUE', 'tsa_ca_refid': CA_REFID, KEY: 'false'}),
    # 2.x read the key as str(value).lower() == 'true': any other row was "no", 3.0 reads it as yes
    *[(f'key_read_as_no_{i}', {'tsa_ca_refid': CA_REFID, KEY: v}, {'tsa_ca_refid': CA_REFID, KEY: 'false'})
      for i, v in enumerate(('', None, 'no', '0', ' true', 'False'))],
    ('key_upper_case_true', {'tsa_ca_refid': CA_REFID, KEY: 'TRUE'}, None),
    ('key_read_as_no_tsa_disabled', {'tsa_enabled': 'false', 'tsa_ca_refid': CA_REFID, KEY: ''}, None),
]


def _migration():
    return importlib.import_module('migrations._from_2_254.162_tsa_ca_signer_kept')


def test_the_step_is_part_of_the_upgrade():
    from migrations._from_2_254 import STEPS
    assert STEPS[-1] == '162_tsa_ca_signer_kept'


@pytest.mark.parametrize('case,before,after', CASES, ids=[c[0] for c in CASES])
def test_sqlite(case, before, after):
    conn = sqlite3.connect(':memory:')
    conn.execute(f"CREATE TABLE {SETTINGS} (id INTEGER PRIMARY KEY AUTOINCREMENT, "
                 "key VARCHAR(100) NOT NULL UNIQUE, value TEXT, encrypted BOOLEAN)")
    conn.execute(f"CREATE TABLE {CAS} (id INTEGER PRIMARY KEY AUTOINCREMENT, refid VARCHAR(36))")
    conn.execute(f"INSERT INTO {CAS} (refid) VALUES (?)", (CA_REFID,))
    conn.executemany(f"INSERT INTO {SETTINGS} (key, value) VALUES (?, ?)", before.items())
    conn.commit()
    for _ in range(2):
        _migration().upgrade(conn)
        assert dict(conn.execute(f"SELECT key, value FROM {SETTINGS}")) == (after or before)


def test_sqlite_without_the_tables_is_a_no_op():
    conn = sqlite3.connect(':memory:')
    _migration().upgrade(conn)
    assert conn.execute("SELECT count(*) FROM sqlite_master").fetchone()[0] == 0


@pytest.mark.postgres
@pytest.mark.skipif(not PG_URL, reason='UCM_TEST_PG_URL not set')
@pytest.mark.parametrize('case,before,after', CASES, ids=[c[0] for c in CASES])
def test_postgres(case, before, after):
    schema = f"migtest_162_{os.getenv('PYTEST_XDIST_WORKER', 'main')}"
    engine = create_engine(PG_URL)
    conn = engine.connect()
    try:
        conn.execute(text(f"DROP SCHEMA IF EXISTS {schema} CASCADE"))
        conn.execute(text(f"CREATE SCHEMA {schema}"))
        conn.execute(text(f"SET search_path TO {schema}"))
        conn.execute(text(f"CREATE TABLE {SETTINGS} (id SERIAL PRIMARY KEY, "
                          "key VARCHAR(100) NOT NULL UNIQUE, value TEXT, encrypted BOOLEAN)"))
        conn.execute(text(f"CREATE TABLE {CAS} (id SERIAL PRIMARY KEY, refid VARCHAR(36))"))
        conn.execute(text(f"INSERT INTO {CAS} (refid) VALUES (:r)"), {'r': CA_REFID})
        for k, v in before.items():
            conn.execute(text(f"INSERT INTO {SETTINGS} (key, value) VALUES (:k, :v)"), {'k': k, 'v': v})
        for _ in range(2):
            _migration().upgrade(conn)
            assert dict(conn.execute(text(f"SELECT key, value FROM {SETTINGS}")).fetchall()) \
                == (after or before)
    finally:
        conn.rollback()
        conn.execute(text(f"DROP SCHEMA IF EXISTS {schema} CASCADE"))
        conn.commit()
        conn.close()
        engine.dispose()


@pytest.mark.postgres
@pytest.mark.skipif(not PG_URL, reason='UCM_TEST_PG_URL not set')
def test_postgres_without_the_tables_is_a_no_op():
    schema = f"migtest_162e_{os.getenv('PYTEST_XDIST_WORKER', 'main')}"
    engine = create_engine(PG_URL)
    conn = engine.connect()
    try:
        conn.execute(text(f"DROP SCHEMA IF EXISTS {schema} CASCADE"))
        conn.execute(text(f"CREATE SCHEMA {schema}"))
        conn.execute(text(f"SET search_path TO {schema}"))
        _migration().upgrade(conn)
        assert conn.execute(text("SELECT count(*) FROM information_schema.tables "
                                 "WHERE table_schema = :s"), {'s': schema}).scalar() == 0
    finally:
        conn.rollback()
        conn.execute(text(f"DROP SCHEMA IF EXISTS {schema} CASCADE"))
        conn.commit()
        conn.close()
        engine.dispose()
