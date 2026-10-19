"""Migration 101 moves the legacy EAB blob into the credential table.

The blob was read as a silent fallback: its keys registered accounts while
being invisible and irrevocable in the UI. After the import the fallback is
gone, so a key left in the blob no longer registers anything.
"""
import base64
import hashlib
import hmac
import importlib
import json
import os
import sqlite3

import pytest
from sqlalchemy import create_engine, text

from models import SystemConfig, db
from models.acme_models import AcmeEabCredential
from services.acme.acme_service import AcmeService
from utils.encryption import decrypt_if_needed

PG_URL = os.getenv('UCM_TEST_PG_URL')
BLOB = json.dumps({'legacy-kid': 'bGVnYWN5LXNlY3JldA', 'kept-kid': 'bmV3', '': 'x', 'bad': 3})

SQLITE_SCHEMA = (
    "CREATE TABLE system_config (key TEXT PRIMARY KEY, value TEXT)",
    "CREATE TABLE acme_eab_credentials (id INTEGER PRIMARY KEY AUTOINCREMENT, kid VARCHAR(64) NOT NULL UNIQUE,"
    " hmac_key_b64 TEXT NOT NULL, label VARCHAR(255), created_at DATETIME NOT NULL,"
    " status VARCHAR(20) NOT NULL DEFAULT 'active', allowed_domains TEXT)",
)
PG_SCHEMA = (
    "CREATE TABLE system_config (key VARCHAR(255) PRIMARY KEY, value TEXT)",
    "CREATE TABLE acme_eab_credentials (id SERIAL PRIMARY KEY, kid VARCHAR(64) NOT NULL UNIQUE,"
    " hmac_key_b64 TEXT NOT NULL, label VARCHAR(255), created_at TIMESTAMP NOT NULL,"
    " status VARCHAR(20) NOT NULL DEFAULT 'active', allowed_domains TEXT)",
)


def _migration():
    return importlib.import_module('migrations.101_acme_eab_keys_import')


def _check(rows, blob_left):
    by_kid = {r[0]: r for r in rows}
    assert set(by_kid) == {'legacy-kid', 'kept-kid'}
    # Encrypted at rest, and the secret survives the trip.
    assert by_kid['legacy-kid'][1] != 'bGVnYWN5LXNlY3JldA'
    assert decrypt_if_needed(by_kid['legacy-kid'][1]) == 'bGVnYWN5LXNlY3JldA'
    assert by_kid['legacy-kid'][2] == 'active'
    # An existing credential is not overwritten.
    assert by_kid['kept-kid'][1] == 'existing'
    assert blob_left is None


def test_sqlite_imports_then_drops_the_blob():
    conn = sqlite3.connect(':memory:')
    for statement in SQLITE_SCHEMA:
        conn.execute(statement)
    conn.execute("INSERT INTO system_config VALUES ('acme_eab_keys', ?)", (BLOB,))
    conn.execute("INSERT INTO acme_eab_credentials (kid, hmac_key_b64, created_at) "
                 "VALUES ('kept-kid', 'existing', CURRENT_TIMESTAMP)")
    _migration().upgrade(conn)
    _migration().upgrade(conn)
    rows = conn.execute("SELECT kid, hmac_key_b64, status FROM acme_eab_credentials").fetchall()
    blob = conn.execute("SELECT 1 FROM system_config WHERE key = 'acme_eab_keys'").fetchone()
    _check(rows, blob)


@pytest.mark.postgres
@pytest.mark.skipif(not PG_URL, reason='UCM_TEST_PG_URL not set')
def test_postgres_imports_then_drops_the_blob():
    schema = f"migtest_101_{os.getenv('PYTEST_XDIST_WORKER', 'main')}"
    engine = create_engine(PG_URL)
    conn = engine.connect()
    try:
        conn.execute(text(f"DROP SCHEMA IF EXISTS {schema} CASCADE"))
        conn.execute(text(f"CREATE SCHEMA {schema}"))
        conn.execute(text(f"SET search_path TO {schema}"))
        for statement in PG_SCHEMA:
            conn.execute(text(statement))
        conn.execute(text("INSERT INTO system_config VALUES ('acme_eab_keys', :v)"), {'v': BLOB})
        conn.execute(text("INSERT INTO acme_eab_credentials (kid, hmac_key_b64, created_at) "
                          "VALUES ('kept-kid', 'existing', CURRENT_TIMESTAMP)"))
        _migration().upgrade(conn)
        _migration().upgrade(conn)
        rows = conn.execute(text("SELECT kid, hmac_key_b64, status FROM acme_eab_credentials")).fetchall()
        blob = conn.execute(text("SELECT 1 FROM system_config WHERE key = 'acme_eab_keys'")).fetchone()
        _check(rows, blob)
    finally:
        conn.rollback()
        conn.execute(text(f"DROP SCHEMA IF EXISTS {schema} CASCADE"))
        conn.commit()
        conn.close()
        engine.dispose()


def _eab(jwk, kid, key, url):
    protected = base64.urlsafe_b64encode(json.dumps(
        {'alg': 'HS256', 'kid': kid, 'url': url}).encode()).rstrip(b'=').decode()
    payload = base64.urlsafe_b64encode(json.dumps(jwk).encode()).rstrip(b'=').decode()
    sig = base64.urlsafe_b64encode(hmac.new(key, f'{protected}.{payload}'.encode(),
                                            hashlib.sha256).digest()).rstrip(b'=').decode()
    return {'protected': protected, 'payload': payload, 'signature': sig}


def test_a_key_left_in_the_blob_no_longer_registers(app):
    jwk = {'kty': 'EC', 'crv': 'P-256', 'x': 'f83OJ3D2xF1Bg8vub9tLe1gHMzV76e8Tus9uPHvRVEU',
           'y': 'x_FEzRu9m36HLN_tue659LNpXW6pCyStikYjKIWI5a0'}
    key = b'blob-only-secret'
    kid = 'blob-only-kid'
    with app.app_context():
        row = SystemConfig.query.filter_by(key='acme_eab_keys').first()
        if row is None:
            row = SystemConfig(key='acme_eab_keys')
            db.session.add(row)
        row.value = json.dumps({kid: base64.urlsafe_b64encode(key).rstrip(b'=').decode()})
        db.session.commit()
        try:
            assert AcmeEabCredential.query.filter_by(kid=kid).first() is None
            url = 'http://localhost/acme/new-account'
            valid, error = AcmeService(base_url='http://localhost').validate_eab(
                _eab(jwk, kid, key, url), jwk, url)
            assert valid is False
            assert error == 'Unknown external account'
        finally:
            db.session.delete(row)
            db.session.commit()
