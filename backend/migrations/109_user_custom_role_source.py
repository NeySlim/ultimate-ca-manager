"""Migration 109: where a user's custom role came from.

'sso' when the SSO role mapping assigned it; NULL when set by hand (and for every
existing user, so a sync never removes a role that was assigned manually).
"""
import sqlite3

pg_compatible = True


def _upgrade_sqlite(conn):
    if conn.execute("SELECT 1 FROM sqlite_master WHERE type = 'table' "
                    "AND name = 'users'").fetchone() is None:
        return
    columns = {row[1] for row in conn.execute("PRAGMA table_info(users)")}
    if 'custom_role_source' not in columns:
        conn.execute("ALTER TABLE users ADD COLUMN custom_role_source VARCHAR(16)")
    conn.commit()


def _upgrade_pg(conn):
    from sqlalchemy import inspect, text

    if 'users' not in inspect(conn).get_table_names():
        return
    conn.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS "
                      "custom_role_source VARCHAR(16)"))


def upgrade(conn):
    if isinstance(conn, sqlite3.Connection):
        _upgrade_sqlite(conn)
    else:
        _upgrade_pg(conn)


def downgrade(conn):
    # Kept: older versions ignore the column.
    pass
