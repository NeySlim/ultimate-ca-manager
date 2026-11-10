"""Migration 138: the server-side session table of the SQL store.

Same shape as the table Flask-Session 0.8 creates itself (``flask_sessions``):
used on PostgreSQL without Redis, so a session opened on one node is valid on
the others. Created everywhere and left empty where files hold the sessions.
"""
import logging
import sqlite3

logger = logging.getLogger(__name__)
pg_compatible = True

TABLE = 'flask_sessions'
INDEX = 'ix_flask_sessions_expiry'


def _upgrade_sqlite(conn):
    conn.execute(f"CREATE TABLE IF NOT EXISTS {TABLE} (id INTEGER NOT NULL PRIMARY KEY, "
                 "session_id VARCHAR(255) UNIQUE, data BLOB, expiry DATETIME)")
    conn.execute(f"CREATE INDEX IF NOT EXISTS {INDEX} ON {TABLE} (expiry)")
    conn.commit()
    logger.info("[138] flask_sessions (SQLite)")


def _upgrade_pg(conn):
    from sqlalchemy import text

    conn.execute(text(f"CREATE TABLE IF NOT EXISTS {TABLE} (id SERIAL PRIMARY KEY, "
                      "session_id VARCHAR(255) UNIQUE, data BYTEA, expiry TIMESTAMP)"))
    conn.execute(text(f"CREATE INDEX IF NOT EXISTS {INDEX} ON {TABLE} (expiry)"))
    logger.info("[138] flask_sessions (PostgreSQL)")


def upgrade(conn):
    if isinstance(conn, sqlite3.Connection):
        _upgrade_sqlite(conn)
    else:
        _upgrade_pg(conn)


def downgrade(conn):
    """No downgrade: an unused session table is harmless."""
    pass
