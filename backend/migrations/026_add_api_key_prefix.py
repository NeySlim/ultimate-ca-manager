"""
Migration 026: Add ``key_prefix`` column to ``api_keys``

The original schema only stored the SHA-256 hash of the key, never the
plaintext or any prefix. The frontend tried to render ``{key.key_prefix}…``
on the API keys list, which always rendered as ``undefined…`` and the
"copy" button next to it copied the literal string ``undefined`` (#90).

This migration adds a nullable ``key_prefix`` column. New keys store the
first 12 characters of the plaintext (e.g. ``ucm_ak_AbC1``), which is
enough to identify a key without revealing it. Existing rows stay NULL —
the frontend handles the absence gracefully.

Multi-backend convention (v2.128+): runs on both SQLite and PostgreSQL.
"""
import logging
import sqlite3

logger = logging.getLogger(__name__)
pg_compatible = True

COLUMN_NAME = 'key_prefix'
SQLITE_TYPE = 'VARCHAR(20)'
PG_TYPE = 'VARCHAR(20)'


def _column_exists_sqlite(conn, table, column):
    cur = conn.execute(f"PRAGMA table_info({table})")
    return any(row[1] == column for row in cur.fetchall())


def _upgrade_sqlite(conn):
    cur = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='api_keys'"
    )
    if not cur.fetchone():
        logger.info("Migration 026: api_keys table absent, skipping")
        return

    if not _column_exists_sqlite(conn, 'api_keys', COLUMN_NAME):
        conn.execute(f"ALTER TABLE api_keys ADD COLUMN {COLUMN_NAME} {SQLITE_TYPE}")
        logger.info(f"Migration 026: added api_keys.{COLUMN_NAME}")

    conn.commit()


def _upgrade_pg(engine):
    from sqlalchemy import inspect, text

    insp = inspect(engine)
    if 'api_keys' not in set(insp.get_table_names()):
        logger.info("Migration 026: api_keys table absent, skipping")
        return

    cols = {c['name'] for c in insp.get_columns('api_keys')}
    with engine.begin() as conn:
        if COLUMN_NAME not in cols:
            conn.execute(text(
                f"ALTER TABLE api_keys ADD COLUMN {COLUMN_NAME} {PG_TYPE}"
            ))
            logger.info(f"Migration 026: added api_keys.{COLUMN_NAME}")


def upgrade(conn):
    if isinstance(conn, sqlite3.Connection):
        _upgrade_sqlite(conn)
    else:
        _upgrade_pg(conn)


def downgrade(conn):
    """SQLite cannot DROP COLUMN cleanly; left as no-op."""
    pass
