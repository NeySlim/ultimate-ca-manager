"""Upgrade step 181: key recovery requests name their requester and approver by account id.

Two nullable INTEGER columns on key_recovery_requests, naming users(id) ON DELETE SET NULL; NULL
for the requests written before it, which no name lookup fills in (a later account may hold the
name). Idempotent, dual-backend.
"""
import logging
import sqlite3

logger = logging.getLogger(__name__)
pg_compatible = True

REQUESTS = 'key_recovery_requests'
COLUMNS = ('requested_by_id', 'decided_by_id')
DEFINITION = 'INTEGER REFERENCES users(id) ON DELETE SET NULL'


def upgrade(conn):
    if isinstance(conn, sqlite3.Connection):
        present = {row[1] for row in conn.execute(f"PRAGMA table_info({REQUESTS})")}
        if not present:
            return
        for column in COLUMNS:
            if column not in present:
                conn.execute(f"ALTER TABLE {REQUESTS} ADD COLUMN {column} {DEFINITION}")
                logger.info(f"[181] {REQUESTS}.{column} added (SQLite)")
        conn.commit()
        return
    from sqlalchemy import inspect, text
    inspector = inspect(conn)
    if REQUESTS not in inspector.get_table_names():
        return
    present = {c['name'] for c in inspector.get_columns(REQUESTS)}
    for column in COLUMNS:
        if column not in present:
            conn.execute(text(f"ALTER TABLE {REQUESTS} ADD COLUMN {column} {DEFINITION}"))
            logger.info(f"[181] {REQUESTS}.{column} added (PostgreSQL)")


def downgrade(conn):
    """No downgrade: 2.254 and 3.0 ignore the columns."""
    pass
