"""Migration 069: domain restrictions on ACME EAB credentials.

Adds ``acme_eab_credentials.allowed_domains`` (TEXT, JSON list of patterns,
NULL = unrestricted). Rows that exist when the column is added get
``["*"]`` so their behaviour does not change.

Dual-backend (SQLite + PostgreSQL).
"""
import logging
import sqlite3

logger = logging.getLogger(__name__)
pg_compatible = True

_TABLE = 'acme_eab_credentials'
_COLUMN = 'allowed_domains'
_UNRESTRICTED = '["*"]'


def _upgrade_sqlite(conn):
    tables = {
        row[0] for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'").fetchall()
    }
    if _TABLE not in tables:
        logger.info("069: no %s table, nothing to do (SQLite)", _TABLE)
        return
    cols = {row[1] for row in conn.execute(f"PRAGMA table_info({_TABLE})")}
    if _COLUMN in cols:
        return
    conn.execute(f"ALTER TABLE {_TABLE} ADD COLUMN {_COLUMN} TEXT")
    # Backfill only on the run that adds the column: later NULLs are deliberate.
    conn.execute(f"UPDATE {_TABLE} SET {_COLUMN} = ?", (_UNRESTRICTED,))
    conn.commit()
    logger.info("069: added %s.%s (SQLite)", _TABLE, _COLUMN)


def _upgrade_pg(conn):
    from sqlalchemy import inspect, text

    inspector = inspect(conn)
    if _TABLE not in inspector.get_table_names():
        logger.info("069: no %s table, nothing to do (PostgreSQL)", _TABLE)
        return
    if _COLUMN in {c['name'] for c in inspector.get_columns(_TABLE)}:
        return
    conn.execute(text(f"ALTER TABLE {_TABLE} ADD COLUMN {_COLUMN} TEXT"))
    conn.execute(text(f"UPDATE {_TABLE} SET {_COLUMN} = :v"), {'v': _UNRESTRICTED})
    logger.info("069: added %s.%s (PostgreSQL)", _TABLE, _COLUMN)


def upgrade(conn):
    if isinstance(conn, sqlite3.Connection):
        _upgrade_sqlite(conn)
    else:
        _upgrade_pg(conn)


def downgrade(conn):
    # Added column is harmless if left behind, matching nearby migrations.
    pass
