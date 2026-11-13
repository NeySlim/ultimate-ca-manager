"""Migration 144 stores every certificate serial in decimal, never merges two rows of
one CA into one serial, and lists them as migration 142 does (SQLite and PostgreSQL)."""
import base64
import importlib
import json
import os
import random
import sqlite3
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import NameOID
from sqlalchemy import create_engine, text

from models import Certificate, RevokedSerial, SystemConfig

PG_URL = os.getenv('UCM_TEST_PG_URL')
CERTS = Certificate.__tablename__
REVOKED = RevokedSerial.__tablename__
CONFIG = SystemConfig.__tablename__
INDEX = 'uix_certificates_ca_serial'
_DDL = [f"CREATE TABLE {CERTS} (id INTEGER PRIMARY KEY, caref VARCHAR(50), serial_number VARCHAR(100), crt TEXT)",
        f"CREATE TABLE {REVOKED} (id INTEGER PRIMARY KEY, caref VARCHAR(50), serial_number VARCHAR(100), "
        "certificate_id INTEGER)",
        f"CREATE TABLE {CONFIG} (id INTEGER PRIMARY KEY, key VARCHAR(100) UNIQUE NOT NULL, value TEXT, "
        "encrypted BOOLEAN, description VARCHAR(255), updated_at TIMESTAMP, updated_by VARCHAR(80))",
        f"CREATE UNIQUE INDEX {INDEX} ON {CERTS} (caref, serial_number) "
        "WHERE caref IS NOT NULL AND serial_number IS NOT NULL AND serial_number <> ''"]


def _migration():
    return importlib.import_module('migrations._from_2_254.144_canonical_certificate_serials')


def _certificate(serial):
    key = ec.generate_private_key(ec.SECP256R1())
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, 'm144')])
    now = datetime.now(timezone.utc)
    cert = (x509.CertificateBuilder().subject_name(name).issuer_name(name).public_key(key.public_key())
            .serial_number(serial).not_valid_before(now - timedelta(days=1))
            .not_valid_after(now + timedelta(days=1)).sign(key, hashes.SHA256()))
    return base64.b64encode(cert.public_bytes(serialization.Encoding.PEM)).decode()


# A serial whose hex spelling has no letter: only the certificate tells it from decimal
DIGITS = int('7' + ''.join(random.choice('0123456789') for _ in range(30)), 16)
DIGITS_CRT = _certificate(DIGITS)

MIXED = [  # (id, caref, serial_number, crt) -> stored afterwards
    ((1, 'ca-a', 'ab', None), '171'),
    ((2, 'ca-a', 'AB:CD', None), str(0xABCD)),
    ((3, 'ca-a', format(DIGITS, 'x'), DIGITS_CRT), str(DIGITS)),
    ((4, 'ca-a', '12', None), '12'),
    ((5, None, '0x10', None), '16'),
    ((8, 'ca-a', 'not a serial', None), 'not a serial'),
    ((9, 'ca-a', None, None), None),
    ((10, 'ca-a', '', None), ''),
    # 'c' becomes '12' while '12' (a hex spelling of 0x12) is still stored, until it becomes '18'
    ((11, 'ca-c', 'c', None), '12'),
    ((12, 'ca-c', '12', _certificate(0x12)), '18'),
]
# Same certificate stored under two spellings: neither row is converted
COLLIDING = [((6, 'ca-b', '1f', None), '1f'), ((7, 'ca-b', '31', None), '31')]
REVOCATIONS = [  # (id, caref, serial_number, certificate_id) -> stored afterwards
    ((1, 'ca-a', format(DIGITS, 'x'), 3), str(DIGITS)),
    ((2, 'ca-a', 'FF', None), '255'),
    ((3, 'ca-a', 'ab', 1), '171'),
    ((4, 'ca-b', '1f', 6), '31'),  # no unique index on revocations: always converted
]
PENDING = [{'caref': 'ca-b', 'serial_number': '31', 'count': 2,
            'rows': [{'id': 6, 'stored': '1f'}, {'id': 7, 'stored': '31'}]}]
