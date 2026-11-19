"""Migration 135: one-time TOTP codes and sessions closed by a credential change.

``totp_last_step`` holds the last TOTP time step accepted, so a code is refused
the second time (RFC 6238 §5.2). ``session_version`` is copied into each session
at login and bumped by a password change or reset: older sessions stop there.
Existing accounts start at NULL and 0, which keeps every open session valid.
"""
import sqlite3

pg_compatible = True

# (column, SQLite definition, PostgreSQL definition)
_COLUMNS = (
    ('totp_last_step', 'BIGINT', 'BIGINT'),
    ('session_version', 'INTEGER NOT NULL DEFAULT 0', 'INTEGER NOT NULL DEFAULT 0'),
)


def _upgrade_sqlite(conn):
    present = {row[1] for row in conn.execute("PRAGMA table_info(users)")}
    for name, sqlite_def, _ in _COLUMNS:
        if name not in present:
            conn.execute(f"ALTER TABLE users ADD COLUMN {name} {sqlite_def}")
    conn.commit()


def _upgrade_pg(conn):
    from sqlalchemy import text

    for name, _, pg_def in _COLUMNS:
        conn.execute(text(f"ALTER TABLE users ADD COLUMN IF NOT EXISTS {name} {pg_def}"))


def upgrade(conn):
    if isinstance(conn, sqlite3.Connection):
        _upgrade_sqlite(conn)
    else:
        _upgrade_pg(conn)


def downgrade(conn):
    # Kept: older versions ignore both columns.
    pass
