"""Migration 130: an enrolment's serial is unique per issuer, the issuer filled from the PEM."""
import importlib
import os
import sqlite3
from datetime import datetime, timedelta, timezone

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import NameOID
from sqlalchemy import create_engine, text
from sqlalchemy.exc import IntegrityError

from models.auth_certificate import AuthCertificate

PG_URL = os.getenv('UCM_TEST_PG_URL')
TABLE = AuthCertificate.__tablename__
COLUMNS = ('id, user_id, cert_serial, cert_subject, cert_issuer, cert_fingerprint, '
           'name, enabled, cert_pem')


def _migration():
    return importlib.import_module('migrations.130_auth_certificate_serial_per_issuer')


def _pem(issuer_cn, serial):
    key = ec.generate_private_key(ec.SECP256R1())
    now = datetime.now(timezone.utc)
    cert = (x509.CertificateBuilder()
            .subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, 'client')]))
            .issuer_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, issuer_cn)]))
            .public_key(key.public_key()).serial_number(serial)
            .not_valid_before(now - timedelta(days=1)).not_valid_after(now + timedelta(days=1))
            .sign(key, hashes.SHA256()))
    return cert.public_bytes(serialization.Encoding.PEM)


def _ddl(serial_column, blob='BLOB'):
    return f"""CREATE TABLE {TABLE} (
        id INTEGER PRIMARY KEY NOT NULL, user_id INTEGER NOT NULL, {serial_column},
        cert_subject TEXT NOT NULL, cert_issuer TEXT, cert_fingerprint VARCHAR(128),
        name VARCHAR(128), enabled BOOLEAN NOT NULL, valid_from TIMESTAMP, valid_until TIMESTAMP,
        created_at TIMESTAMP, last_used_at TIMESTAMP, cert_pem {blob})"""


# (id, serial, issuer, pem): a legacy row with only its PEM, one with nothing, one complete
ROWS = [
    (1, '10', None, _pem('Legacy CA', 16)),
    (2, '11', None, None),
    (3, '12', 'CN=Known CA', None),
]
EXPECTED = {1: ('10', 'CN=Legacy CA'), 2: ('11', ''), 3: ('12', 'CN=Known CA')}


def _seed(execute):
    for row_id, serial, issuer, pem in ROWS:
        execute(f"INSERT INTO {TABLE} ({COLUMNS}) VALUES (:id, 1, :serial, 'CN=client', :issuer, '', "
                f":name, TRUE, :pem)",
                {'id': row_id, 'serial': serial, 'issuer': issuer, 'name': f'row {row_id}', 'pem': pem})


def _sqlite(serial_column, with_index):
    conn = sqlite3.connect(':memory:')
    conn.execute(_ddl(serial_column))
    if with_index:
        conn.execute(f"CREATE UNIQUE INDEX ix_{TABLE}_cert_serial ON {TABLE} (cert_serial)")
    _seed(conn.execute)
    conn.commit()
    return conn


@pytest.mark.parametrize('serial_column, with_index', [
    ('cert_serial VARCHAR(128) NOT NULL', True),          # baseline and create_all
    ('cert_serial VARCHAR(128) NOT NULL UNIQUE', False),  # column-level constraint: rebuilt
])
def test_sqlite_keeps_the_rows_and_makes_the_serial_unique_per_issuer(serial_column, with_index):
    conn = _sqlite(serial_column, with_index)
    _migration().upgrade(conn)
    _migration().upgrade(conn)
    got = {r[0]: (r[1], r[2]) for r in conn.execute(f"SELECT id, cert_serial, cert_issuer FROM {TABLE}")}
    assert got == EXPECTED
    assert conn.execute(f"SELECT name, cert_pem FROM {TABLE} WHERE id = 1").fetchone() == ('row 1', ROWS[0][3])

    insert = (f"INSERT INTO {TABLE} (user_id, cert_serial, cert_subject, cert_issuer, enabled) "
              "VALUES (1, '12', 'CN=other', ?, 1)")
    conn.execute(insert, ('CN=Another CA',))
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(insert, ('CN=Known CA',))
    indexes = {r[1]: r[2] for r in conn.execute(f"PRAGMA index_list({TABLE})")}
    assert indexes[f'uq_{TABLE}_issuer_serial'] == 1
    assert indexes[f'ix_{TABLE}_cert_serial'] == 0


def test_sqlite_without_the_table_is_a_no_op():
    _migration().upgrade(sqlite3.connect(':memory:'))


def test_a_fresh_schema_holds_the_same_index():
    engine = create_engine('sqlite://')
    with engine.begin() as conn:
        conn.execute(text("CREATE TABLE users (id INTEGER PRIMARY KEY)"))
    AuthCertificate.__table__.create(engine)
    with engine.connect() as conn:
        indexes = {r[1]: r[2] for r in conn.execute(text(f"PRAGMA index_list({TABLE})"))}
    assert indexes[f'uq_{TABLE}_issuer_serial'] == 1 and indexes[f'ix_{TABLE}_cert_serial'] == 0
    insert = AuthCertificate.__table__.insert()
    values = dict(user_id=1, cert_serial='42', cert_subject='CN=c', enabled=True)
    with engine.begin() as conn:
        conn.execute(insert.values(cert_issuer='CN=A', **values))
        conn.execute(insert.values(cert_issuer='CN=B', **values))
    with pytest.raises(IntegrityError):
        with engine.begin() as conn:
            conn.execute(insert.values(cert_issuer='CN=A', **values))


@pytest.mark.postgres
@pytest.mark.skipif(not PG_URL, reason='UCM_TEST_PG_URL not set')
def test_postgres_keeps_the_rows_and_makes_the_serial_unique_per_issuer():
    schema = f"migtest_130_{os.getenv('PYTEST_XDIST_WORKER', 'main')}"
    engine = create_engine(PG_URL)
    conn = engine.connect()
    try:
        conn.execute(text(f"DROP SCHEMA IF EXISTS {schema} CASCADE"))
        conn.execute(text(f"CREATE SCHEMA {schema}"))
        conn.execute(text(f"SET search_path TO {schema}"))
        conn.execute(text(_ddl('cert_serial VARCHAR(128) NOT NULL', blob='BYTEA')))
        conn.execute(text(f"CREATE UNIQUE INDEX ix_{TABLE}_cert_serial ON {TABLE} (cert_serial)"))
        conn.execute(text(f"ALTER TABLE {TABLE} ADD CONSTRAINT {TABLE}_cert_serial_key UNIQUE (cert_serial)"))
        _seed(lambda sql, params: conn.execute(text(sql), params))
        _migration().upgrade(conn)
        _migration().upgrade(conn)
        got = {r[0]: (r[1], r[2]) for r in conn.execute(text(f"SELECT id, cert_serial, cert_issuer FROM {TABLE}"))}
        assert got == EXPECTED
        insert = text(f"INSERT INTO {TABLE} (id, user_id, cert_serial, cert_subject, cert_issuer, enabled) "
                      "VALUES (:id, 1, '12', 'CN=other', :issuer, TRUE)")
        conn.execute(insert, {'id': 10, 'issuer': 'CN=Another CA'})
        savepoint = conn.begin_nested()
        with pytest.raises(IntegrityError):
            conn.execute(insert, {'id': 11, 'issuer': 'CN=Known CA'})
        savepoint.rollback()
    finally:
        conn.rollback()
        conn.execute(text(f"DROP SCHEMA IF EXISTS {schema} CASCADE"))
        conn.commit()
        conn.close()
        engine.dispose()
