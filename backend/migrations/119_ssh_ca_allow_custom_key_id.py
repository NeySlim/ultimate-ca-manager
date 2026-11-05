"""Migration 119: an SSH CA names its certificates unless told otherwise.

Requesters could set any key ID, which sshd logs as the holder's identity.
Every CA, existing ones included, now starts with the setting off. The key ID
column becomes TEXT: principals@CA name can exceed 255 characters.
"""
import sqlite3

pg_compatible = True


def _upgrade_sqlite(conn):
    if conn.execute("SELECT 1 FROM sqlite_master WHERE type = 'table' "
                    "AND name = 'ssh_cas'").fetchone() is None:
        return
    columns = {row[1] for row in conn.execute("PRAGMA table_info(ssh_cas)")}
    if 'allow_custom_key_id' not in columns:
        conn.execute("ALTER TABLE ssh_cas ADD COLUMN allow_custom_key_id "
                     "BOOLEAN NOT NULL DEFAULT 0")
    # SQLite does not enforce VARCHAR lengths: the key ID column needs nothing
    conn.commit()


def _upgrade_pg(conn):
    from sqlalchemy import inspect, text

    inspector = inspect(conn)
    tables = inspector.get_table_names()
    if 'ssh_cas' in tables and 'allow_custom_key_id' not in {
            c['name'] for c in inspector.get_columns('ssh_cas')}:
        conn.execute(text("ALTER TABLE ssh_cas ADD COLUMN allow_custom_key_id "
                          "BOOLEAN NOT NULL DEFAULT FALSE"))
    if 'ssh_certificates' in tables:
        conn.execute(text("ALTER TABLE ssh_certificates ALTER COLUMN key_id TYPE TEXT"))


def upgrade(conn):
    if isinstance(conn, sqlite3.Connection):
        _upgrade_sqlite(conn)
    else:
        _upgrade_pg(conn)


def downgrade(conn):
    # Kept: older versions ignore the column.
    pass
