"""Migration 127: custom X.509 extensions a template adds to its certificates (#437).

A JSON list of {oid, critical, value}; NULL for every existing template.
"""
import sqlite3

pg_compatible = True


def _upgrade_sqlite(conn):
    if conn.execute("SELECT 1 FROM sqlite_master WHERE type = 'table' "
                    "AND name = 'certificate_templates'").fetchone() is None:
        return
    columns = {row[1] for row in conn.execute("PRAGMA table_info(certificate_templates)")}
    if 'custom_extensions' not in columns:
        conn.execute("ALTER TABLE certificate_templates ADD COLUMN custom_extensions TEXT")
    conn.commit()


def _upgrade_pg(conn):
    from sqlalchemy import inspect, text

    if 'certificate_templates' not in inspect(conn).get_table_names():
        return
    conn.execute(text("ALTER TABLE certificate_templates ADD COLUMN IF NOT EXISTS "
                      "custom_extensions TEXT"))


def upgrade(conn):
    if isinstance(conn, sqlite3.Connection):
        _upgrade_sqlite(conn)
    else:
        _upgrade_pg(conn)


def downgrade(conn):
    # Kept: older versions ignore the column.
    pass
