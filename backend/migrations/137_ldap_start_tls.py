"""Migration 137: LDAP providers can run StartTLS before binding.

``pro_sso_providers.ldap_start_tls``: off for every existing provider, so a
directory reached in plain LDAP keeps working as before. A NULL or unknown
``default_role`` meant viewer until now; it becomes viewer explicitly, since an
empty default role now refuses unmapped users.
"""
import logging
import sqlite3

logger = logging.getLogger(__name__)
pg_compatible = True

TABLE = 'pro_sso_providers'
COLUMN = 'ldap_start_tls'
ROLES = "('admin', 'operator', 'auditor', 'viewer')"
NORMALISE_ROLE = (f"UPDATE {TABLE} SET default_role = 'viewer' "
                  f"WHERE default_role IS NULL OR default_role NOT IN {ROLES}")


def _upgrade_sqlite(conn):
    if conn.execute("SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?",
                    (TABLE,)).fetchone() is None:
        return
    present = {row[1] for row in conn.execute(f"PRAGMA table_info({TABLE})")}
    if COLUMN not in present:  # first run only: a later empty default role is a choice
        conn.execute(f"ALTER TABLE {TABLE} ADD COLUMN {COLUMN} BOOLEAN NOT NULL DEFAULT 0")
        if 'default_role' in present:
            conn.execute(NORMALISE_ROLE)
    conn.commit()
    logger.info("[137] pro_sso_providers.ldap_start_tls (SQLite)")


def _upgrade_pg(conn):
    from sqlalchemy import inspect, text

    inspector = inspect(conn)
    if TABLE not in set(inspector.get_table_names()):
        return
    present = {c['name'] for c in inspector.get_columns(TABLE)}
    if COLUMN not in present:  # first run only: a later empty default role is a choice
        conn.execute(text(f"ALTER TABLE {TABLE} ADD COLUMN {COLUMN} BOOLEAN NOT NULL DEFAULT FALSE"))
        if 'default_role' in present:
            conn.execute(text(NORMALISE_ROLE))
    logger.info("[137] pro_sso_providers.ldap_start_tls (PostgreSQL)")


def upgrade(conn):
    if isinstance(conn, sqlite3.Connection):
        _upgrade_sqlite(conn)
    else:
        _upgrade_pg(conn)


def downgrade(conn):
    """No downgrade: the column is harmless when unused."""
    pass
