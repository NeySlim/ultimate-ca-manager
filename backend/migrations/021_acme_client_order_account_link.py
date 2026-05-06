"""
Migration 021: Link AcmeClientOrder rows to their local AcmeAccount

Background
----------
Prior to v2.128, proxy orders (``acme_client_orders.is_proxy_order = 1``)
only stored ``client_jwk_thumbprint`` — the SHA-256 thumbprint of the
ACME client's JWK. There was no foreign key to the local ``AcmeAccount``
that owns that JWK, so the UI could not show:

  * which account placed each order in the proxy order history;
  * the proxy orders belonging to a given account in the account detail.

See `issue #71 <https://github.com/NeySlim/ultimate-ca-manager/issues/71>`_.

This migration:

  1. Adds nullable ``account_id`` column to ``acme_client_orders``.
  2. Backfills it from ``client_jwk_thumbprint`` by joining
     ``acme_accounts.jwk_thumbprint``.
  3. Creates a non-unique index on the new column.

Multi-backend convention (v2.128+): runs on both SQLite and PostgreSQL.
"""
import logging
import sqlite3

logger = logging.getLogger(__name__)
pg_compatible = True


_BACKFILL_SQL = """
UPDATE acme_client_orders
SET account_id = (
    SELECT acme_accounts.account_id
    FROM acme_accounts
    WHERE acme_accounts.jwk_thumbprint = acme_client_orders.client_jwk_thumbprint
    LIMIT 1
)
WHERE acme_client_orders.account_id IS NULL
  AND acme_client_orders.client_jwk_thumbprint IS NOT NULL
"""


def _column_exists_sqlite(conn, table, column):
    cur = conn.execute(f"PRAGMA table_info({table})")
    return any(row[1] == column for row in cur.fetchall())


def _upgrade_sqlite(conn):
    cur = conn.execute(
        "SELECT name FROM sqlite_master "
        "WHERE type='table' AND name IN ('acme_client_orders', 'acme_accounts')"
    )
    tables = {row[0] for row in cur.fetchall()}
    if 'acme_client_orders' not in tables:
        logger.info("Migration 021: acme_client_orders absent, skipping")
        return

    if not _column_exists_sqlite(conn, 'acme_client_orders', 'account_id'):
        conn.execute(
            "ALTER TABLE acme_client_orders ADD COLUMN account_id VARCHAR(64)"
        )
        logger.info("Migration 021: added acme_client_orders.account_id")

    if 'acme_accounts' in tables:
        conn.execute(_BACKFILL_SQL)

    conn.execute(
        "CREATE INDEX IF NOT EXISTS ix_acme_client_orders_account_id "
        "ON acme_client_orders(account_id)"
    )
    conn.commit()


def _upgrade_pg(conn):
    # Runner passes a Connection (already in transaction) — issue #111.
    from sqlalchemy import inspect, text
    insp = inspect(conn)
    existing = set(insp.get_table_names())
    if 'acme_client_orders' not in existing:
        logger.info("Migration 021: acme_client_orders absent, skipping")
        return

    cols = {c['name'] for c in insp.get_columns('acme_client_orders')}
    if 'account_id' not in cols:
        conn.execute(text(
            "ALTER TABLE acme_client_orders ADD COLUMN account_id VARCHAR(64)"
        ))
        logger.info("Migration 021: added acme_client_orders.account_id")

    if 'acme_accounts' in existing:
        conn.execute(text(_BACKFILL_SQL))

    conn.execute(text(
        "CREATE INDEX IF NOT EXISTS ix_acme_client_orders_account_id "
        "ON acme_client_orders(account_id)"
    ))


def upgrade(conn):
    if isinstance(conn, sqlite3.Connection):
        _upgrade_sqlite(conn)
    else:
        _upgrade_pg(conn)


def downgrade(conn):
    """SQLite cannot DROP COLUMN cleanly; left as no-op for symmetry with 020."""
    pass
