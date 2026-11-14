"""Upgrade step 146: the certificates an ACME order's renewals moved off, kept with the order.

A renewal that cannot write into the order's row (revoked or on hold) imports a new one; the
old row must still lead to the CA account that obtained it, to be revoked there later.
"""
import sqlite3

pg_compatible = True

TABLE = 'acme_client_orders'
COLUMN = f"ALTER TABLE {TABLE} ADD COLUMN replaced_certificates TEXT"


def _upgrade_sqlite(conn):
    if conn.execute("SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?",
                    (TABLE,)).fetchone() is not None:
        if 'replaced_certificates' not in {row[1] for row in conn.execute(f"PRAGMA table_info({TABLE})")}:
            conn.execute(COLUMN)
    conn.commit()


def _upgrade_pg(conn):
    from sqlalchemy import inspect, text

    inspector = inspect(conn)
    if TABLE in inspector.get_table_names():
        if 'replaced_certificates' not in {c['name'] for c in inspector.get_columns(TABLE)}:
            conn.execute(text(COLUMN))


def upgrade(conn):
    if isinstance(conn, sqlite3.Connection):
        _upgrade_sqlite(conn)
    else:
        _upgrade_pg(conn)


def downgrade(conn):
    """No downgrade: older versions ignore the column."""
