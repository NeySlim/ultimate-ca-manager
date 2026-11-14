"""Upgrade step 145: the page an SP-initiated SAML login returns to, kept with its AuthnRequest id."""
import sqlite3

pg_compatible = True

TABLE = 'pro_sso_saml_message_ids'
COLUMN = f"ALTER TABLE {TABLE} ADD COLUMN next_path VARCHAR(512)"


def _upgrade_sqlite(conn):
    if conn.execute("SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?",
                    (TABLE,)).fetchone() is not None:
        if 'next_path' not in {row[1] for row in conn.execute(f"PRAGMA table_info({TABLE})")}:
            conn.execute(COLUMN)
    conn.commit()


def _upgrade_pg(conn):
    from sqlalchemy import inspect, text

    inspector = inspect(conn)
    if TABLE in inspector.get_table_names():
        if 'next_path' not in {c['name'] for c in inspector.get_columns(TABLE)}:
            conn.execute(text(COLUMN))


def upgrade(conn):
    if isinstance(conn, sqlite3.Connection):
        _upgrade_sqlite(conn)
    else:
        _upgrade_pg(conn)


def downgrade(conn):
    """No downgrade: older versions ignore the column."""
