"""Migration 100: let a user turn on a security key as their second factor.

Without enforced 2FA, a WebAuthn key only served passwordless logins. The
flag makes a password login ask for the key, and keeps asking after an
administrator lifts enforcement. Off for every existing account.
"""

import sqlite3

pg_compatible = True


def _upgrade_sqlite(conn):
    columns = {row[1] for row in conn.execute("PRAGMA table_info(users)")}
    if 'webauthn_2fa' not in columns:
        conn.execute(
            "ALTER TABLE users ADD COLUMN webauthn_2fa BOOLEAN NOT NULL DEFAULT 0")
    conn.commit()


def _upgrade_pg(conn):
    from sqlalchemy import text

    conn.execute(text(
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS "
        "webauthn_2fa BOOLEAN NOT NULL DEFAULT FALSE"))


def upgrade(conn):
    if isinstance(conn, sqlite3.Connection):
        _upgrade_sqlite(conn)
    else:
        _upgrade_pg(conn)


def downgrade(conn):
    # Kept: older versions ignore the column.
    pass
