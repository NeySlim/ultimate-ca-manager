"""Upgrade step 159: second-factor and WebAuthn lockout counters, shared by every node.

``second_factor_failures`` holds one row per locked-out target, purged once expired.
Created on SQLite too: a single node keeps its lockouts across a restart.
"""
import logging
import sqlite3

logger = logging.getLogger(__name__)
pg_compatible = True

DDL = ("CREATE TABLE IF NOT EXISTS second_factor_failures ("
       "kind VARCHAR(16) NOT NULL, target VARCHAR(255) NOT NULL, failures INTEGER NOT NULL, "
       "locked_until TIMESTAMP, updated_at TIMESTAMP NOT NULL, PRIMARY KEY (kind, target))")


def upgrade(conn):
    if isinstance(conn, sqlite3.Connection):
        conn.execute(DDL)
        conn.commit()
        logger.info("[159] second_factor_failures (SQLite)")
        return
    from sqlalchemy import text
    conn.execute(text(DDL))
    logger.info("[159] second_factor_failures (PostgreSQL)")


def downgrade(conn):
    """No downgrade: an unused table is harmless."""
    pass
