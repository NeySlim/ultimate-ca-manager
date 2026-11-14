"""Upgrade step 141: HA node registry and cross-node scheduler requests.

``cluster_nodes`` holds one row per node, refreshed by its scheduler process, with the
fingerprint of its key-encryption key (never the key);
``scheduler_requests`` carries "run now" from any node to the leader;
``discovery_scan_runs.node_id`` names the node whose process runs a scan;
``cluster_nodes.package_family`` is the package a rolling update gives the node.
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
             "is_leader BOOLEAN NOT NULL DEFAULT {false}, version VARCHAR(32), pid INTEGER, "
             "package_family VARCHAR(32), kek_fingerprint VARCHAR(16))")
# Columns added to this migration after it first ran on development databases
LATE_COLUMNS = (('package_family', 'VARCHAR(32)'), ('kek_fingerprint', 'VARCHAR(16)'))
LATE_COLUMN = "ALTER TABLE cluster_nodes ADD COLUMN {name} {type}"
REQUESTS_DDL = ("CREATE TABLE IF NOT EXISTS scheduler_requests ("
                "id {serial} PRIMARY KEY, task_name VARCHAR(100) NOT NULL, "
                "requested_at TIMESTAMP NOT NULL, requested_by VARCHAR(255), taken_at TIMESTAMP)")
REQUESTS_INDEX = ("CREATE INDEX IF NOT EXISTS ix_scheduler_requests_taken_at "
                  "ON scheduler_requests (taken_at)")
NODE_COLUMN = f"ALTER TABLE {RUNS} ADD COLUMN node_id VARCHAR(255)"


def _upgrade_sqlite(conn):
    conn.execute(NODES_DDL.format(false='0'))
    present = {row[1] for row in conn.execute("PRAGMA table_info(cluster_nodes)")}
    for name, kind in LATE_COLUMNS:
        if name not in present:
            conn.execute(LATE_COLUMN.format(name=name, type=kind))
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
    present = {c['name'] for c in inspect(conn).get_columns('cluster_nodes')}
    for name, kind in LATE_COLUMNS:
        if name not in present:
            conn.execute(text(LATE_COLUMN.format(name=name, type=kind)))
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
