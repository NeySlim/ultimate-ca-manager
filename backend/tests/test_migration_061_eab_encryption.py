"""Migration 061 — encrypt external ACME EAB HMAC keys at rest."""
import importlib
import sqlite3

import pytest
from cryptography.fernet import Fernet
from sqlalchemy import create_engine, text


@pytest.fixture
def encryption_enabled(monkeypatch):
    monkeypatch.setenv('KEY_ENCRYPTION_KEY', Fernet.generate_key().decode())
    from security import encryption
    encryption.key_encryption.reload()
    assert encryption.key_encryption.is_enabled
    yield encryption
    monkeypatch.delenv('KEY_ENCRYPTION_KEY', raising=False)
    encryption.key_encryption.reload()


def _migration():
    return importlib.import_module('migrations.061_encrypt_acme_client_eab_keys')


def test_migration_061_encrypts_sqlite_rows_idempotently(encryption_enabled):
    conn = sqlite3.connect(':memory:')
    conn.execute(
        'CREATE TABLE acme_client_accounts '
        '(id INTEGER PRIMARY KEY, eab_hmac_key TEXT)'
    )
    conn.execute(
        'INSERT INTO acme_client_accounts (id, eab_hmac_key) VALUES (?, ?)',
        (1, 'plaintext-eab-key'),
    )
    conn.execute(
        'CREATE TABLE system_config (key TEXT PRIMARY KEY, value TEXT)'
    )
    conn.execute(
        'INSERT INTO system_config (key, value) VALUES (?, ?)',
        ('acme.client.eab_hmac_key', 'plaintext-config-eab-key'),
    )
    conn.commit()

    migration = _migration()
    migration.upgrade(conn)
    encrypted = conn.execute(
        'SELECT eab_hmac_key FROM acme_client_accounts WHERE id = 1'
    ).fetchone()[0]
    assert encrypted != 'plaintext-eab-key'
    assert encryption_enabled.key_encryption.is_string_encrypted(encrypted)
    assert encryption_enabled.decrypt_text(encrypted) == 'plaintext-eab-key'
    encrypted_config = conn.execute(
        "SELECT value FROM system_config WHERE key = 'acme.client.eab_hmac_key'"
    ).fetchone()[0]
    assert encryption_enabled.key_encryption.is_string_encrypted(encrypted_config)
    assert encryption_enabled.decrypt_text(encrypted_config) == 'plaintext-config-eab-key'

    migration.upgrade(conn)
    assert conn.execute(
        'SELECT eab_hmac_key FROM acme_client_accounts WHERE id = 1'
    ).fetchone()[0] == encrypted
    assert conn.execute(
        "SELECT value FROM system_config WHERE key = 'acme.client.eab_hmac_key'"
    ).fetchone()[0] == encrypted_config


def test_migration_061_sqlalchemy_path_uses_supplied_connection(encryption_enabled):
    engine = create_engine('sqlite:///:memory:')
    migration = _migration()

    # A SQLAlchemy Connection exercises the PostgreSQL migration branch while
    # keeping the test hermetic. The SQL used is portable to PostgreSQL.
    with engine.begin() as conn:
        conn.execute(text(
            'CREATE TABLE acme_client_accounts '
            '(id INTEGER PRIMARY KEY, eab_hmac_key TEXT)'
        ))
        conn.execute(
            text(
                'INSERT INTO acme_client_accounts (id, eab_hmac_key) '
                'VALUES (:id, :value)'
            ),
            {'id': 1, 'value': 'plaintext-pg-eab-key'},
        )
        conn.execute(text(
            'CREATE TABLE system_config (key TEXT PRIMARY KEY, value TEXT)'
        ))
        conn.execute(
            text('INSERT INTO system_config (key, value) VALUES (:key, :value)'),
            {'key': 'acme.proxy.eab_hmac_key', 'value': 'plaintext-pg-config-key'},
        )
        migration._upgrade_pg(conn)
        encrypted = conn.execute(text(
            'SELECT eab_hmac_key FROM acme_client_accounts WHERE id = 1'
        )).scalar_one()
        encrypted_config = conn.execute(text(
            "SELECT value FROM system_config "
            "WHERE key = 'acme.proxy.eab_hmac_key'"
        )).scalar_one()

    assert encrypted != 'plaintext-pg-eab-key'
    assert encryption_enabled.key_encryption.is_string_encrypted(encrypted)
    assert encryption_enabled.decrypt_text(encrypted) == 'plaintext-pg-eab-key'
    assert encryption_enabled.key_encryption.is_string_encrypted(encrypted_config)
    assert encryption_enabled.decrypt_text(encrypted_config) == 'plaintext-pg-config-key'
