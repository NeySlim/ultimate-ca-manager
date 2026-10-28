"""Migration 113: remember what a PKCS#11 provider's module says it is.

Read at each successful connection test: library, manufacturer, versions.
"""
import sqlite3

pg_compatible = True

_TABLE = 'hsm_providers'
_COLUMN = 'module_info'


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
