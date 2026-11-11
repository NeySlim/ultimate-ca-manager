"""Migration 152: files every node writes from the database (Kerberos keytab, HTTPS pair).

``shared_files`` holds one row per file, its bytes under the master key like a
certificate's private key. Created on SQLite too: a single node restores them as well.
"""
import logging
import sqlite3

logger = logging.getLogger(__name__)
pg_compatible = True

DDL = ("CREATE TABLE IF NOT EXISTS shared_files ("
       "name VARCHAR(64) NOT NULL PRIMARY KEY, content TEXT NOT NULL, "
       "updated_at TIMESTAMP, updated_by VARCHAR(255))")


def upgrade(conn):
    if isinstance(conn, sqlite3.Connection):
        conn.execute(DDL)
        conn.commit()
        logger.info("[152] shared_files (SQLite)")
        return
    from sqlalchemy import text
    conn.execute(text(DDL))
    logger.info("[152] shared_files (PostgreSQL)")


def downgrade(conn):
    """No downgrade: an unused table is harmless."""
    pass
