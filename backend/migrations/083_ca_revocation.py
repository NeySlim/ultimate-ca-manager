"""Migration 083: revocation of an intermediate CA (#343).

certificate_authorities gains the revocation state a certificate row already
carries: revoked (BOOLEAN), revoked_at (DATETIME), revoke_reason (VARCHAR(100),
RFC 5280 reason name) and invalidity_at (DATETIME, RFC 5280 §5.3.2). The
parent's CRL and OCSP answers come from a revoked_serials row written at
revocation time, so no other table changes.
"""

import logging
import sqlite3

logger = logging.getLogger(__name__)
pg_compatible = True

_COLUMNS_SQLITE = (
    ("revoked", "BOOLEAN DEFAULT 0"),
    ("revoked_at", "DATETIME"),
    ("revoke_reason", "VARCHAR(100)"),
    ("invalidity_at", "DATETIME"),
)

_COLUMNS_PG = (
    ("revoked", "BOOLEAN DEFAULT FALSE"),
    ("revoked_at", "TIMESTAMP"),
    ("revoke_reason", "VARCHAR(100)"),
    ("invalidity_at", "TIMESTAMP"),
)


def _upgrade_sqlite(conn):
    cols = {row[1] for row in conn.execute("PRAGMA table_info(certificate_authorities)")}
    for name, ddl in _COLUMNS_SQLITE:
        if name not in cols:
            conn.execute(f"ALTER TABLE certificate_authorities ADD COLUMN {name} {ddl}")
            logger.info("083: added %s column to certificate_authorities (SQLite)", name)
    conn.commit()


def _upgrade_pg(conn):
    from sqlalchemy import inspect, text

    inspector = inspect(conn)
    cols = {c['name'] for c in inspector.get_columns('certificate_authorities')}
    for name, ddl in _COLUMNS_PG:
        if name not in cols:
            conn.execute(text(f"ALTER TABLE certificate_authorities ADD COLUMN {name} {ddl}"))
            logger.info("083: added %s column to certificate_authorities (PostgreSQL)", name)


def upgrade(conn):
    if isinstance(conn, sqlite3.Connection):
        _upgrade_sqlite(conn)
    else:
        _upgrade_pg(conn)


def downgrade(conn):
    # Added columns are harmless if left behind (same policy as 079/080/082).
    pass
