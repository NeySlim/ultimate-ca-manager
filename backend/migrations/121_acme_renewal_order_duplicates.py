"""Migration 121: put the renewal schedule of ACME client orders right.

A status check took orders from issued back to valid, off the schedule: those holding
a live certificate go back, unless a newer order for the names took over (never a proxy
order, whose client renews it). Renewing an order also left the one that fetched the
certificate on the schedule, so every cycle doubled them: it holds nothing of its own,
the certificate and order URL being its older order's, and goes. Multi-backend
convention: runs on SQLite and PostgreSQL.
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
            AND COALESCE(certificates.revoked, FALSE) = FALSE
      )
      AND NOT EXISTS (
          SELECT 1 FROM acme_client_orders newer
          WHERE newer.id > acme_client_orders.id
            AND newer.status = 'issued'
            AND newer.domains = acme_client_orders.domains
            AND newer.environment = acme_client_orders.environment
            AND newer.certificate_id <> acme_client_orders.certificate_id
      )
"""

_DROP_LEFTOVERS = """
    DELETE FROM acme_client_orders
    WHERE status = 'issued'
      AND COALESCE(is_proxy_order, FALSE) = FALSE
      AND EXISTS (
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
        dropped = conn.execute(_DROP_LEFTOVERS).rowcount
        conn.commit()
    else:
        from sqlalchemy import text
        reissued = conn.execute(text(_REISSUE)).rowcount
        dropped = conn.execute(text(_DROP_LEFTOVERS)).rowcount
    logger.info("Migration 121: %s order(s) back on the schedule, %s leftover(s) removed", reissued, dropped)


def downgrade(conn):
    """Nothing to restore: both states only ever came from a bug."""
