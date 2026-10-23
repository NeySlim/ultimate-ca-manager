"""Migration 110: an SSH CA signs for any principal only when told to.

An empty allowed-principals list used to mean "anything, root included".
Existing CAs without a list keep that behaviour, now as an explicit setting.
"""
import json
import sqlite3

pg_compatible = True


def _lists_nothing(stored):
    """Read as SSHCertificateAuthority.get_allowed_principals does."""
    if not stored:
        return True
    try:
        return not json.loads(stored)
    except (json.JSONDecodeError, TypeError):
        return True


def _upgrade_sqlite(conn):
    if conn.execute("SELECT 1 FROM sqlite_master WHERE type = 'table' "
                    "AND name = 'ssh_cas'").fetchone() is None:
        return
    columns = {row[1] for row in conn.execute("PRAGMA table_info(ssh_cas)")}
    if 'allow_any_principal' not in columns:
        conn.execute("ALTER TABLE ssh_cas ADD COLUMN allow_any_principal "
                     "BOOLEAN NOT NULL DEFAULT 0")
        empty = [(row[0],) for row in conn.execute("SELECT id, allowed_principals FROM ssh_cas")
                 if _lists_nothing(row[1])]
        conn.executemany("UPDATE ssh_cas SET allow_any_principal = 1 WHERE id = ?", empty)
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
    for row in conn.execute(text("SELECT id, allowed_principals FROM ssh_cas")).all():
        if _lists_nothing(row[1]):
            conn.execute(text("UPDATE ssh_cas SET allow_any_principal = TRUE WHERE id = :id"),
                         {'id': row[0]})


def upgrade(conn):
    if isinstance(conn, sqlite3.Connection):
        _upgrade_sqlite(conn)
    else:
        _upgrade_pg(conn)


def downgrade(conn):
    # Kept: older versions ignore the column.
    pass
