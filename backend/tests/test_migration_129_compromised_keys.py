"""Migration 129 creates compromised_keys and fills it from the certificates and the revocation
records that know a compromised key, idempotently, on SQLite and PostgreSQL."""
import base64
import importlib
import os
import sqlite3
from datetime import datetime, timedelta

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.exc import IntegrityError

from models import Certificate
from models.compromised_key import CompromisedKeyRecord
from models.revoked_serial import RevokedSerial
from utils.spki_digest import public_key_sha256

PG_URL = os.getenv('UCM_TEST_PG_URL')
KEYS, SERIALS, CERTS = (CompromisedKeyRecord.__tablename__, RevokedSerial.__tablename__,
                        Certificate.__tablename__)
INDEX = f'ix_{KEYS}_public_key_sha256'
COLUMNS = {c.name for c in CompromisedKeyRecord.__table__.columns}


def _certificate():
    key = ec.generate_private_key(ec.SECP256R1())
    name = x509.Name([x509.NameAttribute(x509.NameOID.COMMON_NAME, 'migration-129.example')])
    now = datetime(2026, 1, 1)
    cert = (x509.CertificateBuilder().subject_name(name).issuer_name(name).public_key(key.public_key())
            .serial_number(x509.random_serial_number()).not_valid_before(now)
            .not_valid_after(now + timedelta(days=90)).sign(key, hashes.SHA256()))
    return base64.b64encode(cert.public_bytes(serialization.Encoding.PEM)).decode(), \
        public_key_sha256(key.public_key())


(EXT, EXT_KEY), (ACME, ACME_KEY), (LOC, LOC_KEY), (SUP, _s), (LIVE, _l) = [_certificate() for _ in range(5)]
# (refid, caref, source, revoked, reason, crt, revoked_at)
CERT_ROWS = [('ext', None, 'manual', True, ' KeyCompromise ', EXT, None),
             ('acme', None, 'acme_client', True, 'keyCompromise', ACME, '2026-03-01 00:00:00'),
             ('loc', 'ca-1', 'manual', True, 'key_compromise', LOC, '2026-03-02 00:00:00'),
             ('sup', None, 'acme_client', True, 'superseded', SUP, '2026-03-03 00:00:00'),
             ('live', None, 'acme_client', False, 'keyCompromise', LIVE, None),
             ('bad', None, 'manual', True, 'keyCompromise', 'bm90IGEgY2VydGlmaWNhdGU=', None),
             ('none', None, 'manual', True, 'keyCompromise', None, None)]
# (serial, reason, digest, revoked_at): two serials of one key, a key a certificate already gave,
# no digest, another reason
RECORDS = [('1', 'keyCompromise', 'a' * 64, '2026-01-02 00:00:00'),
           ('2', 'key_compromise', 'a' * 64, '2026-01-01 00:00:00'),
           ('3', ' KeyCompromise', ACME_KEY, '2026-02-01 00:00:00'),
           ('4', 'keyCompromise', None, '2026-03-01 00:00:00'),
           ('5', 'superseded', 'c' * 64, '2026-04-01 00:00:00')]
FILLED = sorted([('a' * 64, 'local', None), (EXT_KEY, 'external', 'ext'),
                 (ACME_KEY, 'acme_client', 'acme'), (LOC_KEY, 'local', 'loc')])
SELECT = f"SELECT public_key_sha256, source, cert_refid FROM {KEYS} ORDER BY 1"


def _migration():
    return importlib.import_module('migrations.129_compromised_keys')


def _literal(value):
    return 'NULL' if value is None else f"'{value}'"


def _pre_129(execute, pk, boolean):
    execute(f"CREATE TABLE {SERIALS} (id {pk}, serial_number VARCHAR(100), revoke_reason VARCHAR(100),"
            f" revoked_at TIMESTAMP, public_key_sha256 VARCHAR(64))")
    for serial, reason, digest, at in RECORDS:
        execute(f"INSERT INTO {SERIALS} (serial_number, revoke_reason, public_key_sha256, revoked_at)"
                f" VALUES ('{serial}', '{reason}', {_literal(digest)}, '{at}')")
    execute(f"CREATE TABLE {CERTS} (id {pk}, refid VARCHAR(36), caref VARCHAR(36), source VARCHAR(20),"
            f" revoked {boolean}, revoke_reason VARCHAR(100), crt TEXT, revoked_at TIMESTAMP,"
            f" subject TEXT)")
    for refid, caref, source, revoked, reason, crt, at in CERT_ROWS:
        flag = ('TRUE' if revoked else 'FALSE') if boolean == 'BOOLEAN' else int(revoked)
        execute(f"INSERT INTO {CERTS} (refid, caref, source, revoked, revoke_reason, crt, revoked_at,"
                f" subject) VALUES ('{refid}', {_literal(caref)}, '{source}', {flag}, '{reason}',"
                f" {_literal(crt)}, {_literal(at)}, 'CN={refid}')")


