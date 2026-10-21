"""Migration 106: the RSA signature scheme a CA signs with.

`pkcs1v15` for every existing CA, which is what they all signed with; `pss`
is opt-in per CA and only meaningful for an RSA key.
"""
import sqlite3

pg_compatible = True


def _upgrade_sqlite(conn):
    if conn.execute("SELECT 1 FROM sqlite_master WHERE type = 'table' "
                    "AND name = 'certificate_authorities'").fetchone() is None:
        return
    columns = {row[1] for row in conn.execute("PRAGMA table_info(certificate_authorities)")}
    if 'signature_scheme' not in columns:
        conn.execute("ALTER TABLE certificate_authorities ADD COLUMN "
                     "signature_scheme VARCHAR(16) NOT NULL DEFAULT 'pkcs1v15'")
    conn.commit()


def _upgrade_pg(conn):
    from sqlalchemy import inspect, text

    if 'certificate_authorities' not in inspect(conn).get_table_names():
        return
    conn.execute(text("ALTER TABLE certificate_authorities ADD COLUMN IF NOT EXISTS "
                      "signature_scheme VARCHAR(16) NOT NULL DEFAULT 'pkcs1v15'"))


def upgrade(conn):
    if isinstance(conn, sqlite3.Connection):
        _upgrade_sqlite(conn)
    else:
        _upgrade_pg(conn)


def downgrade(conn):
    # Kept: older versions ignore the column and sign PKCS#1 v1.5.
    pass
