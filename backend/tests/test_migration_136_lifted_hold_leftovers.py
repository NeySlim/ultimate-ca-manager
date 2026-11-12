"""Migration 136 deletes, once, the suspension records a lifted hold left linked to its
unrevoked row, naming its serial in a spelling no other serial has, under its CA or a twin
of the same key, and nothing else (SQLite and PostgreSQL)."""
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
        "revoked BOOLEAN, crt TEXT)",
        f"CREATE TABLE {RECORDS} (id INTEGER PRIMARY KEY, caref VARCHAR(50), serial_number VARCHAR(100), "
        "revoke_reason VARCHAR(50), certificate_id INTEGER)"]


def _migration():
    return importlib.import_module('migrations.136_lifted_hold_leftovers')


def _cert(key, cn, serial=None):
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, cn)])
    now = datetime.now(timezone.utc)
    cert = (x509.CertificateBuilder().subject_name(name).issuer_name(name).public_key(key.public_key())
            .serial_number(serial or x509.random_serial_number()).not_valid_before(now - timedelta(days=1))
            .not_valid_after(now + timedelta(days=1)).sign(key, hashes.SHA256()))
    return base64.b64encode(cert.public_bytes(serialization.Encoding.PEM)).decode()


KEY, OTHER_KEY = ec.generate_private_key(ec.SECP256R1()), ec.generate_private_key(ec.SECP256R1())
CA_ROWS = [(1, 'ca-a', _cert(KEY, 'm136 root')), (2, 'ca-twin', _cert(KEY, 'm136 root')),
           (3, 'ca-other', _cert(OTHER_KEY, 'm136 root')), (4, 'ca-namesake', _cert(KEY, 'm136 other'))]
LETTERED = 0xabc123      # hex spellings with a letter
DIGITS = 0x123456        # hex spelling all digits: '123456' is another serial's decimal
CERT_ROWS = [(1, 'ca-a', str(LETTERED), False, _cert(KEY, 'leaf', LETTERED)),
             (2, 'ca-a', '200', True, None), (3, 'ca-a', '300', None, None),
             (4, 'ca-a', '400', False, None),
             (5, 'ca-a', format(DIGITS, 'x'), False, _cert(KEY, 'leaf digits', DIGITS))]
RECORD_ROWS = [  # (id, caref, serial, reason, certificate_id), kept afterwards?
    ((1, 'ca-a', format(LETTERED, 'X'), 'certificateHold', 1), False),   # another spelling of the row's
    ((2, 'ca-twin', str(LETTERED), 'certificateHold', 1), False),        # under a twin of the same key
    ((3, 'ca-a', '300', 'certificate_hold', 3), False),                  # older reason spelling, row never said
    ((4, 'ca-a', '200', 'certificateHold', 2), True),                    # the row is held: a real hold
    ((5, 'ca-a', str(LETTERED), 'keyCompromise', 1), True),              # a final reason always revokes
    ((6, 'ca-a', '400', 'certificateHold', None), True),                 # not linked
    ((7, 'ca-a', '999', 'certificateHold', 4), True),                    # another serial than the row's
    ((8, 'ca-other', '400', 'certificateHold', 4), True),                # another key
    ((9, 'ca-namesake', '400', 'certificateHold', 4), True),             # same key, another subject
    ((10, 'ca-a', format(DIGITS, 'x'), 'certificateHold', 5), True),     # all digits: names another serial
    ((11, 'ca-a', str(DIGITS), 'certificateHold', 5), False),            # the decimal of the row's serial
]
KEPT = sorted(row[0] for row, kept in RECORD_ROWS if kept)


def _sqlite():
    conn = sqlite3.connect(':memory:')
    for ddl in _DDL:
        conn.execute(ddl)
    conn.executemany(f"INSERT INTO {CAS} VALUES (?, ?, ?)", CA_ROWS)
    conn.executemany(f"INSERT INTO {CERTS} VALUES (?, ?, ?, ?, ?)", CERT_ROWS)
    conn.executemany(f"INSERT INTO {RECORDS} VALUES (?, ?, ?, ?, ?)", [row for row, _ in RECORD_ROWS])
    conn.commit()
    return conn


def test_sqlite_deletes_the_leftovers_once():
    conn = _sqlite()
    for _ in range(2):
        _migration().upgrade(conn)
        assert [r for (r,) in conn.execute(f"SELECT id FROM {RECORDS} ORDER BY id")] == KEPT


def test_sqlite_without_tables_does_nothing():
    _migration().upgrade(sqlite3.connect(':memory:'))


@pytest.mark.postgres
@pytest.mark.skipif(not PG_URL, reason='UCM_TEST_PG_URL not set')
def test_postgresql():
    schema = f"m136_{os.getenv('PYTEST_XDIST_WORKER', 'main')}_{uuid.uuid4().hex[:6]}"
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
            conn.execute(text(f"INSERT INTO {CERTS} VALUES (:i, :c, :s, :v, :p)"),
                         [dict(zip('icsvp', row)) for row in CERT_ROWS])
            conn.execute(text(f"INSERT INTO {RECORDS} VALUES (:i, :c, :s, :r, :t)"),
                         [dict(zip('icsrt', row)) for row, _ in RECORD_ROWS])
        for _ in range(2):
            with engine.begin() as conn:
                _migration().upgrade(conn)
            with engine.begin() as conn:
                assert [r for (r,) in conn.execute(text(f"SELECT id FROM {RECORDS} ORDER BY id"))] == KEPT
    finally:
        engine.dispose()
        with admin.begin() as conn:
            conn.execute(text(f'DROP SCHEMA IF EXISTS {schema} CASCADE'))
        admin.dispose()
