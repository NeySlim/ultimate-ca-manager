"""Migration 112: remember which upstream authorizations a proxy client deactivated.

The proxy shares one upstream authorization between the orders of several clients
(#307); a deactivation that cannot be passed upstream is kept per order (#422).
"""
import sqlite3

pg_compatible = True

_TABLE = 'acme_client_orders'
_COLUMN = 'deactivated_authz_urls'


def _upgrade_sqlite(conn):
    if conn.execute("SELECT 1 FROM sqlite_master WHERE type = 'table' "
                    "AND name = ?", (_TABLE,)).fetchone() is None:
        return
    columns = {row[1] for row in conn.execute(f"PRAGMA table_info({_TABLE})")}
    if _COLUMN not in columns:
        conn.execute(f"ALTER TABLE {_TABLE} ADD COLUMN {_COLUMN} TEXT")
    conn.commit()


def _upgrade_pg(conn):
    from sqlalchemy import inspect, text

    inspector = inspect(conn)
    if _TABLE not in inspector.get_table_names():
        return
    if _COLUMN in {c['name'] for c in inspector.get_columns(_TABLE)}:
        return
    conn.execute(text(f"ALTER TABLE {_TABLE} ADD COLUMN {_COLUMN} TEXT"))


def upgrade(conn):
    if isinstance(conn, sqlite3.Connection):
        _upgrade_sqlite(conn)
    else:
        _upgrade_pg(conn)


def downgrade(conn):
    # Kept: older versions ignore the column.
    pass
