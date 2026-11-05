"""Migration 129 creates compromised_keys and fills it from the revocation records, idempotently,
on SQLite and PostgreSQL."""
import importlib
import os
import sqlite3

import pytest
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.exc import IntegrityError

from models.compromised_key import CompromisedKeyRecord
from models.revoked_serial import RevokedSerial

PG_URL = os.getenv('UCM_TEST_PG_URL')
KEYS, SERIALS = CompromisedKeyRecord.__tablename__, RevokedSerial.__tablename__
INDEX = f'ix_{KEYS}_public_key_sha256'
COLUMNS = {c.name for c in CompromisedKeyRecord.__table__.columns}
# (serial, reason, digest, revoked_at): two serials of one key, spellings, no digest, another reason
RECORDS = [('1', 'keyCompromise', 'a' * 64, '2026-01-02 00:00:00'),
           ('2', 'key_compromise', 'a' * 64, '2026-01-01 00:00:00'),
           ('3', 'KeyCompromise', 'b' * 64, '2026-02-01 00:00:00'),
           ('4', 'keyCompromise', None, '2026-03-01 00:00:00'),
           ('5', 'superseded', 'c' * 64, '2026-04-01 00:00:00')]
FILLED = [('a' * 64, 'local'), ('b' * 64, 'local')]


def _migration():
    return importlib.import_module('migrations.129_compromised_keys')


def _pre_129(execute, pk):
    execute(f"CREATE TABLE {SERIALS} (id {pk}, serial_number VARCHAR(100), revoke_reason VARCHAR(100),"
            f" revoked_at TIMESTAMP, public_key_sha256 VARCHAR(64))")
    for serial, reason, digest, at in RECORDS:
        digest = f"'{digest}'" if digest else 'NULL'
        execute(f"INSERT INTO {SERIALS} (serial_number, revoke_reason, public_key_sha256, revoked_at)"
                f" VALUES ('{serial}', '{reason}', {digest}, '{at}')")


def test_sqlite_creates_and_fills_the_table_once():
    conn = sqlite3.connect(':memory:')
    _pre_129(conn.execute, 'INTEGER PRIMARY KEY')
    _migration().upgrade(conn)
    _migration().upgrade(conn)
    assert {row[1] for row in conn.execute(f"PRAGMA table_info({KEYS})")} == COLUMNS
    assert conn.execute(f"SELECT public_key_sha256, source FROM {KEYS} ORDER BY 1").fetchall() == FILLED
    assert conn.execute(f"SELECT revoked_at FROM {KEYS} WHERE public_key_sha256 = ?",
                        ('a' * 64,)).fetchone()[0].startswith('2026-01-01')
    unique = {row[1]: row[2] for row in conn.execute(f"PRAGMA index_list({KEYS})")}
    assert unique[INDEX] == 1
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(f"INSERT INTO {KEYS} (public_key_sha256, revoked_at, source)"
                     f" VALUES ('{'a' * 64}', '2026-01-01', 'local')")


def test_sqlite_without_revocation_records_only_creates_the_table():
    conn = sqlite3.connect(':memory:')
    _migration().upgrade(conn)
    _migration().upgrade(conn)
    assert conn.execute(f"SELECT COUNT(*) FROM {KEYS}").fetchone() == (0,)


@pytest.mark.postgres
@pytest.mark.skipif(not PG_URL, reason='UCM_TEST_PG_URL not set')
@pytest.mark.parametrize('with_records', [True, False])
def test_postgres_creates_and_fills_the_table_once(with_records):
    schema = f"migtest_129{'' if with_records else 'e'}_{os.getenv('PYTEST_XDIST_WORKER', 'main')}"
    engine = create_engine(PG_URL)
    conn = engine.connect()
    try:
        conn.execute(text(f"DROP SCHEMA IF EXISTS {schema} CASCADE"))
        conn.execute(text(f"CREATE SCHEMA {schema}"))
        conn.execute(text(f"SET search_path TO {schema}"))
        if with_records:
            _pre_129(lambda sql: conn.execute(text(sql)), 'SERIAL PRIMARY KEY')
        _migration().upgrade(conn)
        _migration().upgrade(conn)
        inspector = inspect(conn)
        assert {c['name'] for c in inspector.get_columns(KEYS, schema=schema)} == COLUMNS
        assert any(i['name'] == INDEX and i['unique'] for i in inspector.get_indexes(KEYS, schema=schema))
        filled = conn.execute(text(f"SELECT public_key_sha256, source FROM {KEYS} ORDER BY 1")).fetchall()
        assert [tuple(r) for r in filled] == (FILLED if with_records else [])
        if with_records:
            assert str(conn.execute(text(f"SELECT revoked_at FROM {KEYS} WHERE public_key_sha256 = :d"),
                                    {'d': 'a' * 64}).scalar()).startswith('2026-01-01')
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
