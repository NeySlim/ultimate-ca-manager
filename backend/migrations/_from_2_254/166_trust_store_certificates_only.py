"""Upgrade step 166: a trust store entry keeps its certificates only (RFC 5914 §2).

2.x stored the whole text of an imported file, a private key included. Each row keeps its
CERTIFICATE blocks; a row a key is removed from is logged by id, name and fingerprint, never the
key, and listed under ``truststore_private_keys_removed``, which the next start turns into audit
entries (utils/trust_pem.report_removed_keys). Running it again changes nothing.
"""
import json
import logging
import sqlite3

from utils.trust_pem import REMOVED_KEY, certificate_blocks, first_fingerprint, holds_private_key, removal_warning

logger = logging.getLogger(__name__)
pg_compatible = True

TABLE = 'trusted_certificates'
CONFIG = 'system_config'


def plan(rows):
    """``(updates, removed)`` for rows ``(id, name, certificate_pem)``.

    A row with no certificate block and no key is left as it is: nothing in it can be told apart."""
    updates, removed = [], []
    for row_id, name, text in rows:
        if not text:
            continue
        kept = certificate_blocks(text).decode('ascii')
        keyed = holds_private_key(text)
        if kept == text or not (kept or keyed):
            continue
        updates.append((row_id, kept))
        if keyed:
            removed.append({'id': row_id, 'name': name, 'fingerprint_sha256': first_fingerprint(kept)})
    return updates, removed


def _apply(run, tables):
    if TABLE not in tables:
        return
    updates, removed = plan(run(f"SELECT id, name, certificate_pem FROM {TABLE} ORDER BY id").fetchall())
    for row_id, kept in updates:
        run(f"UPDATE {TABLE} SET certificate_pem = :p WHERE id = :i", {'p': kept, 'i': row_id})
    if updates:
        logger.info("Upgrade step 166: %d trust store entries reduced to their certificates", len(updates))
    for entry in removed:
        logger.warning("Upgrade step 166: %s", removal_warning(entry['id'], entry['name'], entry['fingerprint_sha256']))
    if not removed or CONFIG not in tables:
        return
    held = run(f"SELECT value FROM {CONFIG} WHERE key = :k", {'k': REMOVED_KEY}).fetchone()
    try:
        listed = json.loads(held[0] or '[]') if held else []
    except ValueError:
        listed = []
    value = json.dumps(listed + removed)
    if held:
        run(f"UPDATE {CONFIG} SET value = :v WHERE key = :k", {'v': value, 'k': REMOVED_KEY})
    else:
        run(f"INSERT INTO {CONFIG} (key, value, description, updated_at) VALUES (:k, :v, "
            "'Trust store entries a private key was removed from by the upgrade', CURRENT_TIMESTAMP)",
            {'k': REMOVED_KEY, 'v': value})


def upgrade(conn):
    if isinstance(conn, sqlite3.Connection):
        tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
        _apply(lambda sql, params=None: conn.execute(sql, params or {}), tables)
        conn.commit()
        return
    from sqlalchemy import inspect, text
    _apply(lambda sql, params=None: conn.execute(text(sql), params or {}), set(inspect(conn).get_table_names()))


def downgrade(conn):
    """No downgrade: a removed key is not kept anywhere."""
