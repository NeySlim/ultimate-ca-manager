"""Upgrade step 176: whether a revocation record was published (issue #450).

A nullable BOOLEAN column on revoked_serials: NULL for the records written before it (unknown),
set at every write since. A second run keeps the values written since. Idempotent, dual-backend.
"""
import logging
import sqlite3

logger = logging.getLogger(__name__)
pg_compatible = True

RECORDS = 'revoked_serials'
COLUMN = 'published'
DDL = f"ALTER TABLE {RECORDS} ADD COLUMN {COLUMN} BOOLEAN"


def upgrade(conn):
    if isinstance(conn, sqlite3.Connection):
        columns = {row[1] for row in conn.execute(f"PRAGMA table_info({RECORDS})")}
        if columns and COLUMN not in columns:
            conn.execute(DDL)
            conn.commit()
            logger.info("[176] revoked_serials.published added (SQLite)")
        return
    from sqlalchemy import inspect, text
    inspector = inspect(conn)
    if RECORDS not in inspector.get_table_names():
        return
    if COLUMN not in {c['name'] for c in inspector.get_columns(RECORDS)}:
        conn.execute(text(DDL))
        logger.info("[176] revoked_serials.published added (PostgreSQL)")


def downgrade(conn):
    """No downgrade: 2.254 ignores the column."""
    pass