def test_sqlite_creates_and_fills_the_table_once():
    conn = sqlite3.connect(':memory:')
    _pre_129(conn.execute, 'INTEGER PRIMARY KEY', 'INTEGER')
    _migration().upgrade(conn)
    _migration().upgrade(conn)
    assert {row[1] for row in conn.execute(f"PRAGMA table_info({KEYS})")} == COLUMNS
    assert conn.execute(SELECT).fetchall() == FILLED
    dates = dict(conn.execute(f"SELECT public_key_sha256, revoked_at FROM {KEYS}").fetchall())
    assert dates['a' * 64].startswith('2026-01-01') and dates[ACME_KEY].startswith('2026-03-01')
    assert dates[EXT_KEY]  # unknown revocation date: the time of the upgrade
    unique = {row[1]: row[2] for row in conn.execute(f"PRAGMA index_list({KEYS})")}
    assert unique[INDEX] == 1
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(f"INSERT INTO {KEYS} (public_key_sha256, revoked_at, source)"
                     f" VALUES ('{'a' * 64}', '2026-01-01', 'local')")


def test_sqlite_without_certificates_or_records_only_creates_the_table():
    conn = sqlite3.connect(':memory:')
    _migration().upgrade(conn)
    _migration().upgrade(conn)
    assert conn.execute(f"SELECT COUNT(*) FROM {KEYS}").fetchone() == (0,)


@pytest.mark.postgres
@pytest.mark.skipif(not PG_URL, reason='UCM_TEST_PG_URL not set')
@pytest.mark.parametrize('with_rows', [True, False])
def test_postgres_creates_and_fills_the_table_once(with_rows):
    schema = f"migtest_129{'' if with_rows else 'e'}_{os.getenv('PYTEST_XDIST_WORKER', 'main')}"
    engine = create_engine(PG_URL)
    conn = engine.connect()
    try:
        conn.execute(text(f"DROP SCHEMA IF EXISTS {schema} CASCADE"))
        conn.execute(text(f"CREATE SCHEMA {schema}"))
        conn.execute(text(f"SET search_path TO {schema}"))
        if with_rows:
            _pre_129(lambda sql: conn.execute(text(sql)), 'SERIAL PRIMARY KEY', 'BOOLEAN')
        _migration().upgrade(conn)
        _migration().upgrade(conn)
        inspector = inspect(conn)
        assert {c['name'] for c in inspector.get_columns(KEYS, schema=schema)} == COLUMNS
        assert any(i['name'] == INDEX and i['unique'] for i in inspector.get_indexes(KEYS, schema=schema))
        assert [tuple(r) for r in conn.execute(text(SELECT)).fetchall()] == (FILLED if with_rows else [])
        if with_rows:
            dates = dict(conn.execute(text(f"SELECT public_key_sha256, revoked_at FROM {KEYS}")).fetchall())
            assert str(dates['a' * 64]).startswith('2026-01-01')
            assert str(dates[ACME_KEY]).startswith('2026-03-01')
            # The time of the upgrade, in UTC like every naive timestamp of the schema
            now = conn.execute(text("SELECT CURRENT_TIMESTAMP AT TIME ZONE 'UTC'")).scalar()
            assert abs(now - dates[EXT_KEY]) < timedelta(minutes=5)
            with pytest.raises(IntegrityError):
                conn.execute(text(f"INSERT INTO {KEYS} (public_key_sha256, revoked_at, source)"
                                  f" VALUES ('{'a' * 64}', '2026-01-01', 'local')"))
    finally:
        conn.rollback()
        conn.execute(text(f"DROP SCHEMA IF EXISTS {schema} CASCADE"))
        conn.commit()
        conn.close()
        engine.dispose()


def test_the_model_matches_the_migration(app):
    from models import db
    with app.app_context():
        inspector = inspect(db.engine)
        assert {c['name'] for c in inspector.get_columns(KEYS)} == COLUMNS
        assert any(i['name'] == INDEX and i['unique'] for i in inspector.get_indexes(KEYS))
