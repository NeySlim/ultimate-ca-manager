"""
Migration 023: Add ``sync_role_on_login`` column to ``pro_sso_providers``

Background
----------
Until v2.132, every SSO login on an existing user triggered ``_resolve_role``
which falls back to the provider's ``default_role`` when no ``role_mapping``
entry matches. The result was that any role change made manually in the UCM
UI (e.g. promoting a user to ``admin``) was silently reverted to the default
role on the next SSO login.

See `issue #81 <https://github.com/NeySlim/ultimate-ca-manager/issues/81>`_.

From v2.133 onwards:

* ``auto_update_users`` controls **userinfo sync only** (email, full name).
* ``default_role`` is **creation-time only**.
* Role re-sync from SSO on every login is now an **explicit opt-in** via
  the new ``sync_role_on_login`` flag (default ``FALSE``). When enabled,
  the role is only updated if the configured ``role_mapping`` resolves
  the user's external groups to a known UCM role; if no mapping matches,
  the user's stored role is left untouched.

Multi-backend convention (v2.128+): runs on both SQLite and PostgreSQL.
"""
import logging
import sqlite3

logger = logging.getLogger(__name__)
pg_compatible = True


def _column_exists_sqlite(conn, table, column):
    cur = conn.execute(f"PRAGMA table_info({table})")
    return any(row[1] == column for row in cur.fetchall())


def _upgrade_sqlite(conn):
    cur = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='pro_sso_providers'"
    )
    if not cur.fetchone():
        logger.info("Migration 023: pro_sso_providers table absent, skipping")
        return

    if not _column_exists_sqlite(conn, 'pro_sso_providers', 'sync_role_on_login'):
        conn.execute(
            "ALTER TABLE pro_sso_providers "
            "ADD COLUMN sync_role_on_login INTEGER NOT NULL DEFAULT 0"
        )
        logger.info("Migration 023: added pro_sso_providers.sync_role_on_login")

    conn.commit()


def _upgrade_pg(conn):
    # Runner passes a Connection (already in transaction) — issue #111.
    from sqlalchemy import inspect, text
    insp = inspect(conn)
    if 'pro_sso_providers' not in set(insp.get_table_names()):
        logger.info("Migration 023: pro_sso_providers table absent, skipping")
        return

    cols = {c['name'] for c in insp.get_columns('pro_sso_providers')}
    if 'sync_role_on_login' not in cols:
        conn.execute(text(
            "ALTER TABLE pro_sso_providers "
            "ADD COLUMN sync_role_on_login BOOLEAN NOT NULL DEFAULT FALSE"
        ))
        logger.info("Migration 023: added pro_sso_providers.sync_role_on_login")


def upgrade(conn):
    if isinstance(conn, sqlite3.Connection):
        _upgrade_sqlite(conn)
    else:
        _upgrade_pg(conn)


def downgrade(conn):
    """SQLite cannot DROP COLUMN cleanly; left as no-op."""
    pass
