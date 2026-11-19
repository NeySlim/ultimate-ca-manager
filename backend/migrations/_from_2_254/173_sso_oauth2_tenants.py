"""Upgrade step 173: an OIDC provider may accept a named list of Microsoft Entra tenants.

``pro_sso_providers.oauth2_tenants``: a JSON array of tenant ids (GUIDs); empty keeps the
single-issuer validation. ``oauth2_role_tenants``: those of them whose role claims are honoured.
``user_sso_identities.expected_tenant``: the tenant an attachment not bound yet may be adopted from.
Idempotent, dual-backend (SQLite + PostgreSQL).
"""
import logging
import sqlite3

logger = logging.getLogger(__name__)
pg_compatible = True

COLUMNS = (
    ('pro_sso_providers', 'oauth2_tenants', 'TEXT'),
    ('pro_sso_providers', 'oauth2_role_tenants', 'TEXT'),
    ('user_sso_identities', 'expected_tenant', 'VARCHAR(36)'),
)


def upgrade(conn):
    if isinstance(conn, sqlite3.Connection):
        tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
        for table, column, kind in COLUMNS:
            if table in tables and column not in {
                    row[1] for row in conn.execute(f"PRAGMA table_info({table})")}:
                conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {kind}")
                logger.info(f"[173] {table}.{column} (SQLite)")
        conn.commit()
        return
    from sqlalchemy import inspect, text
    tables = set(inspect(conn).get_table_names())
    for table, column, kind in COLUMNS:
        if table in tables and column not in {c['name'] for c in inspect(conn).get_columns(table)}:
            conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {column} {kind}"))
            logger.info(f"[173] {table}.{column} (PostgreSQL)")


def downgrade(conn):
    """No downgrade: 2.254 ignores the columns."""
