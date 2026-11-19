"""Migration 133: the free-text audit columns become TEXT.

PostgreSQL refused an entry whose User-Agent, resource id list, resource name or
username was longer than its VARCHAR, and the action it recorded went untraced.
"""
import sqlite3

pg_compatible = True

TABLE = 'audit_logs'
COLUMNS = ('username', 'resource_id', 'resource_name', 'user_agent')


def upgrade(conn):
    # SQLite does not enforce VARCHAR lengths: nothing to change there
    if isinstance(conn, sqlite3.Connection):
        return
    from sqlalchemy import inspect, text

    if not inspect(conn).has_table(TABLE):
        return
    for column in COLUMNS:
        # VARCHAR to TEXT is binary-compatible: no table rewrite, the index on username is kept
        conn.execute(text(f"ALTER TABLE {TABLE} ALTER COLUMN {column} TYPE TEXT"))


def downgrade(conn):
    # Kept: older versions read TEXT columns unchanged.
    pass
