"""Migration 029: encrypt ACME private keys stored in system_config.

Historically the ACME client account key (``acme.client.<env>.account_key``)
and the server-side ACME account key (``acme.account.<id>.private_key``)
were written as raw PEM into ``system_config.value``. They are now passed
through ``security.encryption.encrypt_text()`` on write.

This migration walks the existing rows once and rewrites any plain PEM
to the encrypted form. If encryption is disabled (no master.key, no
KEY_ENCRYPTION_KEY env var), ``encrypt_text`` is a no-op so this
migration is also a no-op — the rows just stay readable as before.

Idempotent: ``encrypt_text`` already detects the ENC: marker and
returns the input unchanged, so re-running this migration is safe.

Dual-backend (SQLite + PostgreSQL).
"""

import logging
import sqlite3

logger = logging.getLogger(__name__)
pg_compatible = True


_SELECT_SQL = (
    "SELECT key, value FROM system_config "
    "WHERE key LIKE 'acme.client.%.account_key' "
    "   OR key LIKE 'acme.account.%.private_key'"
)


def _upgrade_sqlite(conn):
    try:
        from security.encryption import encrypt_text, key_encryption
    except Exception as e:  # pragma: no cover
        logger.warning(f"029: cannot import security.encryption ({e}); skipping")
        return

    if not getattr(key_encryption, 'is_enabled', False):
        logger.info("029: encryption disabled, leaving ACME keys as-is")
        return

    cur = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='system_config'"
    )
    if not cur.fetchone():
        logger.info("029: system_config absent, skipping (fresh)")
        return

    rows = conn.execute(_SELECT_SQL).fetchall()
    rewritten = 0
    for row in rows:
        key = row[0]
        value = row[1]
        if not value:
            continue
        new_value = encrypt_text(value)
        if new_value != value:
            conn.execute(
                "UPDATE system_config SET value = ? WHERE key = ?",
                (new_value, key),
            )
            rewritten += 1
    conn.commit()
    if rewritten:
        logger.info(f"029: encrypted {rewritten} ACME private key(s) at rest (SQLite)")


def _upgrade_pg(conn):
    from sqlalchemy import inspect, text

    try:
        from security.encryption import encrypt_text, key_encryption
    except Exception as e:  # pragma: no cover
        logger.warning(f"029: cannot import security.encryption ({e}); skipping")
        return

    if not getattr(key_encryption, 'is_enabled', False):
        logger.info("029: encryption disabled, leaving ACME keys as-is")
        return

    insp = inspect(conn)
    if 'system_config' not in set(insp.get_table_names()):
        logger.info("029: system_config absent, skipping (fresh PG)")
        return

    rows = conn.execute(text(_SELECT_SQL)).fetchall()
    rewritten = 0
    for row in rows:
        key = row[0]
        value = row[1]
        if not value:
            continue
        new_value = encrypt_text(value)
        if new_value != value:
            conn.execute(
                text("UPDATE system_config SET value = :v WHERE key = :k"),
                {"v": new_value, "k": key},
            )
            rewritten += 1
    if rewritten:
        logger.info(f"029: encrypted {rewritten} ACME private key(s) at rest (PostgreSQL)")


def upgrade(conn):
    if isinstance(conn, sqlite3.Connection):
        _upgrade_sqlite(conn)
    else:
        _upgrade_pg(conn)


def downgrade(conn):
    """Best effort: decrypt back to plain PEM so old code can read them."""
    try:
        from security.encryption import decrypt_text, key_encryption
    except Exception:
        return
    if not getattr(key_encryption, 'is_enabled', False):
        return

    if isinstance(conn, sqlite3.Connection):
        rows = conn.execute(_SELECT_SQL).fetchall()
        for row in rows:
            key, value = row[0], row[1]
            if not value:
                continue
            try:
                plain = decrypt_text(value)
            except Exception:
                continue
            if plain != value:
                conn.execute(
                    "UPDATE system_config SET value = ? WHERE key = ?",
                    (plain, key),
                )
        conn.commit()
    else:
        from sqlalchemy import text
        rows = conn.execute(text(_SELECT_SQL)).fetchall()
        for row in rows:
            key, value = row[0], row[1]
            if not value:
                continue
            try:
                plain = decrypt_text(value)
            except Exception:
                continue
            if plain != value:
                conn.execute(
                    text("UPDATE system_config SET value = :v WHERE key = :k"),
                    {"v": plain, "k": key},
                )
