"""Upgrade step 153: data-encryption keys (DEK) wrapped by the key-encryption key (KEK).

One row per DEK version: state 'active' (encrypts; after a disable, decrypts only until
retire_after), 'previous' (decrypts only: rewritten
by a rotation, then kept through its retention) or 'disabled' (no key: encryption turned
off while a KEK stays configured).
retire_after: set once a DEK only decrypts (after a rotation or a disable), when it may be dropped.
No row: the KEK material is itself DEK version 1, as before the envelope.
"""
import logging
import sqlite3

logger = logging.getLogger(__name__)
pg_compatible = True

DDL = ("CREATE TABLE IF NOT EXISTS encryption_keys ("
       "version INTEGER NOT NULL PRIMARY KEY, state VARCHAR(16) NOT NULL, "
       "kek_id VARCHAR(16) NOT NULL, wrapped TEXT, created_at TIMESTAMP NOT NULL, "
       "retire_after TIMESTAMP)")


def upgrade(conn):
    if isinstance(conn, sqlite3.Connection):
        conn.execute(DDL)
        conn.commit()
        logger.info("[153] encryption_keys (SQLite)")
        return
    from sqlalchemy import text
    conn.execute(text(DDL))
    logger.info("[153] encryption_keys (PostgreSQL)")


def downgrade(conn):
    """No downgrade: dropping the table would lose every rotated key."""
    pass
