"""Migration 134 removes CRL rows sharing a number, makes the pair unique, seeds the counters."""
import base64
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

from models import CA
from models.crl import CRLMetadata, CRLNumberCounter
from utils.crl_issuer import crl_issuer_key

PG_URL = os.getenv('UCM_TEST_PG_URL')
CAS = CA.__tablename__
CRLS = CRLMetadata.__tablename__
COUNTERS = CRLNumberCounter.__tablename__


def _migration():
    return importlib.import_module('migrations.134_crl_number_unique_and_counters')


def _cert(name, key=None):
    key = key or ec.generate_private_key(ec.SECP256R1())
    subject = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, name)])
    now = datetime.now(timezone.utc)
    return key, (x509.CertificateBuilder().subject_name(subject).issuer_name(subject)
                 .public_key(key.public_key()).serial_number(x509.random_serial_number())
                 .not_valid_before(now - timedelta(days=1)).not_valid_after(now + timedelta(days=30))
                 .sign(key, hashes.SHA256()))


def _stored(cert):
    return base64.b64encode(cert.public_bytes(serialization.Encoding.PEM)).decode()


def _scenario():
    """CA 1 and its cross record 2 share an issuer; CA 3 is another one. CA 1 holds a duplicate."""
    key, cert = _cert('Migration 134 Root')
    _, cross = _cert('Migration 134 Root', key)
    _, other = _cert('Migration 134 Other')
    cas = [(1, _stored(cert)), (2, _stored(cross)), (3, _stored(other))]
    # (id, ca_id, crl_number): 11 and 12 share CA 1's number 5, 12 is the most recent
    crls = [(10, 1, 4), (11, 1, 5), (12, 1, 5), (20, 2, 9), (30, 3, 2)]
    expected = {crl_issuer_key(cert): 9, crl_issuer_key(other): 2}
    return cas, crls, expected


_CA_DDL = f"CREATE TABLE {CAS} (id INTEGER PRIMARY KEY, crt TEXT)"
_CRL_DDL = f"CREATE TABLE {CRLS} (id INTEGER PRIMARY KEY, ca_id INTEGER NOT NULL, crl_number INTEGER NOT NULL)"


def test_sqlite_dedupes_enforces_and_seeds():
    cas, crls, expected = _scenario()
    conn = sqlite3.connect(':memory:')
    conn.execute(_CA_DDL)
    conn.execute(_CRL_DDL)
    conn.executemany(f"INSERT INTO {CAS} VALUES (?, ?)", cas)
    conn.executemany(f"INSERT INTO {CRLS} VALUES (?, ?, ?)", crls)
    conn.commit()
    _migration().upgrade(conn)
    _migration().upgrade(conn)
    assert sorted(r[0] for r in conn.execute(f"SELECT id FROM {CRLS}")) == [10, 12, 20, 30]
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(f"INSERT INTO {CRLS} VALUES (99, 1, 4)")
    assert dict(conn.execute(f"SELECT issuer_key, last_number FROM {COUNTERS}")) == expected


def test_sqlite_never_lowers_a_counter():
    cas, crls, expected = _scenario()
    conn = sqlite3.connect(':memory:')
    conn.execute(_CA_DDL)
    conn.execute(_CRL_DDL)
    conn.executemany(f"INSERT INTO {CAS} VALUES (?, ?)", cas)
    conn.executemany(f"INSERT INTO {CRLS} VALUES (?, ?, ?)", crls)
    _migration().upgrade(conn)
    key = next(iter(expected))
    conn.execute(f"UPDATE {COUNTERS} SET last_number = 50 WHERE issuer_key = ?", (key,))
    conn.commit()
    _migration().upgrade(conn)
    assert dict(conn.execute(f"SELECT issuer_key, last_number FROM {COUNTERS}"))[key] == 50


def test_sqlite_without_the_tables_creates_the_counters():
    conn = sqlite3.connect(':memory:')
    _migration().upgrade(conn)
    assert conn.execute(f"SELECT COUNT(*) FROM {COUNTERS}").fetchone() == (0,)


def test_a_fresh_schema_declares_what_the_migration_builds():
    """create_all and the migration agree on the indexes."""
    engine = create_engine('sqlite://')
    for model in (CA, CRLMetadata, CRLNumberCounter):
        model.__table__.create(engine)
    with engine.connect() as conn:
        crl_indexes = {r[1]: r[2] for r in conn.execute(text(f"PRAGMA index_list({CRLS})"))}
        counter_indexes = {r[1]: r[2] for r in conn.execute(text(f"PRAGMA index_list({COUNTERS})"))}
    assert crl_indexes.get('uix_crl_ca_number') == 1
    assert counter_indexes.get('ix_crl_number_counters_issuer_key') == 1


def test_the_baseline_declares_the_unique_index():
    baseline = importlib.import_module('migrations.000_baseline_v252')
    conn = sqlite3.connect(':memory:')
    conn.executescript(baseline.SCHEMA_SQL)
    indexes = {r[1]: r[2] for r in conn.execute(f"PRAGMA index_list({CRLS})")}
    assert indexes.get('uix_crl_ca_number') == 1


@pytest.mark.postgres
@pytest.mark.skipif(not PG_URL, reason='UCM_TEST_PG_URL not set')
def test_postgres_dedupes_enforces_and_seeds():
    cas, crls, expected = _scenario()
    schema = f"migtest_134_{os.getenv('PYTEST_XDIST_WORKER', 'main')}"
    engine = create_engine(PG_URL)
    conn = engine.connect()
    try:
        conn.execute(text(f"DROP SCHEMA IF EXISTS {schema} CASCADE"))
        conn.execute(text(f"CREATE SCHEMA {schema}"))
        conn.execute(text(f"SET search_path TO {schema}"))
        conn.execute(text(_CA_DDL))
        conn.execute(text(_CRL_DDL))
        for row in cas:
            conn.execute(text(f"INSERT INTO {CAS} VALUES (:i, :c)"), {'i': row[0], 'c': row[1]})
        for row in crls:
            conn.execute(text(f"INSERT INTO {CRLS} VALUES (:i, :c, :n)"),
                         {'i': row[0], 'c': row[1], 'n': row[2]})
        _migration().upgrade(conn)
        _migration().upgrade(conn)
        assert sorted(r[0] for r in conn.execute(text(f"SELECT id FROM {CRLS}"))) == [10, 12, 20, 30]
        assert dict(conn.execute(text(f"SELECT issuer_key, last_number FROM {COUNTERS}")).fetchall()) \
            == expected
        savepoint = conn.begin_nested()
        with pytest.raises(IntegrityError):
            conn.execute(text(f"INSERT INTO {CRLS} VALUES (99, 1, 4)"))
        savepoint.rollback()
    finally:
        conn.rollback()
        conn.execute(text(f"DROP SCHEMA IF EXISTS {schema} CASCADE"))
        conn.commit()
        conn.close()
        engine.dispose()
