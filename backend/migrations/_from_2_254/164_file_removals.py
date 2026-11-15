"""Upgrade step 164: the paths a restore removed, which every node deletes from its disk.

``file_removals`` holds one row per path and files generation (services/file_regen_service).
Created on SQLite too: a single node reconciles its files the same way.
"""
import logging
import sqlite3

logger = logging.getLogger(__name__)
pg_compatible = True

DDL = ("CREATE TABLE IF NOT EXISTS file_removals ("
       "id {pk}, generation INTEGER NOT NULL, path VARCHAR(1024) NOT NULL)")
INDEXES = ("CREATE INDEX IF NOT EXISTS ix_file_removals_generation ON file_removals (generation)",
           "CREATE INDEX IF NOT EXISTS ix_file_removals_path ON file_removals (path)")


def upgrade(conn):
    if isinstance(conn, sqlite3.Connection):
        conn.execute(DDL.format(pk='INTEGER NOT NULL PRIMARY KEY'))
        for statement in INDEXES:
            conn.execute(statement)
        conn.commit()
        logger.info("[164] file_removals (SQLite)")
        return
    from sqlalchemy import text
    conn.execute(text(DDL.format(pk='SERIAL PRIMARY KEY')))
    for statement in INDEXES:
        conn.execute(text(statement))
    logger.info("[164] file_removals (PostgreSQL)")


def downgrade(conn):
    """No downgrade: an unused table is harmless."""
    pass
