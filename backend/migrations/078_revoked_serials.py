"""Migration 078: create revoked_serials table for persistent revocation records.

When a certificate is revoked and later deleted (e.g. after renewal), the
revocation must still appear in CRLs and OCSP responses until the original
certificate's notAfter has passed. This table holds the minimal data needed
to generate those revocation entries independently of the certificates table.
"""

import logging
import sqlite3

logger = logging.getLogger(__name__)
pg_compatible = True


_DDL_SQLITE = """
CREATE TABLE IF NOT EXISTS revoked_serials (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    caref VARCHAR(36) NOT NULL,
    serial_number VARCHAR(100) NOT NULL,
    revoked_at DATETIME NOT NULL,
    revoke_reason VARCHAR(100),
    invalidity_at DATETIME,
    valid_to DATETIME NOT NULL,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    certificate_id INTEGER,
    FOREIGN KEY (caref) REFERENCES certificate_authorities(refid)
)
"""

_DDL_PG = """
CREATE TABLE IF NOT EXISTS revoked_serials (
    id SERIAL PRIMARY KEY,
    caref VARCHAR(36) NOT NULL REFERENCES certificate_authorities(refid),
    serial_number VARCHAR(100) NOT NULL,
    revoked_at TIMESTAMP NOT NULL,
    revoke_reason VARCHAR(100),
    invalidity_at TIMESTAMP,
    valid_to TIMESTAMP NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    certificate_id INTEGER
)
"""

_INDEX_CAREF = "CREATE INDEX IF NOT EXISTS ix_revoked_serials_caref ON revoked_serials (caref)"
_INDEX_SERIAL = "CREATE INDEX IF NOT EXISTS ix_revoked_serials_serial_number ON revoked_serials (serial_number)"


def _upgrade_sqlite(conn):
    cur = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='revoked_serials'"
    )
    if cur.fetchone():
        logger.info("078: revoked_serials table already exists, skipping")
        return

    conn.executescript(_DDL_SQLITE)
    conn.execute(_INDEX_CAREF)
    conn.execute(_INDEX_SERIAL)
    conn.commit()
    logger.info("078: created revoked_serials table (SQLite)")


def _upgrade_pg(conn):
    from sqlalchemy import inspect, text

    insp = inspect(conn)
    if 'revoked_serials' in set(insp.get_table_names()):
        logger.info("078: revoked_serials table already exists, skipping")
        return

    conn.execute(text(_DDL_PG))
    conn.execute(text(_INDEX_CAREF))
    conn.execute(text(_INDEX_SERIAL))
    logger.info("078: created revoked_serials table (PostgreSQL)")


def upgrade(conn):
    if isinstance(conn, sqlite3.Connection):
        _upgrade_sqlite(conn)
    else:
        _upgrade_pg(conn)


def downgrade(conn):
    if isinstance(conn, sqlite3.Connection):
        conn.execute("DROP TABLE IF EXISTS revoked_serials")
        conn.commit()
    else:
        from sqlalchemy import text
        conn.execute(text("DROP TABLE IF EXISTS revoked_serials"))
