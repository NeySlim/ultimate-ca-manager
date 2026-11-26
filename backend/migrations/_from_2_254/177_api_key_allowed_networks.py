"""Upgrade step 177: the source networks an API key is limited to (issue #403).

A nullable TEXT column on api_keys holding a JSON list of canonical networks; NULL, as for every
key written before it, admits any address. Idempotent, dual-backend.
"""
import logging
import sqlite3

logger = logging.getLogger(__name__)
pg_compatible = True

KEYS = 'api_keys'
COLUMN = 'allowed_networks'
DDL = f"ALTER TABLE {KEYS} ADD COLUMN {COLUMN} TEXT"


def upgrade(conn):
    if isinstance(conn, sqlite3.Connection):
        columns = {row[1] for row in conn.execute(f"PRAGMA table_info({KEYS})")}
        if columns and COLUMN not in columns:
            conn.execute(DDL)
            conn.commit()
            logger.info("[177] api_keys.allowed_networks added (SQLite)")
        return
    from sqlalchemy import inspect, text
    inspector = inspect(conn)
    if KEYS not in inspector.get_table_names():
        return
    if COLUMN not in {c['name'] for c in inspector.get_columns(KEYS)}:
        conn.execute(text(DDL))
        logger.info("[177] api_keys.allowed_networks added (PostgreSQL)")


def downgrade(conn):
    """No downgrade: 2.254 and 3.0 ignore the column."""
    pass
