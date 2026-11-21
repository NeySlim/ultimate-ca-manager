"""Upgrade step 161: the HA cluster maintenance and each node's acknowledgement of it.

``cluster_maintenance`` holds at most one row: while its lease runs, no node writes
(a restore, or an administrator around a restore by PostgreSQL's own tools).
``cluster_nodes.maintenance_ack``/``maintenance_ack_scheduler`` carry the token each
process of a node last refused writes for. Created on SQLite too, where nothing writes them.
"""
import logging
import sqlite3

logger = logging.getLogger(__name__)
pg_compatible = True

NODES = 'cluster_nodes'
DDL = ("CREATE TABLE IF NOT EXISTS cluster_maintenance ("
       "id INTEGER NOT NULL PRIMARY KEY, token VARCHAR(36) NOT NULL, reason VARCHAR(16) NOT NULL, "
       "phase VARCHAR(16) NOT NULL, started_at {timestamp} NOT NULL, expires_at {timestamp} NOT NULL, "
       "restored_at {timestamp}, node_id VARCHAR(255), actor VARCHAR(255))")
NODE_COLUMNS = ('maintenance_ack', 'maintenance_ack_scheduler')
ADD_COLUMN = "ALTER TABLE cluster_nodes ADD COLUMN {name} VARCHAR(36)"


def upgrade(conn):
    if isinstance(conn, sqlite3.Connection):
        conn.execute(DDL.format(timestamp='DATETIME'))
        if conn.execute("SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?",
                        (NODES,)).fetchone() is not None:
            have = {row[1] for row in conn.execute(f"PRAGMA table_info({NODES})")}
            for name in NODE_COLUMNS:
                if name not in have:
                    conn.execute(ADD_COLUMN.format(name=name))
        conn.commit()
        logger.info("[161] cluster_maintenance, cluster_nodes.maintenance_ack (SQLite)")
        return
    from sqlalchemy import inspect, text
    conn.execute(text(DDL.format(timestamp='TIMESTAMP WITHOUT TIME ZONE')))
    inspector = inspect(conn)
    if NODES in inspector.get_table_names():
        have = {c['name'] for c in inspector.get_columns(NODES)}
        for name in NODE_COLUMNS:
            if name not in have:
                conn.execute(text(ADD_COLUMN.format(name=name)))
    logger.info("[161] cluster_maintenance, cluster_nodes.maintenance_ack (PostgreSQL)")


def downgrade(conn):
    """No downgrade: an unused table and columns are harmless."""
    pass
