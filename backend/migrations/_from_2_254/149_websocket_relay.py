"""Upgrade step 149: websocket_relay, the WebSocket events of the scheduler process.

Without a message queue the scheduler process appends its events here and every web
worker emits the rows newer than its own cursor. Ids are never reused (AUTOINCREMENT on
SQLite, a sequence on PostgreSQL): a purge that empties the table keeps the cursors valid.
"""
import logging
import sqlite3

logger = logging.getLogger(__name__)
pg_compatible = True

TABLE_DDL = ("CREATE TABLE IF NOT EXISTS websocket_relay ("
             "id {serial}, created_at TIMESTAMP NOT NULL, "
             "room VARCHAR(128) NOT NULL, payload TEXT NOT NULL)")
INDEX = ("CREATE INDEX IF NOT EXISTS ix_websocket_relay_created_at "
         "ON websocket_relay (created_at)")


def upgrade(conn):
    if isinstance(conn, sqlite3.Connection):
        conn.execute(TABLE_DDL.format(serial='INTEGER PRIMARY KEY AUTOINCREMENT'))
        conn.execute(INDEX)
        conn.commit()
        logger.info("[149] websocket_relay (SQLite)")
        return
    from sqlalchemy import text
    conn.execute(text(TABLE_DDL.format(serial='BIGSERIAL PRIMARY KEY')))
    conn.execute(text(INDEX))
    logger.info("[149] websocket_relay (PostgreSQL)")


def downgrade(conn):
    """No downgrade: the table is harmless when unused."""
    pass