# A row whose target is the spelling a held row keeps is held too, down a chain
BLOCKED = [
    ((21, 'ca-x', '10', _certificate(0x10)), '10'),
    ((22, 'ca-x', '0x10', None), '0x10'),
    ((23, 'ca-x', 'a', None), 'a'),  # '10' is row 21's spelling
    ((31, 'ca-y', '34', _certificate(0x34)), '34'),
    ((32, 'ca-y', '0x34', None), '0x34'),
    ((33, 'ca-y', '22', _certificate(0x22)), '22'),  # '34' is row 31's spelling
    ((34, 'ca-y', '0x16', None), '0x16'),  # '22' is row 33's spelling
    ((35, 'ca-y', 'ff', None), '255'),
]
BLOCKED_PENDING = [
    {'caref': 'ca-x', 'serial_number': '16', 'count': 2,
     'rows': [{'id': 21, 'stored': '10'}, {'id': 22, 'stored': '0x10'}]},
    {'caref': 'ca-x', 'serial_number': 'a', 'count': 1, 'waits_for': '10',
     'rows': [{'id': 23, 'stored': 'a'}, {'id': 21, 'stored': '10'}]},
    {'caref': 'ca-y', 'serial_number': '0x16', 'count': 1, 'waits_for': '22',
     'rows': [{'id': 34, 'stored': '0x16'}, {'id': 33, 'stored': '22'}]},
    {'caref': 'ca-y', 'serial_number': '22', 'count': 1, 'waits_for': '34',
     'rows': [{'id': 33, 'stored': '22'}, {'id': 31, 'stored': '34'}]},
    {'caref': 'ca-y', 'serial_number': '52', 'count': 2,
     'rows': [{'id': 31, 'stored': '34'}, {'id': 32, 'stored': '0x34'}]},
]
# Once one row of each shared serial is deleted, the held chain converts
BLOCKED_RESOLVED = {21: '16', 23: '10', 31: '52', 33: '34', 34: '22', 35: '255'}


def _rows(cases):
    return [row for row, _ in cases]


def _expected(cases):
    return {row[0]: after for row, after in cases}


def _pending(rows):
    return [json.loads(value) for (key, value) in rows if key == _migration().PENDING_KEY]


def _sqlite(certs, revoked=(), index=True):
    conn = sqlite3.connect(':memory:')
    for ddl in _DDL if index else _DDL[:-1]:
        conn.execute(ddl)
    conn.executemany(f"INSERT INTO {CERTS} VALUES (?, ?, ?, ?)", certs)
    conn.executemany(f"INSERT INTO {REVOKED} VALUES (?, ?, ?, ?)", revoked)
    conn.commit()
    return conn


def _stored(conn, table):
    return dict(conn.execute(f"SELECT id, serial_number FROM {table}").fetchall())


def test_sqlite_converts_mixed_spellings_once():
    conn = _sqlite(_rows(MIXED), _rows(REVOCATIONS[:3]))
    for _ in range(2):
        _migration().upgrade(conn)
        assert _stored(conn, CERTS) == _expected(MIXED)
        assert _stored(conn, REVOKED) == _expected(REVOCATIONS[:3])
    assert _pending(conn.execute(f"SELECT key, value FROM {CONFIG}")) == []
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(f"INSERT INTO {CERTS} VALUES (99, 'ca-a', '171', NULL)")


def test_sqlite_a_collision_is_listed_and_left_as_stored_until_resolved():
    conn = _sqlite(_rows(MIXED + COLLIDING), _rows(REVOCATIONS))
    for _ in range(2):
        _migration().upgrade(conn)
        assert _stored(conn, CERTS) == _expected(MIXED + COLLIDING)
        assert _stored(conn, REVOKED) == _expected(REVOCATIONS)
        assert _pending(conn.execute(f"SELECT key, value FROM {CONFIG}")) == [{'duplicates': PENDING}]
    assert conn.execute(f"SELECT COUNT(*) FROM {CERTS}").fetchone() == (len(MIXED + COLLIDING),)
    conn.execute(f"DELETE FROM {CERTS} WHERE id = 7")  # the procedure: one row kept
    _migration().upgrade(conn)
    assert _stored(conn, CERTS)[6] == '31'
    assert _pending(conn.execute(f"SELECT key, value FROM {CONFIG}")) == []


