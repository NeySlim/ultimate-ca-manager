"""Migration 038: add notes column to acme_eab_credentials.

Allows operators to attach free-form notes to EAB credentials for
tracking purposes (e.g. which cluster/team a credential belongs to).

Idempotent and dual-backend (SQLite + PostgreSQL).
"""

import logging
import sqlite3

logger = logging.getLogger(__name__)
pg_compatible = True


def _upgrade_sqlite(conn):
    """Upgrade SQLite database."""
    cur = conn.execute("PRAGMA table_info(acme_eab_credentials)")
    existing = {row[1] for row in cur.fetchall()}
    if 'notes' in existing:
        logger.info("[038] notes column already exists on acme_eab_credentials, skipping")
        return

    conn.execute("ALTER TABLE acme_eab_credentials ADD COLUMN notes TEXT")
    logger.info("[038] added notes column to acme_eab_credentials (SQLite)")
    conn.commit()


def _upgrade_pg(conn):
    """Upgrade PostgreSQL database."""
    from sqlalchemy import inspect, text

    insp = inspect(conn)
    cols = {c['name'] for c in insp.get_columns('acme_eab_credentials')}
    if 'notes' in cols:
        logger.info("[038] notes column already exists on acme_eab_credentials, skipping")
        return

    conn.execute(text("ALTER TABLE acme_eab_credentials ADD COLUMN notes TEXT"))
    logger.info("[038] added notes column to acme_eab_credentials (PostgreSQL)")


def upgrade(conn):
    """Main upgrade dispatcher."""
    if isinstance(conn, sqlite3.Connection):
        _upgrade_sqlite(conn)
    else:
        _upgrade_pg(conn)


def downgrade(conn):
    """Downgrade dispatcher."""
    if isinstance(conn, sqlite3.Connection):
        _downgrade_sqlite(conn)
    else:
        _downgrade_pg(conn)


def _downgrade_sqlite(conn):
    """Remove notes column from SQLite (recreate table without it)."""
    cur = conn.execute("PRAGMA table_info(acme_eab_credentials)")
    existing = {row[1] for row in cur.fetchall()}
    if 'notes' not in existing:
        logger.info("[038] notes column absent, skipping downgrade")
        return

    # SQLite has no DROP COLUMN before 3.35.0 — rebuild table.
    conn.execute("""
        CREATE TABLE acme_eab_credentials_backup (
            id INTEGER PRIMARY KEY,
            kid VARCHAR(64) UNIQUE NOT NULL,
            hmac_key_b64 TEXT NOT NULL,
            label VARCHAR(255),
            created_by_user_id INTEGER,
            created_at DATETIME NOT NULL,
            expires_at DATETIME,
            used_at DATETIME,
            used_by_account_id VARCHAR(64),
            revoked_at DATETIME,
            revoked_by_user_id INTEGER,
            status VARCHAR(20) DEFAULT 'active' NOT NULL
        )
    """)
    conn.execute("""
        INSERT INTO acme_eab_credentials_backup
            (id, kid, hmac_key_b64, label, created_by_user_id, created_at,
             expires_at, used_at, used_by_account_id, revoked_at,
             revoked_by_user_id, status)
        SELECT id, kid, hmac_key_b64, label, created_by_user_id, created_at,
               expires_at, used_at, used_by_account_id, revoked_at,
               revoked_by_user_id, status
        FROM acme_eab_credentials
    """)
    conn.execute("DROP TABLE acme_eab_credentials")
    conn.execute("ALTER TABLE acme_eab_credentials_backup RENAME TO acme_eab_credentials")
    logger.info("[038] dropped notes column from acme_eab_credentials (SQLite)")
    conn.commit()


def _downgrade_pg(conn):
    """Remove notes column from PostgreSQL."""
    from sqlalchemy import inspect, text

    insp = inspect(conn)
    cols = {c['name'] for c in insp.get_columns('acme_eab_credentials')}
    if 'notes' not in cols:
        logger.info("[038] notes column absent, skipping downgrade")
        return

    conn.execute(text("ALTER TABLE acme_eab_credentials DROP COLUMN IF EXISTS notes"))
    logger.info("[038] dropped notes column from acme_eab_credentials (PostgreSQL)")
