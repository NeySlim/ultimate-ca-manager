"""Upgrade step 156: common name pattern of a certificate template (WSTEP issuance).

Two columns on certificate_templates: the pattern (NULL, every existing template keeps
its subject) and whether the directory path follows the CN (false).
Idempotent, dual-backend (SQLite + PostgreSQL).
"""
import logging
import sqlite3

logger = logging.getLogger(__name__)
pg_compatible = True

TABLE = 'certificate_templates'
_SQLITE_COLUMNS = (('subject_cn_pattern', 'VARCHAR(255)'),
                   ('subject_cn_keep_path', 'BOOLEAN NOT NULL DEFAULT 0'))
_PG_COLUMNS = (('subject_cn_pattern', 'VARCHAR(255)'),
               ('subject_cn_keep_path', 'BOOLEAN NOT NULL DEFAULT FALSE'))


def _upgrade_sqlite(conn):
    tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    if TABLE not in tables:
        logger.info("156: no certificate_templates table, nothing to do (SQLite)")
        return
    cols = {row[1] for row in conn.execute(f"PRAGMA table_info({TABLE})")}
    for name, sql_type in _SQLITE_COLUMNS:
        if name not in cols:
            conn.execute(f"ALTER TABLE {TABLE} ADD COLUMN {name} {sql_type}")
    conn.commit()
    logger.info("156: certificate_templates carries the common name pattern (SQLite)")


def _upgrade_pg(conn):
    from sqlalchemy import inspect, text
    inspector = inspect(conn)
    if TABLE not in inspector.get_table_names():
        logger.info("156: no certificate_templates table, nothing to do (PostgreSQL)")
        return
    cols = {column['name'] for column in inspector.get_columns(TABLE)}
    for name, sql_type in _PG_COLUMNS:
        if name not in cols:
            conn.execute(text(f"ALTER TABLE {TABLE} ADD COLUMN {name} {sql_type}"))
    logger.info("156: certificate_templates carries the common name pattern (PostgreSQL)")


def upgrade(conn):
    if isinstance(conn, sqlite3.Connection):
        _upgrade_sqlite(conn)
    else:
        _upgrade_pg(conn)


def downgrade(conn):
    # Added columns are harmless if left behind, matching nearby migrations.
    pass
