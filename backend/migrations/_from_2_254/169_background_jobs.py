"""Upgrade step 169: the background jobs (backup, restore, audit verification).

``background_jobs`` holds one row per job; the partial unique index keeps one active job per
slot on the whole installation, HA included. Created on SQLite too.
"""
import logging
import sqlite3

logger = logging.getLogger(__name__)
pg_compatible = True

DDL = ("CREATE TABLE IF NOT EXISTS background_jobs ("
       "id VARCHAR(36) NOT NULL PRIMARY KEY, kind VARCHAR(32) NOT NULL, slot VARCHAR(32) NOT NULL, "
       "state VARCHAR(16) NOT NULL, reason VARCHAR(64), node_id VARCHAR(255), executor VARCHAR(255), "
       "requested_by_id INTEGER, requested_by_name VARCHAR(255), requested_ip VARCHAR(64), "
       "params TEXT, secret TEXT, file_name VARCHAR(255), progress_done BIGINT, progress_total BIGINT, "
       "phase VARCHAR(32), cancel_requested BOOLEAN NOT NULL, result TEXT, steps TEXT, "
       "created_at {timestamp} NOT NULL, started_at {timestamp}, finished_at {timestamp}, "
       "lease_expires_at {timestamp})")
INDEXES = (
    "CREATE UNIQUE INDEX IF NOT EXISTS uq_background_jobs_active_slot ON background_jobs (slot) "
    "WHERE state IN ('pending', 'running')",
    "CREATE INDEX IF NOT EXISTS ix_background_jobs_kind_created ON background_jobs (kind, created_at)",
    "CREATE INDEX IF NOT EXISTS ix_background_jobs_state ON background_jobs (state)",
)


def upgrade(conn):
    if isinstance(conn, sqlite3.Connection):
        conn.execute(DDL.format(timestamp='DATETIME'))
        for statement in INDEXES:
            conn.execute(statement)
        conn.commit()
        logger.info("[169] background_jobs (SQLite)")
        return
    from sqlalchemy import text
    conn.execute(text(DDL.format(timestamp='TIMESTAMP WITHOUT TIME ZONE')))
    for statement in INDEXES:
        conn.execute(text(statement))
    logger.info("[169] background_jobs (PostgreSQL)")


def downgrade(conn):
    """No downgrade: an unused table is harmless."""
    pass
