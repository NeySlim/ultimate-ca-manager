"""Migration 118: a CA its operator keeps out of the issuance pickers (#430).

False for every existing CA: they all stay listed until hidden by hand.
"""
import sqlite3

pg_compatible = True


def _upgrade_sqlite(conn):
    if conn.execute("SELECT 1 FROM sqlite_master WHERE type = 'table' "
                    "AND name = 'certificate_authorities'").fetchone() is None:
        return
    columns = {row[1] for row in conn.execute("PRAGMA table_info(certificate_authorities)")}
    if 'issuance_hidden' not in columns:
        conn.execute("ALTER TABLE certificate_authorities ADD COLUMN "
                     "issuance_hidden BOOLEAN NOT NULL DEFAULT 0")
    conn.commit()


def _upgrade_pg(conn):
    from sqlalchemy import inspect, text

    if 'certificate_authorities' not in inspect(conn).get_table_names():
        return
    conn.execute(text("ALTER TABLE certificate_authorities ADD COLUMN IF NOT EXISTS "
                      "issuance_hidden BOOLEAN NOT NULL DEFAULT FALSE"))


def upgrade(conn):
    if isinstance(conn, sqlite3.Connection):
        _upgrade_sqlite(conn)
    else:
        _upgrade_pg(conn)


def downgrade(conn):
    # Kept: older versions ignore the column.
    pass
