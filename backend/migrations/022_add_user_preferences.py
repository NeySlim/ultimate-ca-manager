"""
Migration 022: Add ``preferences`` column to the ``users`` table

Background
----------
User preferences (language, theme, density, etc.) were previously stored
client-side only in ``localStorage``. As a result, every login from a
fresh browser reverted to the browser's regional language and the
default theme.

See `issue #73 <https://github.com/NeySlim/ultimate-ca-manager/issues/73>`_.

This migration adds a nullable ``preferences`` TEXT column on the
``users`` table that stores a JSON-encoded preference object. The
column is nullable; an absent / empty value means "no server-side
override, fall back to client defaults".

Multi-backend convention (v2.128+): runs on both SQLite and PostgreSQL.
"""
import logging
import sqlite3

logger = logging.getLogger(__name__)
pg_compatible = True


def _column_exists_sqlite(conn, table, column):
    cur = conn.execute(f"PRAGMA table_info({table})")
    return any(row[1] == column for row in cur.fetchall())


def _upgrade_sqlite(conn):
    cur = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='users'"
    )
    if not cur.fetchone():
        logger.info("Migration 022: users table absent, skipping")
        return

    if not _column_exists_sqlite(conn, 'users', 'preferences'):
        conn.execute("ALTER TABLE users ADD COLUMN preferences TEXT")
        logger.info("Migration 022: added users.preferences")

    conn.commit()


def _upgrade_pg(engine):
    from sqlalchemy import inspect, text
    insp = inspect(engine)
    if 'users' not in set(insp.get_table_names()):
        logger.info("Migration 022: users table absent, skipping")
        return

    cols = {c['name'] for c in insp.get_columns('users')}
    if 'preferences' not in cols:
        with engine.begin() as conn:
            conn.execute(text("ALTER TABLE users ADD COLUMN preferences TEXT"))
            logger.info("Migration 022: added users.preferences")


def upgrade(conn):
    if isinstance(conn, sqlite3.Connection):
        _upgrade_sqlite(conn)
    else:
        _upgrade_pg(conn)


def downgrade(conn):
    """SQLite cannot DROP COLUMN cleanly; left as no-op."""
    pass
