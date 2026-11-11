"""Migration 154: cluster_nodes.kek_fingerprint, the KEK fingerprint each node publishes.

A node whose fingerprint differs from a live peer's refuses to start (HA).
"""
import logging
import sqlite3

logger = logging.getLogger(__name__)
pg_compatible = True

NODES = 'cluster_nodes'
COLUMN = 'kek_fingerprint'


def upgrade(conn):
    if isinstance(conn, sqlite3.Connection):
        if conn.execute("SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?",
                        (NODES,)).fetchone() is not None:
            have = {row[1] for row in conn.execute(f"PRAGMA table_info({NODES})")}
            if COLUMN not in have:
                conn.execute(f"ALTER TABLE {NODES} ADD COLUMN {COLUMN} VARCHAR(16)")
        conn.commit()
        logger.info("[154] cluster_nodes.kek_fingerprint (SQLite)")
        return
    from sqlalchemy import inspect, text
    inspector = inspect(conn)
    if NODES in inspector.get_table_names():
        if COLUMN not in {c['name'] for c in inspector.get_columns(NODES)}:
            conn.execute(text(f"ALTER TABLE {NODES} ADD COLUMN {COLUMN} VARCHAR(16)"))
    logger.info("[154] cluster_nodes.kek_fingerprint (PostgreSQL)")


def downgrade(conn):
    """No downgrade: the column is harmless when unused."""
    pass
