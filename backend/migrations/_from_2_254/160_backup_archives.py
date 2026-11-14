"""Upgrade step 160: backup_archives and backup_archive_chunks, the HA archive store.

In HA every archive is written to the database in fixed-size chunks, so any node lists
and serves it. Created on SQLite too, where it stays empty (HA runs on PostgreSQL only).
"""
import logging
import sqlite3

logger = logging.getLogger(__name__)
pg_compatible = True

ARCHIVES = ("CREATE TABLE IF NOT EXISTS backup_archives ("
            "id {serial}, filename VARCHAR(128) NOT NULL UNIQUE, "
            "node_id VARCHAR(255) NOT NULL, created_at {timestamp} NOT NULL, "
            "size BIGINT NOT NULL, sha256 VARCHAR(64) NOT NULL, "
            "chunk_size INTEGER NOT NULL, chunk_count INTEGER NOT NULL)")
CHUNKS = ("CREATE TABLE IF NOT EXISTS backup_archive_chunks ("
          "archive_id {bigint} NOT NULL REFERENCES backup_archives (id) ON DELETE CASCADE, "
          "seq INTEGER NOT NULL, data {blob} NOT NULL, PRIMARY KEY (archive_id, seq))")
INDEX = ("CREATE INDEX IF NOT EXISTS ix_backup_archives_created_at "
         "ON backup_archives (created_at)")


def upgrade(conn):
    if isinstance(conn, sqlite3.Connection):
        conn.execute(ARCHIVES.format(serial='INTEGER NOT NULL PRIMARY KEY', timestamp='DATETIME'))
        conn.execute(CHUNKS.format(bigint='INTEGER', blob='BLOB'))
        conn.execute(INDEX)
        conn.commit()
        logger.info("[160] backup_archives (SQLite)")
        return
    from sqlalchemy import text
    conn.execute(text(ARCHIVES.format(serial='BIGSERIAL PRIMARY KEY', timestamp='TIMESTAMP WITHOUT TIME ZONE')))
    conn.execute(text(CHUNKS.format(bigint='BIGINT', blob='BYTEA')))
    conn.execute(text(INDEX))
    logger.info("[160] backup_archives (PostgreSQL)")


def downgrade(conn):
    """No downgrade: the tables are harmless when unused."""
    pass
