"""Migration 148: replaced-certificate entries get the fingerprint of the row they name, both backends."""
import base64
import importlib.util
import json
import os
import sqlite3
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import NameOID

TABLES = ('CREATE TABLE certificates (id INTEGER PRIMARY KEY, serial_number TEXT, crt TEXT)',
          'CREATE TABLE acme_client_orders (id INTEGER PRIMARY KEY, replaced_certificates TEXT)')


def _migration():
    path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                        'migrations', '_from_2_254', '148_acme_replaced_certificate_fingerprints.py')
    spec = importlib.util.spec_from_file_location('m148', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _certificate():
    key = ec.generate_private_key(ec.SECP256R1())
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, 'm148.example')])
    now = datetime.now(timezone.utc)
    cert = (x509.CertificateBuilder().subject_name(name).issuer_name(name)
            .public_key(key.public_key()).serial_number(12)
            .not_valid_before(now).not_valid_after(now + timedelta(days=1))
            .sign(key, hashes.SHA256()))
    stored = base64.b64encode(cert.public_bytes(serialization.Encoding.PEM)).decode()
    return stored, cert.fingerprint(hashes.SHA256()).hex()


def _scene():
    stored, digest = _certificate()
    entries = [{'certificate_id': 7, 'serial': '12'},     # still the row it names
               {'certificate_id': 7, 'serial': '13'},     # the number went to another row
               {'certificate_id': 8, 'serial': '14'}]     # the row is gone
    rows = [('INSERT INTO certificates (id, serial_number, crt) VALUES (7, :s, :c)',
             {'s': '12', 'c': stored}),
            ('INSERT INTO acme_client_orders (id, replaced_certificates) VALUES (1, :r)',
             {'r': json.dumps(entries)})]
    expected = [dict(entries[0], fingerprint=digest), entries[1], entries[2]]
    return rows, expected


def test_sqlite_entries_get_the_fingerprint_once():
    migration = _migration()
    assert migration.pg_compatible is True
    rows, expected = _scene()
    conn = sqlite3.connect(':memory:')
    for statement in TABLES:
        conn.execute(statement)
    for statement, values in rows:
        conn.execute(statement, values)
    migration.upgrade(conn)
    first = conn.execute('SELECT replaced_certificates FROM acme_client_orders').fetchone()[0]
    migration.upgrade(conn)
    assert conn.execute('SELECT replaced_certificates FROM acme_client_orders').fetchone()[0] == first
    assert json.loads(first) == expected


def test_sqlite_without_the_tables_is_a_no_op():
    conn = sqlite3.connect(':memory:')
    _migration().upgrade(conn)
    assert conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall() == []


@pytest.mark.postgres
@pytest.mark.skipif(not os.getenv('UCM_TEST_PG_URL'), reason='UCM_TEST_PG_URL not set')
def test_postgresql_entries_get_the_fingerprint_once():
    from sqlalchemy import create_engine, text
    schema = f"m148_{os.getenv('PYTEST_XDIST_WORKER', 'main')}_{uuid.uuid4().hex[:6]}"
    engine = create_engine(os.environ['UCM_TEST_PG_URL'])
    migration = _migration()
    rows, expected = _scene()
    try:
        with engine.begin() as conn:
            conn.execute(text(f'CREATE SCHEMA {schema}'))
            conn.execute(text(f'SET search_path TO {schema}'))
            for statement in TABLES:
                conn.execute(text(statement))
            for statement, values in rows:
                conn.execute(text(statement), values)
        for _ in range(2):
            with engine.begin() as conn:
                conn.execute(text(f'SET search_path TO {schema}'))
                migration.upgrade(conn)
        with engine.begin() as conn:
            conn.execute(text(f'SET search_path TO {schema}'))
            value = conn.execute(text('SELECT replaced_certificates FROM acme_client_orders')).scalar()
            assert json.loads(value) == expected
    finally:
        with engine.begin() as conn:
            conn.execute(text(f'DROP SCHEMA IF EXISTS {schema} CASCADE'))
        engine.dispose()