def test_sqlite_a_target_taken_by_a_held_row_holds_that_row_too():
    conn = _sqlite(_rows(BLOCKED))
    for _ in range(2):
        _migration().upgrade(conn)
        assert _stored(conn, CERTS) == _expected(BLOCKED)
        assert _pending(conn.execute(f"SELECT key, value FROM {CONFIG}")) == [{'duplicates': BLOCKED_PENDING}]
    conn.execute(f"DELETE FROM {CERTS} WHERE id IN (22, 32)")
    _migration().upgrade(conn)
    assert _stored(conn, CERTS) == BLOCKED_RESOLVED
    assert _pending(conn.execute(f"SELECT key, value FROM {CONFIG}")) == []


def test_sqlite_creates_the_index_142_could_not_once_the_duplicates_are_gone():
    conn = _sqlite([(1, 'ca-a', '11', None), (2, 'ca-a', '11', None), (3, 'ca-a', 'b', None)], index=False)
    _migration().upgrade(conn)
    assert _pending(conn.execute(f"SELECT key, value FROM {CONFIG}")) == [
        {'duplicates': [{'caref': 'ca-a', 'serial_number': '11', 'count': 3,
                         'rows': [{'id': 1, 'stored': '11'}, {'id': 2, 'stored': '11'}, {'id': 3, 'stored': 'b'}]}]}]
    assert _stored(conn, CERTS) == {1: '11', 2: '11', 3: 'b'}
    conn.execute(f"DELETE FROM {CERTS} WHERE id IN (2, 3)")
    _migration().upgrade(conn)
    assert conn.execute("SELECT name FROM sqlite_master WHERE name = ?", (INDEX,)).fetchone()


def test_sqlite_without_tables_does_nothing():
    _migration().upgrade(sqlite3.connect(':memory:'))


@pytest.mark.postgres
@pytest.mark.skipif(not PG_URL, reason='UCM_TEST_PG_URL not set')
@pytest.mark.parametrize('certs, revoked, pending', [
    (MIXED, REVOCATIONS[:3], []), (MIXED + COLLIDING, REVOCATIONS, PENDING), (BLOCKED, [], BLOCKED_PENDING)])
def test_postgresql(certs, revoked, pending):
    schema = f"m144_{os.getenv('PYTEST_XDIST_WORKER', 'main')}_{uuid.uuid4().hex[:6]}"
    admin = create_engine(PG_URL)
    with admin.begin() as conn:
        conn.execute(text(f'CREATE SCHEMA {schema}'))
    engine = create_engine(PG_URL, connect_args={'options': f'-csearch_path={schema}'})
    try:
        with engine.begin() as conn:
            for ddl in _DDL:
                conn.execute(text(ddl.replace('INTEGER PRIMARY KEY', 'SERIAL PRIMARY KEY')))
            for row in _rows(certs):
                conn.execute(text(f"INSERT INTO {CERTS} VALUES (:i, :c, :s, :p)"), dict(zip('icsp', row)))
            for row in _rows(revoked):
                conn.execute(text(f"INSERT INTO {REVOKED} VALUES (:i, :c, :s, :p)"), dict(zip('icsp', row)))
        for _ in range(2):
            with engine.begin() as conn:
                _migration().upgrade(conn)
            with engine.begin() as conn:
                assert dict(conn.execute(text(f"SELECT id, serial_number FROM {CERTS}")).fetchall()) == \
                    _expected(certs)
                assert dict(conn.execute(text(f"SELECT id, serial_number FROM {REVOKED}")).fetchall()) == \
                    _expected(revoked)
                listed = _pending(conn.execute(text(f"SELECT key, value FROM {CONFIG}")))
                assert listed == ([{'duplicates': pending}] if pending else [])
        with engine.begin() as conn:
            if not pending:
                with pytest.raises(Exception):
                    conn.execute(text(f"INSERT INTO {CERTS} VALUES (99, 'ca-a', '171', NULL)"))
        if certs is BLOCKED:
            with engine.begin() as conn:
                conn.execute(text(f"DELETE FROM {CERTS} WHERE id IN (22, 32)"))
                _migration().upgrade(conn)
            with engine.begin() as conn:
                assert dict(conn.execute(text(f"SELECT id, serial_number FROM {CERTS}")).fetchall()) == \
                    BLOCKED_RESOLVED
    finally:
        engine.dispose()
        with admin.begin() as conn:
            conn.execute(text(f'DROP SCHEMA IF EXISTS {schema} CASCADE'))
        admin.dispose()
