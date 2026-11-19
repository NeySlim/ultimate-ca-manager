"""Upgrade step 172: the LDAP option that reads Active Directory nested groups and primary group.

``ldap_nested_groups`` is off on every existing provider: the groups read stay the direct ones
until an administrator turns it on. Idempotent, dual-backend (SQLite + PostgreSQL).
"""
import logging
import sqlite3

logger = logging.getLogger(__name__)
pg_compatible = True

TABLE = 'pro_sso_providers'
COLUMN = 'ldap_nested_groups'
DDL = "ALTER TABLE {table} ADD COLUMN {column} BOOLEAN DEFAULT {false} NOT NULL"


def upgrade(conn):
    if isinstance(conn, sqlite3.Connection):
        exists = conn.execute("SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?",
                              (TABLE,)).fetchone() is not None
        if exists and COLUMN not in {row[1] for row in conn.execute(f"PRAGMA table_info({TABLE})")}:
            conn.execute(DDL.format(table=TABLE, column=COLUMN, false='0'))
            logger.info("[172] LDAP nested groups option (SQLite)")
        conn.commit()
        return
    from sqlalchemy import inspect, text
    inspector = inspect(conn)
    if TABLE in inspector.get_table_names() and \
            COLUMN not in {c['name'] for c in inspector.get_columns(TABLE)}:
        conn.execute(text(DDL.format(table=TABLE, column=COLUMN, false='false')))
        logger.info("[172] LDAP nested groups option (PostgreSQL)")


def downgrade(conn):
    """No downgrade: 2.254 ignores the column."""
