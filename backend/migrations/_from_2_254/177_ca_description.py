"""Upgrade step 177: the optional free-text description of a CA (issue #459).

A nullable TEXT column beside the display name (descr); a second run keeps the descriptions
written since. Idempotent, dual-backend.
"""
import logging
import sqlite3

logger = logging.getLogger(__name__)
pg_compatible = True

CAS = 'certificate_authorities'
COLUMN = 'description'
DDL = f"ALTER TABLE {CAS} ADD COLUMN {COLUMN} TEXT"


def upgrade(conn):
    if isinstance(conn, sqlite3.Connection):
        columns = {row[1] for row in conn.execute(f"PRAGMA table_info({CAS})")}
        if columns and COLUMN not in columns:
            conn.execute(DDL)
            conn.commit()
            logger.info("[177] certificate_authorities.description added (SQLite)")
        return
    from sqlalchemy import inspect, text
    inspector = inspect(conn)
    if CAS not in inspector.get_table_names():
        return
    if COLUMN not in {c['name'] for c in inspector.get_columns(CAS)}:
        conn.execute(text(DDL))
        logger.info("[177] certificate_authorities.description added (PostgreSQL)")


def downgrade(conn):
    """No downgrade: 2.254 ignores the column."""
    pass
