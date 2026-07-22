"""Migration 065: reset stale WebAuthn signature counters.

Before v2.200 the stored counter was written as ``max(new_sign_count,
stored + 1)`` while the library check was disabled. For an authenticator that
reports 0 on every authentication — Apple passkeys, Windows Hello and many
FIDO2 keys do exactly that — the stored value therefore grew by one per login
without ever reflecting anything real.

v2.200 started enforcing the counter against that stored value, which made
those inflated numbers impossible to beat: every affected user was locked out
of their own security key (`Response sign count of 0 was not greater than
current count of N`).

The stored values cannot be told apart from genuine counters, so they are all
reset to 0. The authenticator's real value is recorded again on the next
successful authentication, and clone detection resumes from there — for keys
that actually implement a counter.

Dual-backend (SQLite + PostgreSQL).
"""

import logging
import sqlite3

logger = logging.getLogger(__name__)
pg_compatible = True

_TABLE = 'webauthn_credentials'


def _upgrade_sqlite(conn):
    tables = {
        row[0] for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
    }
    if _TABLE not in tables:
        logger.info('[065] %s absent, skipping (SQLite)', _TABLE)
        return

    cur = conn.execute(f'UPDATE {_TABLE} SET sign_count = 0 WHERE sign_count != 0')
    conn.commit()
    logger.info('[065] reset %s stale WebAuthn sign counter(s) (SQLite)', cur.rowcount)


def _upgrade_pg(conn):
    from sqlalchemy import inspect, text

    inspector = inspect(conn)
    if _TABLE not in set(inspector.get_table_names()):
        logger.info('[065] %s absent, skipping (PostgreSQL)', _TABLE)
        return

    result = conn.execute(text(
        f'UPDATE {_TABLE} SET sign_count = 0 WHERE sign_count != 0'
    ))
    logger.info(
        '[065] reset %s stale WebAuthn sign counter(s) (PostgreSQL)',
        result.rowcount,
    )


def upgrade(conn):
    if isinstance(conn, sqlite3.Connection):
        _upgrade_sqlite(conn)
    else:
        _upgrade_pg(conn)


def downgrade(conn):
    """Counters cannot be restored — and must not be: the previous values were
    the cause of the lockout."""
    pass
