"""Migration 137: LDAP providers can run StartTLS before binding.

``pro_sso_providers.ldap_start_tls``: off for every existing provider, so a
directory reached in plain LDAP keeps working as before.
"""
import logging
import sqlite3

logger = logging.getLogger(__name__)
pg_compatible = True

TABLE = 'pro_sso_providers'
COLUMN = 'ldap_start_tls'


def _upgrade_sqlite(conn):
    if conn.execute("SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?",
                    (TABLE,)).fetchone() is None:
        return
    present = {row[1] for row in conn.execute(f"PRAGMA table_info({TABLE})")}
    if COLUMN not in present:
        conn.execute(f"ALTER TABLE {TABLE} ADD COLUMN {COLUMN} BOOLEAN NOT NULL DEFAULT 0")
    conn.commit()
    logger.info("[137] pro_sso_providers.ldap_start_tls (SQLite)")


def _upgrade_pg(conn):
    from sqlalchemy import inspect, text

    inspector = inspect(conn)
    if TABLE not in set(inspector.get_table_names()):
        return
    if COLUMN not in {c['name'] for c in inspector.get_columns(TABLE)}:
        conn.execute(text(f"ALTER TABLE {TABLE} ADD COLUMN {COLUMN} BOOLEAN NOT NULL DEFAULT FALSE"))
    logger.info("[137] pro_sso_providers.ldap_start_tls (PostgreSQL)")


def upgrade(conn):
    if isinstance(conn, sqlite3.Connection):
        _upgrade_sqlite(conn)
    else:
        _upgrade_pg(conn)


def downgrade(conn):
    """No downgrade: the column is harmless when unused."""
    pass
