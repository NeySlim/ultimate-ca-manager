"""Migration 076: add Microsoft Intune SCEP challenge validation columns to scep_profiles.

Issue #228 part 2. Intune doesn't support a static SCEP challenge password --
it issues a per-device, per-request encrypted+signed challenge blob that only
Intune's own API can validate. These columns hold the per-profile Entra app
registration (tenant/client id + encrypted client secret) an admin configures
to enable that live validation, mutually exclusive in practice with the
existing static challenge_password. Defaults to NULL/disabled -- existing
profiles keep working exactly as before until an admin opts one in.

intune_client_secret is encrypted via utils.encryption (always encrypts --
unlike security.encryption's encrypt_text, which challenge_password uses and
which silently stores plaintext if no master key is configured). A real Entra
app secret gets the stronger of this codebase's two encryption helpers.

Idempotent and multi-backend (SQLite + PostgreSQL).
"""

import logging
import sqlite3

logger = logging.getLogger(__name__)
pg_compatible = True

_NEW_COLUMNS_SQLITE = [
    ("intune_enabled", "BOOLEAN DEFAULT 0 NOT NULL"),
    ("intune_tenant_id", "VARCHAR(255)"),
    ("intune_client_id", "VARCHAR(255)"),
    ("intune_client_secret", "TEXT"),
    ("intune_last_test_at", "DATETIME"),
    ("intune_last_test_result", "VARCHAR(255)"),
]

_NEW_COLUMNS_PG = [
    ("intune_enabled", "BOOLEAN DEFAULT FALSE NOT NULL"),
    ("intune_tenant_id", "VARCHAR(255)"),
    ("intune_client_id", "VARCHAR(255)"),
    ("intune_client_secret", "TEXT"),
    ("intune_last_test_at", "TIMESTAMP"),
    ("intune_last_test_result", "VARCHAR(255)"),
]


def _upgrade_sqlite(conn):
    cur = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='scep_profiles'"
    )
    if not cur.fetchone():
        logger.info("076: scep_profiles table absent, skipping")
        return

    cur = conn.execute("PRAGMA table_info(scep_profiles)")
    cols = {row[1] for row in cur.fetchall()}

    for name, ddl in _NEW_COLUMNS_SQLITE:
        if name in cols:
            continue
        conn.execute(f"ALTER TABLE scep_profiles ADD COLUMN {name} {ddl}")
        logger.info("076: added %s column to scep_profiles (SQLite)", name)
    conn.commit()


def _upgrade_pg(conn):
    from sqlalchemy import inspect, text

    insp = inspect(conn)
    if 'scep_profiles' not in set(insp.get_table_names()):
        logger.info("076: scep_profiles table absent, skipping")
        return

    cols = {c['name'] for c in insp.get_columns('scep_profiles')}

    for name, ddl in _NEW_COLUMNS_PG:
        if name in cols:
            continue
        conn.execute(text(f"ALTER TABLE scep_profiles ADD COLUMN {name} {ddl}"))
        logger.info("076: added %s column to scep_profiles (PostgreSQL)", name)


def upgrade(conn):
    if isinstance(conn, sqlite3.Connection):
        _upgrade_sqlite(conn)
    else:
        _upgrade_pg(conn)


def downgrade(conn):
    # SQLite has no simple DROP COLUMN -- no-op
    pass
