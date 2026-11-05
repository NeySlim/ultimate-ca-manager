"""Migration 120: index certificates.serial_number and caref.

Renewal, revocation and protocol lookups filter on them; without an index each
one scans the table. Multi-backend convention: runs on SQLite and PostgreSQL.
"""
import logging
import sqlite3

logger = logging.getLogger(__name__)
pg_compatible = True

_INDEXES = (
    "CREATE INDEX IF NOT EXISTS ix_certificates_serial_number ON certificates (serial_number)",
    "CREATE INDEX IF NOT EXISTS ix_certificates_caref ON certificates (caref)",
)


def upgrade(conn):
    if isinstance(conn, sqlite3.Connection):
        for stmt in _INDEXES:
            conn.execute(stmt)
        conn.commit()
    else:
        from sqlalchemy import text
        for stmt in _INDEXES:
            conn.execute(text(stmt))
    logger.info("Migration 120: ensured certificates lookup indexes")


def downgrade(conn):
    names = ('ix_certificates_serial_number', 'ix_certificates_caref')
    if isinstance(conn, sqlite3.Connection):
        for name in names:
            conn.execute(f"DROP INDEX IF EXISTS {name}")
        conn.commit()
    else:
        from sqlalchemy import text
        for name in names:
            conn.execute(text(f"DROP INDEX IF EXISTS {name}"))
