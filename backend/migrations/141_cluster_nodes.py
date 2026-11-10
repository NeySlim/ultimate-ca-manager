"""Migration 141: HA node registry and cross-node scheduler requests.

``cluster_nodes`` holds one row per node, refreshed by its scheduler process;
``scheduler_requests`` carries "run now" from any node to the leader;
``discovery_scan_runs.node_id`` names the node whose process runs a scan.
Created on SQLite too, where nothing writes them outside HA.
"""
import logging
import sqlite3

logger = logging.getLogger(__name__)
pg_compatible = True

RUNS = 'discovery_scan_runs'
NODES_DDL = ("CREATE TABLE IF NOT EXISTS cluster_nodes ("
             "node_id VARCHAR(255) NOT NULL PRIMARY KEY, "
             "started_at TIMESTAMP NOT NULL, heartbeat_at TIMESTAMP NOT NULL, "
             "is_leader BOOLEAN NOT NULL DEFAULT {false}, version VARCHAR(32), pid INTEGER)")
REQUESTS_DDL = ("CREATE TABLE IF NOT EXISTS scheduler_requests ("
                "id {serial} PRIMARY KEY, task_name VARCHAR(100) NOT NULL, "
                "requested_at TIMESTAMP NOT NULL, requested_by VARCHAR(255), taken_at TIMESTAMP)")
REQUESTS_INDEX = ("CREATE INDEX IF NOT EXISTS ix_scheduler_requests_taken_at "
                  "ON scheduler_requests (taken_at)")
NODE_COLUMN = f"ALTER TABLE {RUNS} ADD COLUMN node_id VARCHAR(255)"


def _upgrade_sqlite(conn):
    conn.execute(NODES_DDL.format(false='0'))
    conn.execute(REQUESTS_DDL.format(serial='INTEGER'))
    conn.execute(REQUESTS_INDEX)
    if conn.execute("SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?",
                    (RUNS,)).fetchone() is not None:
        if 'node_id' not in {row[1] for row in conn.execute(f"PRAGMA table_info({RUNS})")}:
            conn.execute(NODE_COLUMN)
    conn.commit()
    logger.info("[141] cluster_nodes, scheduler_requests, discovery_scan_runs.node_id (SQLite)")


def _upgrade_pg(conn):
    from sqlalchemy import inspect, text

    conn.execute(text(NODES_DDL.format(false='FALSE')))
    conn.execute(text(REQUESTS_DDL.format(serial='SERIAL')))
    conn.execute(text(REQUESTS_INDEX))
    inspector = inspect(conn)
    if RUNS in inspector.get_table_names():
        if 'node_id' not in {c['name'] for c in inspector.get_columns(RUNS)}:
            conn.execute(text(NODE_COLUMN))
    logger.info("[141] cluster_nodes, scheduler_requests, discovery_scan_runs.node_id (PostgreSQL)")


def upgrade(conn):
    if isinstance(conn, sqlite3.Connection):
        _upgrade_sqlite(conn)
    else:
        _upgrade_pg(conn)


def downgrade(conn):
    """No downgrade: the tables and column are harmless when unused."""
    pass
