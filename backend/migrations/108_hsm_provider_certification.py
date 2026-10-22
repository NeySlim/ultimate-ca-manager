"""Migration 108: the certification an operator declares for an HSM provider.

NULL (not declared) for every existing provider; UCM does not verify the hardware.
"""
import sqlite3

pg_compatible = True


def _upgrade_sqlite(conn):
    if conn.execute("SELECT 1 FROM sqlite_master WHERE type = 'table' "
                    "AND name = 'hsm_providers'").fetchone() is None:
        return
    columns = {row[1] for row in conn.execute("PRAGMA table_info(hsm_providers)")}
    if 'certification' not in columns:
        conn.execute("ALTER TABLE hsm_providers ADD COLUMN certification VARCHAR(32)")
    conn.commit()


def _upgrade_pg(conn):
    from sqlalchemy import inspect, text

    if 'hsm_providers' not in inspect(conn).get_table_names():
        return
    conn.execute(text("ALTER TABLE hsm_providers ADD COLUMN IF NOT EXISTS "
                      "certification VARCHAR(32)"))


def upgrade(conn):
    if isinstance(conn, sqlite3.Connection):
        _upgrade_sqlite(conn)
    else:
        _upgrade_pg(conn)


def downgrade(conn):
    # Kept: older versions ignore the column.
    pass
