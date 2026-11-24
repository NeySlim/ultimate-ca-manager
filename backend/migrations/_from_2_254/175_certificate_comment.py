"""Upgrade step 175: the optional plain-text comment of a certificate (issue #454).

A nullable TEXT column; a second run keeps the comments written since. Idempotent, dual-backend.
"""
import logging
import sqlite3

logger = logging.getLogger(__name__)
pg_compatible = True

CERTS = 'certificates'
COLUMN = 'comment'
DDL = f"ALTER TABLE {CERTS} ADD COLUMN {COLUMN} TEXT"


def upgrade(conn):
    if isinstance(conn, sqlite3.Connection):
        columns = {row[1] for row in conn.execute(f"PRAGMA table_info({CERTS})")}
        if columns and COLUMN not in columns:
            conn.execute(DDL)
            conn.commit()
            logger.info("[175] certificates.comment added (SQLite)")
        return
    from sqlalchemy import inspect, text
    inspector = inspect(conn)
    if CERTS not in inspector.get_table_names():
        return
    if COLUMN not in {c['name'] for c in inspector.get_columns(CERTS)}:
        conn.execute(text(DDL))
        logger.info("[175] certificates.comment added (PostgreSQL)")


def downgrade(conn):
    """No downgrade: 2.254 ignores the column."""
    pass
