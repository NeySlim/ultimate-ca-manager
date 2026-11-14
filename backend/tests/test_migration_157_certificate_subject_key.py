"""Migration 157 adds certificates.subject_key, filled from crt, and its index with caref;
it is idempotent on both backends."""
import base64
import importlib
import os
import sqlite3

import pytest
from cryptography import x509
from cryptography.hazmat.primitives.asymmetric import rsa
from sqlalchemy import create_engine, inspect, text

from tests.dashboard_pem import self_signed
from utils.dn_match import name_key

PG_URL = os.getenv('UCM_TEST_PG_URL')
INDEX = 'ix_certificates_caref_subject_key'


def _migration():
    return importlib.import_module('migrations._from_2_254.157_certificate_subject_key')


def _key(cn):
    return name_key(x509.Name([x509.NameAttribute(x509.oid.NameOID.COMMON_NAME, cn)]))


def _rows():
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    return [(1, self_signed(key, cn='Alice Martin')), (2, self_signed(key, cn='alice  martin')),
            (3, self_signed(key, cn='WIN11-WiFi')), (4, base64.b64encode(b'not a certificate').decode()),
            (5, None)]


EXPECTED = [(1, _key('Alice Martin')), (2, _key('Alice Martin')), (3, _key('win11-wifi')), (4, None), (5, None)]


def test_the_table_is_the_model_s():
    from models import Certificate
    assert Certificate.__tablename__ == 'certificates'
    assert INDEX in {i.name for i in Certificate.__table__.indexes}


def test_sqlite_backfills_and_indexes_idempotently(monkeypatch):
    monkeypatch.setattr(_migration(), '_BATCH', 2)  # several batches over five rows
    conn = sqlite3.connect(':memory:')
    conn.execute('CREATE TABLE certificates (id INTEGER PRIMARY KEY, caref VARCHAR(36), crt TEXT)')
    conn.executemany('INSERT INTO certificates (id, crt) VALUES (?, ?)', _rows())
    _migration().upgrade(conn)
    _migration().upgrade(conn)
    assert conn.execute('SELECT id, subject_key FROM certificates ORDER BY id').fetchall() == EXPECTED
    assert [r[2] for r in conn.execute(f'PRAGMA index_info({INDEX})')] == ['caref', 'subject_key']


def test_sqlite_without_the_table_is_a_no_op():
    conn = sqlite3.connect(':memory:')
    _migration().upgrade(conn)
    assert conn.execute('SELECT count(*) FROM sqlite_master').fetchone()[0] == 0


@pytest.mark.postgres
@pytest.mark.skipif(not PG_URL, reason='UCM_TEST_PG_URL not set')
def test_postgres_backfills_and_indexes_idempotently(monkeypatch):
    from tests.conftest import pg_bench_exclusive
    monkeypatch.setattr(_migration(), '_BATCH', 2)
    with pg_bench_exclusive():
        _postgres_round()


def _postgres_round():
    schema = f"migtest_157_{os.getenv('PYTEST_XDIST_WORKER', 'main')}"
    engine = create_engine(PG_URL)
    conn = engine.connect()
    try:
        conn.execute(text(f'DROP SCHEMA IF EXISTS {schema} CASCADE'))
        conn.execute(text(f'CREATE SCHEMA {schema}'))
        conn.execute(text(f'SET search_path TO {schema}'))
        conn.execute(text('CREATE TABLE certificates (id SERIAL PRIMARY KEY, caref VARCHAR(36), crt TEXT)'))
        conn.execute(text('INSERT INTO certificates (id, crt) VALUES (:id, :crt)'),
                     [{'id': i, 'crt': c} for i, c in _rows()])
        _migration().upgrade(conn)
        _migration().upgrade(conn)
        assert conn.execute(text('SELECT id, subject_key FROM certificates ORDER BY id')).fetchall() == EXPECTED
        indexes = {i['name']: i['column_names'] for i in inspect(conn).get_indexes('certificates', schema=schema)}
        assert indexes[INDEX] == ['caref', 'subject_key']
    finally:
        conn.rollback()
        conn.execute(text(f'DROP SCHEMA IF EXISTS {schema} CASCADE'))
        conn.commit()
        conn.close()
        engine.dispose()


def test_the_app_schema_carries_the_column_and_index(app):
    from models import db
    with app.app_context():
        inspector = inspect(db.engine)
        assert 'subject_key' in {c['name'] for c in inspector.get_columns('certificates')}
        assert INDEX in {i['name'] for i in inspector.get_indexes('certificates')}
