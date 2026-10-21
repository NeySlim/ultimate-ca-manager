"""Migration 107: the compliance profile a CA is bound by.

NULL (no profile) for every existing CA; the profile only binds what the CA
issues from the moment one is set.
"""
import sqlite3

pg_compatible = True


def _upgrade_sqlite(conn):
    if conn.execute("SELECT 1 FROM sqlite_master WHERE type = 'table' "
                    "AND name = 'certificate_authorities'").fetchone() is None:
        return
    columns = {row[1] for row in conn.execute("PRAGMA table_info(certificate_authorities)")}
    if 'compliance_profile' not in columns:
        conn.execute("ALTER TABLE certificate_authorities ADD COLUMN "
                     "compliance_profile VARCHAR(16)")
    conn.commit()


def _upgrade_pg(conn):
    from sqlalchemy import inspect, text

    if 'certificate_authorities' not in inspect(conn).get_table_names():
        return
    conn.execute(text("ALTER TABLE certificate_authorities ADD COLUMN IF NOT EXISTS "
                      "compliance_profile VARCHAR(16)"))


def upgrade(conn):
    if isinstance(conn, sqlite3.Connection):
        _upgrade_sqlite(conn)
    else:
        _upgrade_pg(conn)


def downgrade(conn):
    # Kept: older versions ignore the column.
    pass
