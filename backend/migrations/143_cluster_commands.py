"""Migration 143: HA cluster commands and the last one each node applied.

``cluster_commands`` carries a reload or restart from the node where a setting
changed to every node (``node_id`` set: that node only); ``cluster_nodes.command_seen``
is the last command id a node applied. Created on SQLite too, where nothing writes them.
"""
import logging
import sqlite3

logger = logging.getLogger(__name__)
pg_compatible = True

NODES = 'cluster_nodes'
COMMANDS_DDL = ("CREATE TABLE IF NOT EXISTS cluster_commands ("
                "id {serial} PRIMARY KEY, kind VARCHAR(64) NOT NULL, payload TEXT, "
                "created_at TIMESTAMP NOT NULL, created_by VARCHAR(255), node_id VARCHAR(255))")
COMMANDS_INDEX = ("CREATE INDEX IF NOT EXISTS ix_cluster_commands_created_at "
                  "ON cluster_commands (created_at)")
SEEN_COLUMN = f"ALTER TABLE {NODES} ADD COLUMN command_seen INTEGER"


def _upgrade_sqlite(conn):
    conn.execute(COMMANDS_DDL.format(serial='INTEGER'))
    conn.execute(COMMANDS_INDEX)
    if conn.execute("SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?",
                    (NODES,)).fetchone() is not None:
        if 'command_seen' not in {row[1] for row in conn.execute(f"PRAGMA table_info({NODES})")}:
            conn.execute(SEEN_COLUMN)
    conn.commit()
    logger.info("[143] cluster_commands, cluster_nodes.command_seen (SQLite)")


def _upgrade_pg(conn):
    from sqlalchemy import inspect, text

    conn.execute(text(COMMANDS_DDL.format(serial='SERIAL')))
    conn.execute(text(COMMANDS_INDEX))
    inspector = inspect(conn)
    if NODES in inspector.get_table_names():
        if 'command_seen' not in {c['name'] for c in inspector.get_columns(NODES)}:
            conn.execute(text(SEEN_COLUMN))
    logger.info("[143] cluster_commands, cluster_nodes.command_seen (PostgreSQL)")


def upgrade(conn):
    if isinstance(conn, sqlite3.Connection):
        _upgrade_sqlite(conn)
    else:
        _upgrade_pg(conn)


def downgrade(conn):
    """No downgrade: the table and column are harmless when unused."""
    pass
