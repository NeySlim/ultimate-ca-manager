"""Migration 042: key recovery (escrow) requests.

Adds the ``key_recovery_requests`` table backing the dual-control private-key
recovery workflow (request -> approve -> recover), with full audit fields.
"""
import logging
import sqlite3

logger = logging.getLogger(__name__)
pg_compatible = True


_SQLITE_DDL = """
CREATE TABLE IF NOT EXISTS key_recovery_requests (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    cert_id INTEGER NOT NULL,
    cert_refid VARCHAR(64),
    cert_cn VARCHAR(255),
    reason TEXT NOT NULL,
    status VARCHAR(16) NOT NULL DEFAULT 'pending',
    requested_by VARCHAR(120) NOT NULL,
    requested_at DATETIME NOT NULL,
    decided_by VARCHAR(120),
    decided_at DATETIME,
    decision_note TEXT,
    recovered_by VARCHAR(120),
    recovered_at DATETIME
)
"""

_PG_DDL = """
CREATE TABLE IF NOT EXISTS key_recovery_requests (
    id SERIAL PRIMARY KEY,
    cert_id INTEGER NOT NULL,
    cert_refid VARCHAR(64),
    cert_cn VARCHAR(255),
    reason TEXT NOT NULL,
    status VARCHAR(16) NOT NULL DEFAULT 'pending',
    requested_by VARCHAR(120) NOT NULL,
    requested_at TIMESTAMP NOT NULL,
    decided_by VARCHAR(120),
    decided_at TIMESTAMP,
    decision_note TEXT,
    recovered_by VARCHAR(120),
    recovered_at TIMESTAMP
)
"""


def _upgrade_sqlite(conn):
    conn.execute(_SQLITE_DDL)
    conn.execute("CREATE INDEX IF NOT EXISTS ix_key_recovery_status ON key_recovery_requests(status)")
    conn.execute("CREATE INDEX IF NOT EXISTS ix_key_recovery_cert ON key_recovery_requests(cert_id)")
    conn.commit()
    logger.info("[042] created key_recovery_requests (SQLite)")


def _upgrade_pg(conn):
    from sqlalchemy import text
    conn.execute(text(_PG_DDL))
    conn.execute(text("CREATE INDEX IF NOT EXISTS ix_key_recovery_status ON key_recovery_requests(status)"))
    conn.execute(text("CREATE INDEX IF NOT EXISTS ix_key_recovery_cert ON key_recovery_requests(cert_id)"))
    logger.info("[042] created key_recovery_requests (PostgreSQL)")


def upgrade(conn):
    if isinstance(conn, sqlite3.Connection):
        _upgrade_sqlite(conn)
    else:
        _upgrade_pg(conn)


def downgrade(conn):
    if isinstance(conn, sqlite3.Connection):
        conn.execute("DROP TABLE IF EXISTS key_recovery_requests")
        conn.commit()
    else:
        from sqlalchemy import text
        conn.execute(text("DROP TABLE IF EXISTS key_recovery_requests"))
