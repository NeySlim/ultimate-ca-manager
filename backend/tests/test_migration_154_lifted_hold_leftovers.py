"""Migration 154 deletes, once, the suspension records a lifted hold left linked to its
unrevoked row of the same serial under its CA or a twin of the same key, and nothing else
It does nothing on a base whose 2.x migration 136 already ran that cleanup (SQLite and
PostgreSQL)."""
import base64
import importlib
import os
import sqlite3
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import NameOID
from sqlalchemy import create_engine, text

from models import CA, Certificate, RevokedSerial

PG_URL = os.getenv('UCM_TEST_PG_URL')
CERTS, RECORDS, CAS = Certificate.__tablename__, RevokedSerial.__tablename__, CA.__tablename__
_DDL = [f"CREATE TABLE {CAS} (id INTEGER PRIMARY KEY, refid VARCHAR(50), crt TEXT)",
        f"CREATE TABLE {CERTS} (id INTEGER PRIMARY KEY, caref VARCHAR(50), serial_number VARCHAR(100), "
        "revoked BOOLEAN)",
        f"CREATE TABLE {RECORDS} (id INTEGER PRIMARY KEY, caref VARCHAR(50), serial_number VARCHAR(100), "
        "revoke_reason VARCHAR(50), certificate_id INTEGER)"]


def _migration():
    return importlib.import_module('migrations.154_lifted_hold_leftovers')


def _ca(key, cn='m154 root'):
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, cn)])
    now = datetime.now(timezone.utc)
    cert = (x509.CertificateBuilder().subject_name(name).issuer_name(name).public_key(key.public_key())
            .serial_number(x509.random_serial_number()).not_valid_before(now - timedelta(days=1))
            .not_valid_after(now + timedelta(days=1)).sign(key, hashes.SHA256()))
    return base64.b64encode(cert.public_bytes(serialization.Encoding.PEM)).decode()


KEY, OTHER_KEY = ec.generate_private_key(ec.SECP256R1()), ec.generate_private_key(ec.SECP256R1())
CA_ROWS = [(1, 'ca-a', _ca(KEY)), (2, 'ca-twin', _ca(KEY)), (3, 'ca-other', _ca(OTHER_KEY)),
           (4, 'ca-namesake', _ca(KEY, 'm154 other name'))]
CERT_ROWS = [(1, 'ca-a', '100', False), (2, 'ca-a', '200', True), (3, 'ca-a', '300', None),
             (4, 'ca-a', '400', False)]
RECORD_ROWS = [  # (id, caref, serial, reason, certificate_id), kept afterwards?
    ((1, 'ca-a', '100', 'certificateHold', 1), False),     # the leftover
    ((2, 'ca-twin', '100', 'certificateHold', 1), False),  # under a twin of the same key
    ((3, 'ca-a', '300', 'certificate_hold', 3), False),    # older spelling, row never said
    ((4, 'ca-a', '200', 'certificateHold', 2), True),      # the row is held: a real hold
    ((5, 'ca-a', '100', 'keyCompromise', 1), True),        # a final reason always revokes
    ((6, 'ca-a', '400', 'certificateHold', None), True),   # not linked
    ((7, 'ca-a', '999', 'certificateHold', 4), True),      # another serial than the row's
    ((8, 'ca-other', '400', 'certificateHold', 4), True),  # another key
    ((9, 'ca-namesake', '400', 'certificateHold', 4), True),  # same key, another subject
]
KEPT = sorted(row[0] for row, kept in RECORD_ROWS if kept)
ALL = sorted(row[0] for row, _ in RECORD_ROWS)
CLEANED_IN_2X = '136_lifted_hold_leftovers'
_MIGRATIONS_DDL = "CREATE TABLE _migrations (name VARCHAR(255) PRIMARY KEY)"


def _sqlite():
    conn = sqlite3.connect(':memory:')
    for ddl in _DDL:
        conn.execute(ddl)
    conn.executemany(f"INSERT INTO {CAS} VALUES (?, ?, ?)", CA_ROWS)
    conn.executemany(f"INSERT INTO {CERTS} VALUES (?, ?, ?, ?)", CERT_ROWS)
    conn.executemany(f"INSERT INTO {RECORDS} VALUES (?, ?, ?, ?, ?)", [row for row, _ in RECORD_ROWS])
    conn.commit()
    return conn


def test_sqlite_deletes_the_leftovers_once():
    conn = _sqlite()
    for _ in range(2):
        _migration().upgrade(conn)
        assert [r for (r,) in conn.execute(f"SELECT id FROM {RECORDS} ORDER BY id")] == KEPT


def test_sqlite_after_the_2x_cleanup_does_nothing():
    """A 2.x base that ran 136 had its one cleanup: a hold linked since is real and stays."""
    conn = _sqlite()
    conn.execute(_MIGRATIONS_DDL)
    conn.execute("INSERT INTO _migrations (name) VALUES (?)", (CLEANED_IN_2X,))
    conn.commit()
    _migration().upgrade(conn)
    assert [r for (r,) in conn.execute(f"SELECT id FROM {RECORDS} ORDER BY id")] == ALL


def test_sqlite_without_tables_does_nothing():
    _migration().upgrade(sqlite3.connect(':memory:'))


@pytest.mark.postgres
@pytest.mark.skipif(not PG_URL, reason='UCM_TEST_PG_URL not set')
@pytest.mark.parametrize('cleaned_in_2x', [False, True])
def test_postgresql(cleaned_in_2x):
    schema = f"m154_{os.getenv('PYTEST_XDIST_WORKER', 'main')}_{uuid.uuid4().hex[:6]}"
    admin = create_engine(PG_URL)
    with admin.begin() as conn:
        conn.execute(text(f'CREATE SCHEMA {schema}'))
    engine = create_engine(PG_URL, connect_args={'options': f'-csearch_path={schema}'})
    try:
        with engine.begin() as conn:
            for ddl in _DDL:
                conn.execute(text(ddl))
            conn.execute(text(f"INSERT INTO {CAS} VALUES (:i, :r, :c)"),
                         [dict(zip('irc', row)) for row in CA_ROWS])
            conn.execute(text(f"INSERT INTO {CERTS} VALUES (:i, :c, :s, :v)"),
                         [dict(zip('icsv', row)) for row in CERT_ROWS])
            conn.execute(text(f"INSERT INTO {RECORDS} VALUES (:i, :c, :s, :r, :t)"),
                         [dict(zip('icsrt', row)) for row, _ in RECORD_ROWS])
            if cleaned_in_2x:
                conn.execute(text(_MIGRATIONS_DDL))
                conn.execute(text("INSERT INTO _migrations (name) VALUES (:n)"), {'n': CLEANED_IN_2X})
        expected = ALL if cleaned_in_2x else KEPT
        for _ in range(2):
            with engine.begin() as conn:
                _migration().upgrade(conn)
            with engine.begin() as conn:
                assert [r for (r,) in conn.execute(text(f"SELECT id FROM {RECORDS} ORDER BY id"))] == expected
    finally:
        engine.dispose()
        with admin.begin() as conn:
            conn.execute(text(f'DROP SCHEMA IF EXISTS {schema} CASCADE'))
        admin.dispose()
