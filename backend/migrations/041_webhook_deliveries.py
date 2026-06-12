"""Migration 041: durable webhook delivery queue.

Adds the ``webhook_deliveries`` table backing asynchronous, retried webhook
delivery (one row per event-per-endpoint) with per-endpoint delivery history.
"""
import logging
import sqlite3

logger = logging.getLogger(__name__)
pg_compatible = True


_SQLITE_DDL = """
CREATE TABLE IF NOT EXISTS webhook_deliveries (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    endpoint_id INTEGER NOT NULL,
    event_type VARCHAR(64) NOT NULL,
    payload TEXT NOT NULL,
    event_timestamp VARCHAR(40) NOT NULL,
    status VARCHAR(16) NOT NULL DEFAULT 'pending',
    attempts INTEGER NOT NULL DEFAULT 0,
    max_attempts INTEGER NOT NULL DEFAULT 5,
    next_attempt_at DATETIME NOT NULL,
    last_response_code INTEGER,
    last_error TEXT,
    created_at DATETIME NOT NULL,
    delivered_at DATETIME
)
"""

_PG_DDL = """
CREATE TABLE IF NOT EXISTS webhook_deliveries (
    id SERIAL PRIMARY KEY,
    endpoint_id INTEGER NOT NULL,
    event_type VARCHAR(64) NOT NULL,
    payload TEXT NOT NULL,
    event_timestamp VARCHAR(40) NOT NULL,
    status VARCHAR(16) NOT NULL DEFAULT 'pending',
    attempts INTEGER NOT NULL DEFAULT 0,
    max_attempts INTEGER NOT NULL DEFAULT 5,
    next_attempt_at TIMESTAMP NOT NULL,
    last_response_code INTEGER,
    last_error TEXT,
    created_at TIMESTAMP NOT NULL,
    delivered_at TIMESTAMP
)
"""


def _upgrade_sqlite(conn):
    conn.execute(_SQLITE_DDL)
    conn.execute("CREATE INDEX IF NOT EXISTS ix_webhook_deliveries_status ON webhook_deliveries(status)")
    conn.execute("CREATE INDEX IF NOT EXISTS ix_webhook_deliveries_next ON webhook_deliveries(next_attempt_at)")
    conn.execute("CREATE INDEX IF NOT EXISTS ix_webhook_deliveries_endpoint ON webhook_deliveries(endpoint_id)")
    conn.commit()
    logger.info("[041] created webhook_deliveries (SQLite)")


def _upgrade_pg(conn):
    from sqlalchemy import text
    conn.execute(text(_PG_DDL))
    conn.execute(text("CREATE INDEX IF NOT EXISTS ix_webhook_deliveries_status ON webhook_deliveries(status)"))
    conn.execute(text("CREATE INDEX IF NOT EXISTS ix_webhook_deliveries_next ON webhook_deliveries(next_attempt_at)"))
    conn.execute(text("CREATE INDEX IF NOT EXISTS ix_webhook_deliveries_endpoint ON webhook_deliveries(endpoint_id)"))
    logger.info("[041] created webhook_deliveries (PostgreSQL)")


def upgrade(conn):
    if isinstance(conn, sqlite3.Connection):
        _upgrade_sqlite(conn)
    else:
        _upgrade_pg(conn)


def downgrade(conn):
    if isinstance(conn, sqlite3.Connection):
        conn.execute("DROP TABLE IF EXISTS webhook_deliveries")
        conn.commit()
    else:
        from sqlalchemy import text
        conn.execute(text("DROP TABLE IF EXISTS webhook_deliveries"))
