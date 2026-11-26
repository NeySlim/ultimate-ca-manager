"""Upgrade step 179: the KRL each SSH CA publishes (issue #451).

``ssh_krls`` holds one row per SSH CA, read by every node: the public KRL keeps its version
until the revocations change. Created on both backends; idempotent.
"""
import logging
import sqlite3

logger = logging.getLogger(__name__)
pg_compatible = True

DDL = ("CREATE TABLE IF NOT EXISTS ssh_krls ("
       "ssh_ca_id INTEGER NOT NULL PRIMARY KEY REFERENCES ssh_cas (id) ON DELETE CASCADE, "
       "version BIGINT NOT NULL, digest VARCHAR(64) NOT NULL, data {blob} NOT NULL, "
       "updated_at {timestamp} NOT NULL)")


def upgrade(conn):
    if isinstance(conn, sqlite3.Connection):
        conn.execute(DDL.format(blob='BLOB', timestamp='DATETIME'))
        conn.commit()
        logger.info("[179] ssh_krls (SQLite)")
        return
    from sqlalchemy import text
    conn.execute(text(DDL.format(blob='BYTEA', timestamp='TIMESTAMP WITHOUT TIME ZONE')))
    logger.info("[179] ssh_krls (PostgreSQL)")


def downgrade(conn):
    """No downgrade: an unused table is harmless."""
    pass
