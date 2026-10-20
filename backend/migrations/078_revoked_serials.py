"""Migration 078: persistent revocation records and renewal counters.

revoked_serials keeps a revoked serial after its certificate row is gone, so
the CRL and OCSP keep answering "revoked". certificates gains renewed_at
(last in-place renewal, naive UTC) and renewed_times (NOT NULL, 0).
Installations that already applied this file never replay it: the schema
below is the one they carry.
"""

import logging
import sqlite3

logger = logging.getLogger(__name__)
pg_compatible = True

_TABLE_SQLITE = """
    CREATE TABLE IF NOT EXISTS revoked_serials (
        id INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT,
        caref VARCHAR(36) NOT NULL,
        serial_number VARCHAR(100) NOT NULL,
        revoked_at DATETIME NOT NULL,
        revoke_reason VARCHAR(100),
        invalidity_at DATETIME,
        valid_to DATETIME NOT NULL,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        certificate_id INTEGER,
        FOREIGN KEY(caref) REFERENCES certificate_authorities (refid)
    )
"""

_TABLE_PG = """
    CREATE TABLE IF NOT EXISTS revoked_serials (
        id SERIAL PRIMARY KEY,
        caref VARCHAR(36) NOT NULL REFERENCES certificate_authorities (refid),
        serial_number VARCHAR(100) NOT NULL,
        revoked_at TIMESTAMP NOT NULL,
        revoke_reason VARCHAR(100),
        invalidity_at TIMESTAMP,
        valid_to TIMESTAMP NOT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        certificate_id INTEGER
    )
"""

# Same statements on both engines; certificate_id deliberately has no FK
_INDEXES = (
    "CREATE INDEX IF NOT EXISTS ix_revoked_serials_caref ON revoked_serials (caref)",
    "CREATE INDEX IF NOT EXISTS ix_revoked_serials_serial_number "
    "ON revoked_serials (serial_number)",
    "CREATE INDEX IF NOT EXISTS ix_revoked_serials_certificate_id "
    "ON revoked_serials (certificate_id)",
)

_COLUMNS_SQLITE = (
    ("renewed_at", "DATETIME"),
    ("renewed_times", "INTEGER NOT NULL DEFAULT 0"),
)

_COLUMNS_PG = (
    ("renewed_at", "TIMESTAMP"),
    ("renewed_times", "INTEGER NOT NULL DEFAULT 0"),
)


def _upgrade_sqlite(conn):
    tables = {row[0] for row in conn.execute(
        "SELECT name FROM sqlite_master WHERE type = 'table'")}
    conn.execute(_TABLE_SQLITE)
    for statement in _INDEXES:
        conn.execute(statement)
    if 'certificates' in tables:
        cols = {row[1] for row in conn.execute("PRAGMA table_info(certificates)")}
        for name, ddl in _COLUMNS_SQLITE:
            if name not in cols:
                conn.execute(f"ALTER TABLE certificates ADD COLUMN {name} {ddl}")
                logger.info("078: added %s column to certificates (SQLite)", name)
    else:
        logger.warning("078: no certificates table, renewal columns not added (SQLite)")
    conn.commit()


def _upgrade_pg(conn):
    from sqlalchemy import inspect, text

    inspector = inspect(conn)
    tables = set(inspector.get_table_names())
    conn.execute(text(_TABLE_PG))
    for statement in _INDEXES:
        conn.execute(text(statement))
    if 'certificates' in tables:
        cols = {c['name'] for c in inspector.get_columns('certificates')}
        for name, ddl in _COLUMNS_PG:
            if name not in cols:
                conn.execute(text(f"ALTER TABLE certificates ADD COLUMN {name} {ddl}"))
                logger.info("078: added %s column to certificates (PostgreSQL)", name)
    else:
        logger.warning("078: no certificates table, renewal columns not added (PostgreSQL)")


def upgrade(conn):
    if isinstance(conn, sqlite3.Connection):
        _upgrade_sqlite(conn)
    else:
        _upgrade_pg(conn)


def downgrade(conn):
    if isinstance(conn, sqlite3.Connection):
        # The renewal columns stay: older SQLite cannot drop a column
        conn.execute("DROP TABLE IF EXISTS revoked_serials")
        conn.commit()
    else:
        from sqlalchemy import text
        conn.execute(text("ALTER TABLE IF EXISTS certificates DROP COLUMN IF EXISTS renewed_at"))
        conn.execute(text("ALTER TABLE IF EXISTS certificates DROP COLUMN IF EXISTS renewed_times"))
        conn.execute(text("DROP TABLE IF EXISTS revoked_serials"))
