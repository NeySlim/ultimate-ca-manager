"""Migration 139 adds certificates.key_bits and sig_hash, filled from crt, and the
indexes behind the dashboard aggregates; it is idempotent on both backends."""
import importlib
import os
import sqlite3

import pytest
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec, ed25519, rsa
from sqlalchemy import create_engine, inspect, text

from tests.dashboard_pem import self_signed, sha1_rsa

PG_URL = os.getenv('UCM_TEST_PG_URL')
INDEXES = {
    'certificates': {'ix_certificates_valid_to', 'ix_certificates_created_at'},
    'acme_orders': {'ix_acme_orders_status_created_at'},
}


def _migration():
    return importlib.import_module('migrations._from_2_254.139_dashboard_aggregates')


def _rows():
    return [
        (1, self_signed(rsa.generate_private_key(public_exponent=65537, key_size=2048))),
        (2, sha1_rsa()),
        (3, self_signed(ec.generate_private_key(ec.SECP384R1()), hashes.SHA384())),
        (4, self_signed(ed25519.Ed25519PrivateKey.generate())),
        (5, 'not a certificate'),
        (6, None),
    ]


EXPECTED = [(1, 2048, 'sha256'), (2, 2048, 'sha1'), (3, 384, 'sha384'),
            (4, None, None), (5, None, None), (6, None, None)]


def _sqlite_schema(conn):
    conn.execute('CREATE TABLE certificates (id INTEGER PRIMARY KEY, crt TEXT, valid_to DATETIME, '
                 'created_at DATETIME)')
    conn.execute('CREATE TABLE acme_orders (id INTEGER PRIMARY KEY, status VARCHAR(20), created_at DATETIME)')


def test_sqlite_backfills_and_indexes_idempotently(monkeypatch):
    monkeypatch.setattr(_migration(), '_BATCH', 2)  # several batches over six rows
    conn = sqlite3.connect(':memory:')
    _sqlite_schema(conn)
    conn.executemany('INSERT INTO certificates (id, crt) VALUES (?, ?)', _rows())
    _migration().upgrade(conn)
    _migration().upgrade(conn)
    assert conn.execute('SELECT id, key_bits, sig_hash FROM certificates ORDER BY id').fetchall() == EXPECTED
    for table, names in INDEXES.items():
        present = {r[1] for r in conn.execute(f'PRAGMA index_list({table})')}
        assert names <= present, table


def test_sqlite_keeps_values_already_written():
    conn = sqlite3.connect(':memory:')
    _sqlite_schema(conn)
    conn.execute('ALTER TABLE certificates ADD COLUMN key_bits INTEGER')
    conn.execute('ALTER TABLE certificates ADD COLUMN sig_hash VARCHAR(20)')
    conn.execute('INSERT INTO certificates (id, crt, key_bits, sig_hash) VALUES (?, ?, 4096, ?)',
                 (1, _rows()[0][1], 'sha512'))
    _migration().upgrade(conn)
    assert conn.execute('SELECT key_bits, sig_hash FROM certificates').fetchone() == (4096, 'sha512')


def test_sqlite_without_the_tables_is_a_no_op():
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
    schema = f"migtest_139_{os.getenv('PYTEST_XDIST_WORKER', 'main')}"
    engine = create_engine(PG_URL)
    conn = engine.connect()
    try:
        conn.execute(text(f'DROP SCHEMA IF EXISTS {schema} CASCADE'))
        conn.execute(text(f'CREATE SCHEMA {schema}'))
        conn.execute(text(f'SET search_path TO {schema}'))
        conn.execute(text('CREATE TABLE certificates (id SERIAL PRIMARY KEY, crt TEXT, '
                          'valid_to TIMESTAMP, created_at TIMESTAMP)'))
        conn.execute(text('CREATE TABLE acme_orders (id SERIAL PRIMARY KEY, status VARCHAR(20), '
                          'created_at TIMESTAMP)'))
        conn.execute(text('INSERT INTO certificates (id, crt) VALUES (:id, :crt)'),
                     [{'id': i, 'crt': c} for i, c in _rows()])
        _migration().upgrade(conn)
        _migration().upgrade(conn)
        assert conn.execute(text('SELECT id, key_bits, sig_hash FROM certificates ORDER BY id')
                            ).fetchall() == EXPECTED
        inspector = inspect(conn)
        for table, names in INDEXES.items():
            assert names <= {i['name'] for i in inspector.get_indexes(table, schema=schema)}, table
    finally:
        conn.rollback()
        conn.execute(text(f'DROP SCHEMA IF EXISTS {schema} CASCADE'))
        conn.commit()
        conn.close()
        engine.dispose()


def test_the_app_schema_carries_the_columns_and_indexes(app):
    from models import db
    with app.app_context():
        inspector = inspect(db.engine)
        columns = {c['name'] for c in inspector.get_columns('certificates')}
        assert {'key_bits', 'sig_hash'} <= columns
        for table, names in INDEXES.items():
            assert names <= {i['name'] for i in inspector.get_indexes(table)}, table
