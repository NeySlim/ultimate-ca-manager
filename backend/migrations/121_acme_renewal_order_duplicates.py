"""Migration 121: stop the orders a past renewal left behind from renewing too.

Renewing an order opens a second one and leaves both on the schedule, so every cycle
doubled them. The second one is recognised by holding the certificate and order URL
its older order took over. Multi-backend convention: runs on SQLite and PostgreSQL.
"""
import logging
import sqlite3

logger = logging.getLogger(__name__)
pg_compatible = True

_STMT = """
    UPDATE acme_client_orders SET renewal_enabled = FALSE
    WHERE renewal_enabled = TRUE AND EXISTS (
        SELECT 1 FROM acme_client_orders older
        WHERE older.id < acme_client_orders.id
          AND older.certificate_id = acme_client_orders.certificate_id
          AND older.order_url = acme_client_orders.order_url
          AND older.renewal_enabled = TRUE
          AND older.status = 'issued'
          AND older.last_renewal_at IS NOT NULL
    )
"""


def upgrade(conn):
    if isinstance(conn, sqlite3.Connection):
        changed = conn.execute(_STMT).rowcount
        conn.commit()
    else:
        from sqlalchemy import text
        changed = conn.execute(text(_STMT)).rowcount
    logger.info("Migration 121: %s renewal order(s) taken off the schedule", changed)


def downgrade(conn):
    """Nothing to restore: these orders only ever renewed by accident."""
