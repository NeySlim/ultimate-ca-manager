"""Upgrade step 165: an optional LDAP group search base; empty keeps the derived base."""
import logging
import sqlite3

logger = logging.getLogger(__name__)
pg_compatible = True

TABLE = 'pro_sso_providers'
COLUMN = 'ldap_group_base_dn'
DDL = f"ALTER TABLE {TABLE} ADD COLUMN {COLUMN} VARCHAR(500)"


def upgrade(conn):
    if isinstance(conn, sqlite3.Connection):
        if conn.execute("SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?",
                        (TABLE,)).fetchone() is not None \
                and COLUMN not in {row[1] for row in conn.execute(f"PRAGMA table_info({TABLE})")}:
            conn.execute(DDL)
            logger.info("[165] LDAP group search base (SQLite)")
        conn.commit()
        return
    from sqlalchemy import inspect, text
    inspector = inspect(conn)
    if TABLE in inspector.get_table_names() \
            and COLUMN not in {c['name'] for c in inspector.get_columns(TABLE)}:
        conn.execute(text(DDL))
        logger.info("[165] LDAP group search base (PostgreSQL)")


def downgrade(conn):
    """No downgrade: 2.254 ignores the column."""
