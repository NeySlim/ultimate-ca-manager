"""Migration 110: an SSH CA signs for any principal only when told to.

An empty allowed-principals list used to mean "anything, root included".
Existing CAs without a list keep that behaviour, now as an explicit setting.
"""
import sqlite3

pg_compatible = True

_EMPTY = "allowed_principals IS NULL OR TRIM(allowed_principals) IN ('', '[]')"


def _upgrade_sqlite(conn):
    if conn.execute("SELECT 1 FROM sqlite_master WHERE type = 'table' "
                    "AND name = 'ssh_cas'").fetchone() is None:
        return
    columns = {row[1] for row in conn.execute("PRAGMA table_info(ssh_cas)")}
    if 'allow_any_principal' not in columns:
        conn.execute("ALTER TABLE ssh_cas ADD COLUMN allow_any_principal "
                     "BOOLEAN NOT NULL DEFAULT 0")
        conn.execute(f"UPDATE ssh_cas SET allow_any_principal = 1 WHERE {_EMPTY}")
    conn.commit()


def _upgrade_pg(conn):
    from sqlalchemy import inspect, text

    inspector = inspect(conn)
    if 'ssh_cas' not in inspector.get_table_names():
        return
    if 'allow_any_principal' in {c['name'] for c in inspector.get_columns('ssh_cas')}:
        return
    conn.execute(text("ALTER TABLE ssh_cas ADD COLUMN allow_any_principal "
                      "BOOLEAN NOT NULL DEFAULT FALSE"))
    conn.execute(text(f"UPDATE ssh_cas SET allow_any_principal = TRUE WHERE {_EMPTY}"))


def upgrade(conn):
    if isinstance(conn, sqlite3.Connection):
        _upgrade_sqlite(conn)
    else:
        _upgrade_pg(conn)


def downgrade(conn):
    # Kept: older versions ignore the column.
    pass
