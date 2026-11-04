"""Migration 121: put the renewal schedule of ACME client orders right.

A status check took orders from issued back to valid, off the schedule: those holding
a live certificate go back (never a proxy order, whose client renews it). Renewing an
order also left the one that fetched the certificate on the schedule, so every cycle
doubled them: it is recognised by the certificate and order URL its older order took
over. Multi-backend convention: runs on SQLite and PostgreSQL.
"""
import logging
import sqlite3

logger = logging.getLogger(__name__)
pg_compatible = True

_REISSUE = """
    UPDATE acme_client_orders SET status = 'issued'
    WHERE status = 'valid'
      AND COALESCE(is_proxy_order, FALSE) = FALSE
      AND EXISTS (
          SELECT 1 FROM certificates
          WHERE certificates.id = acme_client_orders.certificate_id
            AND certificates.valid_to > CURRENT_TIMESTAMP
      )
"""

_TAKE_OFF = """
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
        reissued = conn.execute(_REISSUE).rowcount
        taken_off = conn.execute(_TAKE_OFF).rowcount
        conn.commit()
    else:
        from sqlalchemy import text
        reissued = conn.execute(text(_REISSUE)).rowcount
        taken_off = conn.execute(text(_TAKE_OFF)).rowcount
    logger.info("Migration 121: %s order(s) back on the schedule, %s taken off", reissued, taken_off)


def downgrade(conn):
    """Nothing to restore: both states only ever came from a bug."""
