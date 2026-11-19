"""Upgrade step 173: an OIDC provider may accept a named list of Microsoft Entra tenants.

``oauth2_tenants``: a JSON array of tenant ids (GUIDs); empty keeps the single-issuer validation.
Idempotent, dual-backend (SQLite + PostgreSQL).
"""
import logging
import sqlite3

logger = logging.getLogger(__name__)
pg_compatible = True

TABLE = 'pro_sso_providers'
COLUMN = 'oauth2_tenants'
DDL = f"ALTER TABLE {TABLE} ADD COLUMN {COLUMN} TEXT"


def upgrade(conn):
    if isinstance(conn, sqlite3.Connection):
        tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
        if TABLE in tables and COLUMN not in {
                row[1] for row in conn.execute(f"PRAGMA table_info({TABLE})")}:
            conn.execute(DDL)
            logger.info("[173] OIDC accepted tenants (SQLite)")
        conn.commit()
        return
    from sqlalchemy import inspect, text
    if TABLE not in inspect(conn).get_table_names():
        return
    if COLUMN not in {c['name'] for c in inspect(conn).get_columns(TABLE)}:
        conn.execute(text(DDL))
        logger.info("[173] OIDC accepted tenants (PostgreSQL)")


def downgrade(conn):
    """No downgrade: 2.254 ignores the column."""
