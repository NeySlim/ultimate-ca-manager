"""Migration 061: encrypt external ACME EAB HMAC keys at rest.

Existing ``acme_client_accounts.eab_hmac_key`` values and legacy SystemConfig
EAB values were historically stored as plaintext. New writes are encrypted by
the model/API; this migration rewrites legacy rows.

Idempotent and dual-backend (SQLite + PostgreSQL).
"""
import logging
import sqlite3

logger = logging.getLogger(__name__)
pg_compatible = True

_ACCOUNT_SELECT_SQL = (
    "SELECT id, eab_hmac_key FROM acme_client_accounts "
    "WHERE eab_hmac_key IS NOT NULL AND eab_hmac_key <> ''"
)
_CONFIG_SELECT_SQL = (
    "SELECT key, value FROM system_config "
    "WHERE key IN ('acme.client.eab_hmac_key', 'acme.proxy.eab_hmac_key') "
    "AND value IS NOT NULL AND value <> ''"
)


def _encryption_helpers():
    try:
        from security.encryption import encrypt_text, key_encryption
        return encrypt_text, key_encryption
    except Exception as exc:  # pragma: no cover - defensive boot fallback
        logger.warning("[061] cannot import encryption helpers: %s", exc)
        return None, None


def _encrypt_value(value, encrypt_text, key_encryption):
    if not value or key_encryption.is_string_encrypted(value):
        return value
    return encrypt_text(value)


def _upgrade_sqlite(conn):
    encrypt_text, key_encryption = _encryption_helpers()
    if encrypt_text is None or not getattr(key_encryption, 'is_enabled', False):
        logger.info("[061] encryption disabled; leaving EAB keys unchanged")
        return

    tables = {
        row[0] for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
    }
    rewritten = 0

    if 'acme_client_accounts' in tables:
        for account_id, value in conn.execute(_ACCOUNT_SELECT_SQL).fetchall():
            encrypted = _encrypt_value(value, encrypt_text, key_encryption)
            if encrypted != value:
                conn.execute(
                    "UPDATE acme_client_accounts "
                    "SET eab_hmac_key = ? WHERE id = ?",
                    (encrypted, account_id),
                )
                rewritten += 1

    if 'system_config' in tables:
        for key, value in conn.execute(_CONFIG_SELECT_SQL).fetchall():
            encrypted = _encrypt_value(value, encrypt_text, key_encryption)
            if encrypted != value:
                conn.execute(
                    "UPDATE system_config SET value = ? WHERE key = ?",
                    (encrypted, key),
                )
                rewritten += 1

    conn.commit()
    logger.info("[061] encrypted %d ACME EAB secret(s) (SQLite)", rewritten)


def _upgrade_pg(conn):
    from sqlalchemy import inspect, text

    encrypt_text, key_encryption = _encryption_helpers()
    if encrypt_text is None or not getattr(key_encryption, 'is_enabled', False):
        logger.info("[061] encryption disabled; leaving EAB keys unchanged")
        return

    tables = set(inspect(conn).get_table_names())
    rewritten = 0

    if 'acme_client_accounts' in tables:
        for account_id, value in conn.execute(text(_ACCOUNT_SELECT_SQL)).fetchall():
            encrypted = _encrypt_value(value, encrypt_text, key_encryption)
            if encrypted != value:
                conn.execute(
                    text(
                        "UPDATE acme_client_accounts "
                        "SET eab_hmac_key = :value WHERE id = :id"
                    ),
                    {'value': encrypted, 'id': account_id},
                )
                rewritten += 1

    if 'system_config' in tables:
        for key, value in conn.execute(text(_CONFIG_SELECT_SQL)).fetchall():
            encrypted = _encrypt_value(value, encrypt_text, key_encryption)
            if encrypted != value:
                conn.execute(
                    text("UPDATE system_config SET value = :value WHERE key = :key"),
                    {'value': encrypted, 'key': key},
                )
                rewritten += 1

    logger.info("[061] encrypted %d ACME EAB secret(s) (PostgreSQL)", rewritten)


def upgrade(conn):
    if isinstance(conn, sqlite3.Connection):
        _upgrade_sqlite(conn)
    else:
        _upgrade_pg(conn)


def _decrypt_sqlite(conn, decrypt_text):
    tables = {
        row[0] for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
    }
    if 'acme_client_accounts' in tables:
        for account_id, value in conn.execute(_ACCOUNT_SELECT_SQL).fetchall():
            plaintext = decrypt_text(value)
            if plaintext != value:
                conn.execute(
                    "UPDATE acme_client_accounts "
                    "SET eab_hmac_key = ? WHERE id = ?",
                    (plaintext, account_id),
                )
    if 'system_config' in tables:
        for key, value in conn.execute(_CONFIG_SELECT_SQL).fetchall():
            plaintext = decrypt_text(value)
            if plaintext != value:
                conn.execute(
                    "UPDATE system_config SET value = ? WHERE key = ?",
                    (plaintext, key),
                )
    conn.commit()


def _decrypt_pg(conn, decrypt_text):
    from sqlalchemy import inspect, text

    tables = set(inspect(conn).get_table_names())
    if 'acme_client_accounts' in tables:
        for account_id, value in conn.execute(text(_ACCOUNT_SELECT_SQL)).fetchall():
            plaintext = decrypt_text(value)
            if plaintext != value:
                conn.execute(
                    text(
                        "UPDATE acme_client_accounts "
                        "SET eab_hmac_key = :value WHERE id = :id"
                    ),
                    {'value': plaintext, 'id': account_id},
                )
    if 'system_config' in tables:
        for key, value in conn.execute(text(_CONFIG_SELECT_SQL)).fetchall():
            plaintext = decrypt_text(value)
            if plaintext != value:
                conn.execute(
                    text("UPDATE system_config SET value = :value WHERE key = :key"),
                    {'value': plaintext, 'key': key},
                )


def downgrade(conn):
    """Best effort: restore plaintext for compatibility with older releases."""
    try:
        from security.encryption import decrypt_text, key_encryption
    except Exception:  # pragma: no cover
        return
    if not getattr(key_encryption, 'is_enabled', False):
        return

    if isinstance(conn, sqlite3.Connection):
        _decrypt_sqlite(conn, decrypt_text)
    else:
        _decrypt_pg(conn, decrypt_text)
