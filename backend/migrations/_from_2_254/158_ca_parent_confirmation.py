"""Upgrade step 158: who confirmed a CA's parent by hand, and when.

Two nullable columns on certificate_authorities, NULL on every existing row: no link
was confirmed by hand before this migration.
Idempotent, dual-backend (SQLite + PostgreSQL).
"""
import logging
import sqlite3

logger = logging.getLogger(__name__)
pg_compatible = True

TABLE = 'certificate_authorities'
_SQLITE_COLUMNS = (('parent_confirmed_by', 'VARCHAR(80)'), ('parent_confirmed_at', 'DATETIME'))
_PG_COLUMNS = (('parent_confirmed_by', 'VARCHAR(80)'), ('parent_confirmed_at', 'TIMESTAMP'))


def _upgrade_sqlite(conn):
    tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    if TABLE not in tables:
        logger.info("158: no certificate_authorities table, nothing to do (SQLite)")
        return
    cols = {row[1] for row in conn.execute(f"PRAGMA table_info({TABLE})")}
    for name, sql_type in _SQLITE_COLUMNS:
        if name not in cols:
            conn.execute(f"ALTER TABLE {TABLE} ADD COLUMN {name} {sql_type}")
    conn.commit()
    logger.info("158: certificate_authorities records a parent confirmed by hand (SQLite)")


def _upgrade_pg(conn):
    from sqlalchemy import inspect, text
    inspector = inspect(conn)
    if TABLE not in inspector.get_table_names():
        logger.info("158: no certificate_authorities table, nothing to do (PostgreSQL)")
        return
    cols = {column['name'] for column in inspector.get_columns(TABLE)}
    for name, sql_type in _PG_COLUMNS:
        if name not in cols:
            conn.execute(text(f"ALTER TABLE {TABLE} ADD COLUMN {name} {sql_type}"))
    logger.info("158: certificate_authorities records a parent confirmed by hand (PostgreSQL)")


def upgrade(conn):
    if isinstance(conn, sqlite3.Connection):
        _upgrade_sqlite(conn)
    else:
        _upgrade_pg(conn)


def downgrade(conn):
    # Added columns are harmless if left behind, matching nearby migrations.
    pass
