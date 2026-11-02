"""Migration 119: an SSH CA names its certificates unless told otherwise.

Requesters could set any key ID, which sshd logs as the holder's identity.
Every CA, existing ones included, now starts with the setting off.
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
    conn.commit()


def _upgrade_pg(conn):
    from sqlalchemy import inspect, text

    inspector = inspect(conn)
    if 'ssh_cas' not in inspector.get_table_names():
        return
    if 'allow_custom_key_id' in {c['name'] for c in inspector.get_columns('ssh_cas')}:
        return
    conn.execute(text("ALTER TABLE ssh_cas ADD COLUMN allow_custom_key_id "
                      "BOOLEAN NOT NULL DEFAULT FALSE"))


def upgrade(conn):
    if isinstance(conn, sqlite3.Connection):
        _upgrade_sqlite(conn)
    else:
        _upgrade_pg(conn)


def downgrade(conn):
    # Kept: older versions ignore the column.
    pass
