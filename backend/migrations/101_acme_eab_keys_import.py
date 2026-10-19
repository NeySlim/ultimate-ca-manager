"""Migration 101: move the legacy ``acme_eab_keys`` blob into ``acme_eab_credentials``.

Keys left in the blob by installs older than migration 027 still registered
accounts, but were invisible in the UI and could not be revoked. Each one
becomes an active credential (secret encrypted like any other), then the blob
is deleted. A kid already in the table is kept as it is. The kid column widens
to 255 so a long legacy kid imports too; an entry that is not a kid/key pair
of strings stays in the blob, which nothing reads any more.
"""
import json
import logging
import sqlite3

logger = logging.getLogger(__name__)
pg_compatible = True

LABEL = 'Imported legacy EAB key'


KID_LENGTH = 255


def _entries(raw):
    """``(importable pairs, leftover blob or None)``; the blob is left whole when unreadable."""
    try:
        blob = json.loads(raw or '{}')
    except (TypeError, ValueError):
        blob = None
    if not isinstance(blob, dict):
        logger.warning("[101] acme_eab_keys is not a JSON object; left in place")
        return [], raw
    entries, leftover = [], {}
    for kid, key in blob.items():
        if isinstance(kid, str) and isinstance(key, str) and kid and key and len(kid) <= KID_LENGTH:
            entries.append((kid, key))
        else:
            leftover[kid] = key
    if leftover:
        logger.warning("[101] %d legacy EAB entr(ies) not importable; left in acme_eab_keys", len(leftover))
    return entries, (json.dumps(leftover) if leftover else None)


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
    entries, leftover = _entries(row[0])
    for kid, key in entries:
        if conn.execute("SELECT 1 FROM acme_eab_credentials WHERE kid = ?", (kid,)).fetchone():
            continue
        conn.execute(
            "INSERT INTO acme_eab_credentials (kid, hmac_key_b64, label, status, created_at) "
            "VALUES (?, ?, ?, 'active', CURRENT_TIMESTAMP)",
            (kid, _encrypt(key), LABEL))
        imported += 1
    if leftover is None:
        conn.execute("DELETE FROM system_config WHERE key = 'acme_eab_keys'")
    else:
        conn.execute("UPDATE system_config SET value = ? WHERE key = 'acme_eab_keys'", (leftover,))
    conn.commit()
    logger.info("[101] imported %d legacy EAB key(s)", imported)


def _upgrade_pg(conn):
    from sqlalchemy import inspect, text

    tables = set(inspect(conn).get_table_names())
    if 'system_config' not in tables or 'acme_eab_credentials' not in tables:
        return
    conn.execute(text(f"ALTER TABLE acme_eab_credentials ALTER COLUMN kid TYPE VARCHAR({KID_LENGTH})"))
    row = conn.execute(text("SELECT value FROM system_config WHERE key = 'acme_eab_keys'")).fetchone()
    if row is None:
        return
    imported = 0
    entries, leftover = _entries(row[0])
    for kid, key in entries:
        if conn.execute(text("SELECT 1 FROM acme_eab_credentials WHERE kid = :kid"), {'kid': kid}).fetchone():
            continue
        conn.execute(text(
            "INSERT INTO acme_eab_credentials (kid, hmac_key_b64, label, status, created_at) "
            "VALUES (:kid, :key, :label, 'active', CURRENT_TIMESTAMP)"),
            {'kid': kid, 'key': _encrypt(key), 'label': LABEL})
        imported += 1
    if leftover is None:
        conn.execute(text("DELETE FROM system_config WHERE key = 'acme_eab_keys'"))
    else:
        conn.execute(text("UPDATE system_config SET value = :v WHERE key = 'acme_eab_keys'"),
                     {'v': leftover})
    logger.info("[101] imported %d legacy EAB key(s)", imported)


def upgrade(conn):
    if isinstance(conn, sqlite3.Connection):
        _upgrade_sqlite(conn)
    else:
        _upgrade_pg(conn)


def downgrade(conn):
    # The credentials stay in the table, which older versions read first.
    pass
