"""
Migration 027: Create ``acme_eab_credentials`` table

UCM previously stored ACME External Account Binding (RFC 8555 §7.3.4)
pre-shared keys as a single JSON blob in ``system_config`` under
``acme_eab_keys``. That worked but had no per-credential metadata
(label, who created it, when used, by which ACME account) and no audit
trail when issuing or revoking credentials.

This migration introduces a proper table so each EAB credential can be
managed individually from the UI, audited, expired, and bound back to
the ACME account that consumed it.

Multi-backend convention (v2.128+): runs on both SQLite and PostgreSQL.
"""
import logging
import sqlite3

logger = logging.getLogger(__name__)
pg_compatible = True

TABLE_NAME = 'acme_eab_credentials'

SQLITE_SQL = f"""
CREATE TABLE IF NOT EXISTS {TABLE_NAME} (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    kid VARCHAR(64) NOT NULL UNIQUE,
    hmac_key_b64 TEXT NOT NULL,
    label VARCHAR(255),
    created_by_user_id INTEGER,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    expires_at DATETIME,
    used_at DATETIME,
    used_by_account_id VARCHAR(64),
    revoked_at DATETIME,
    revoked_by_user_id INTEGER,
    status VARCHAR(20) NOT NULL DEFAULT 'active'
);
CREATE INDEX IF NOT EXISTS idx_acme_eab_kid ON {TABLE_NAME}(kid);
CREATE INDEX IF NOT EXISTS idx_acme_eab_status ON {TABLE_NAME}(status);
"""

PG_SQL = f"""
CREATE TABLE IF NOT EXISTS {TABLE_NAME} (
    id SERIAL PRIMARY KEY,
    kid VARCHAR(64) NOT NULL UNIQUE,
    hmac_key_b64 TEXT NOT NULL,
    label VARCHAR(255),
    created_by_user_id INTEGER,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    expires_at TIMESTAMP,
    used_at TIMESTAMP,
    used_by_account_id VARCHAR(64),
    revoked_at TIMESTAMP,
    revoked_by_user_id INTEGER,
    status VARCHAR(20) NOT NULL DEFAULT 'active'
);
CREATE INDEX IF NOT EXISTS idx_acme_eab_kid ON {TABLE_NAME}(kid);
CREATE INDEX IF NOT EXISTS idx_acme_eab_status ON {TABLE_NAME}(status);
"""


def _upgrade_sqlite(conn):
    conn.executescript(SQLITE_SQL)
    conn.commit()
    logger.info(f"Migration 027: ensured {TABLE_NAME} table (SQLite)")


def _upgrade_pg(engine):
    from sqlalchemy import text
    with engine.begin() as conn:
        for stmt in [s.strip() for s in PG_SQL.split(';') if s.strip()]:
            conn.execute(text(stmt))
    logger.info(f"Migration 027: ensured {TABLE_NAME} table (PostgreSQL)")


def upgrade(conn):
    if isinstance(conn, sqlite3.Connection):
        _upgrade_sqlite(conn)
    else:
        _upgrade_pg(conn)


def downgrade(conn):
    if isinstance(conn, sqlite3.Connection):
        conn.execute(f"DROP TABLE IF EXISTS {TABLE_NAME}")
        conn.commit()
    else:
        from sqlalchemy import text
        with conn.begin() as c:
            c.execute(text(f"DROP TABLE IF EXISTS {TABLE_NAME}"))
