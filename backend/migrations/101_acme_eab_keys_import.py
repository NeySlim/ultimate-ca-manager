"""Migration 101: move the legacy ``acme_eab_keys`` blob into ``acme_eab_credentials``.

Keys left in the blob by installs older than migration 027 still registered
accounts, but were invisible in the UI and could not be revoked. Each one
becomes an active credential (secret encrypted like any other), then the blob
is deleted. A kid already in the table is kept as it is.
"""
import json
import logging
import sqlite3

logger = logging.getLogger(__name__)
pg_compatible = True

LABEL = 'Imported legacy EAB key'


def _entries(raw):
    try:
        blob = json.loads(raw or '{}')
    except (TypeError, ValueError):
        logger.warning("[101] acme_eab_keys is not JSON; dropped")
        return []
    if not isinstance(blob, dict):
        return []
    entries = []
    for kid, key in blob.items():
        if isinstance(kid, str) and isinstance(key, str) and kid and key and len(kid) <= 64:
            entries.append((kid, key))
        else:
            logger.warning("[101] unusable legacy EAB entry dropped")
    return entries


def _encrypt(value):
    from utils.encryption import encrypt_if_needed
    return encrypt_if_needed(value)


def _upgrade_sqlite(conn):
    tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    if 'system_config' not in tables or 'acme_eab_credentials' not in tables:
        return
    row = conn.execute("SELECT value FROM system_config WHERE key = 'acme_eab_keys'").fetchone()
    if row is None:
        return
    imported = 0
    for kid, key in _entries(row[0]):
        if conn.execute("SELECT 1 FROM acme_eab_credentials WHERE kid = ?", (kid,)).fetchone():
            continue
        conn.execute(
            "INSERT INTO acme_eab_credentials (kid, hmac_key_b64, label, status, created_at) "
            "VALUES (?, ?, ?, 'active', CURRENT_TIMESTAMP)",
            (kid, _encrypt(key), LABEL))
        imported += 1
    conn.execute("DELETE FROM system_config WHERE key = 'acme_eab_keys'")
    conn.commit()
    logger.info("[101] imported %d legacy EAB key(s)", imported)


def _upgrade_pg(conn):
    from sqlalchemy import inspect, text

    tables = set(inspect(conn).get_table_names())
    if 'system_config' not in tables or 'acme_eab_credentials' not in tables:
        return
    row = conn.execute(text("SELECT value FROM system_config WHERE key = 'acme_eab_keys'")).fetchone()
    if row is None:
        return
    imported = 0
    for kid, key in _entries(row[0]):
        if conn.execute(text("SELECT 1 FROM acme_eab_credentials WHERE kid = :kid"), {'kid': kid}).fetchone():
            continue
        conn.execute(text(
            "INSERT INTO acme_eab_credentials (kid, hmac_key_b64, label, status, created_at) "
            "VALUES (:kid, :key, :label, 'active', CURRENT_TIMESTAMP)"),
            {'kid': kid, 'key': _encrypt(key), 'label': LABEL})
        imported += 1
    conn.execute(text("DELETE FROM system_config WHERE key = 'acme_eab_keys'"))
    logger.info("[101] imported %d legacy EAB key(s)", imported)


def upgrade(conn):
    if isinstance(conn, sqlite3.Connection):
        _upgrade_sqlite(conn)
    else:
        _upgrade_pg(conn)


def downgrade(conn):
    # The credentials stay in the table, which older versions read first.
    pass
