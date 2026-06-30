"""Migration 047: link AcmeClientOrder rows to their external CA account.

Adds ``acme_client_orders.acme_client_account_id`` — a foreign key to
``acme_client_accounts.id`` (the external ACME CA: Let's Encrypt, Actalis,
ZeroSSL...). This lets each order remember which CA issued it so renewals
target the same authority instead of re-resolving to the global default.

Distinct from the pre-existing ``account_id`` column, which references the
*local* proxy ``acme_accounts`` table.

Backfill strategy (best-effort, never fatal):
  1. match the order's ``environment`` to the Let's Encrypt staging/production
     account when one exists;
  2. otherwise fall back to the ``is_default`` account.

Dual-backend (SQLite + PostgreSQL).
"""
import logging
import sqlite3

logger = logging.getLogger(__name__)
pg_compatible = True

LE_STAGING = "https://acme-staging-v02.api.letsencrypt.org/directory"
LE_PRODUCTION = "https://acme-v02.api.letsencrypt.org/directory"


# -------- SQLite --------

def _column_exists_sqlite(conn, table, column):
    cur = conn.execute(f"PRAGMA table_info({table})")
    return any(row[1] == column for row in cur.fetchall())


def _account_id_for_url_sqlite(conn, url):
    cur = conn.execute(
        "SELECT id FROM acme_client_accounts WHERE directory_url = ?", (url,)
    )
    row = cur.fetchone()
    return row[0] if row else None


def _default_account_id_sqlite(conn):
    cur = conn.execute(
        "SELECT id FROM acme_client_accounts WHERE is_default = 1 LIMIT 1"
    )
    row = cur.fetchone()
    return row[0] if row else None


def _upgrade_sqlite(conn):
    cur = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' "
        "AND name IN ('acme_client_orders', 'acme_client_accounts')"
    )
    tables = {row[0] for row in cur.fetchall()}
    if 'acme_client_orders' not in tables:
        logger.info("[047] acme_client_orders absent, skipping")
        return

    if not _column_exists_sqlite(conn, 'acme_client_orders', 'acme_client_account_id'):
        conn.execute(
            "ALTER TABLE acme_client_orders ADD COLUMN acme_client_account_id INTEGER"
        )
        logger.info("[047] added acme_client_orders.acme_client_account_id")

    conn.execute(
        "CREATE INDEX IF NOT EXISTS ix_acme_client_orders_ca_account_id "
        "ON acme_client_orders(acme_client_account_id)"
    )

    if 'acme_client_accounts' in tables:
        staging_id = _account_id_for_url_sqlite(conn, LE_STAGING)
        production_id = _account_id_for_url_sqlite(conn, LE_PRODUCTION)
        default_id = _default_account_id_sqlite(conn)

        if staging_id is not None:
            conn.execute(
                "UPDATE acme_client_orders SET acme_client_account_id = ? "
                "WHERE acme_client_account_id IS NULL AND environment = 'staging'",
                (staging_id,),
            )
        if production_id is not None:
            conn.execute(
                "UPDATE acme_client_orders SET acme_client_account_id = ? "
                "WHERE acme_client_account_id IS NULL AND environment = 'production'",
                (production_id,),
            )
        # Custom CA: orders whose environment is neither staging nor production
        # were issued by the configured custom directory (Actalis, ZeroSSL...).
        # Link them to that account BEFORE the generic default fallback so an
        # Actalis order is not silently re-pointed at the Let's Encrypt default.
        custom_id = None
        try:
            row = conn.execute(
                "SELECT value FROM system_config WHERE key = 'acme.client.directory_url'"
            ).fetchone()
            custom_url = row[0] if row and row[0] else None
            if custom_url and custom_url not in (LE_STAGING, LE_PRODUCTION):
                custom_id = _account_id_for_url_sqlite(conn, custom_url)
        except sqlite3.OperationalError:
            custom_id = None  # system_config absent
        if custom_id is not None:
            conn.execute(
                "UPDATE acme_client_orders SET acme_client_account_id = ? "
                "WHERE acme_client_account_id IS NULL "
                "AND environment NOT IN ('staging', 'production')",
                (custom_id,),
            )
        if default_id is not None:
            conn.execute(
                "UPDATE acme_client_orders SET acme_client_account_id = ? "
                "WHERE acme_client_account_id IS NULL",
                (default_id,),
            )

    conn.commit()
    logger.info("[047] ACME client order CA-account link complete (SQLite)")


# -------- PostgreSQL --------

def _account_id_for_url_pg(conn, url):
    from sqlalchemy import text
    row = conn.execute(
        text("SELECT id FROM acme_client_accounts WHERE directory_url = :u"),
        {"u": url},
    ).fetchone()
    return row[0] if row else None


def _default_account_id_pg(conn):
    from sqlalchemy import text
    row = conn.execute(
        text("SELECT id FROM acme_client_accounts WHERE is_default = TRUE LIMIT 1")
    ).fetchone()
    return row[0] if row else None


def _upgrade_pg(conn):
    from sqlalchemy import inspect, text

    insp = inspect(conn)
    existing = set(insp.get_table_names())
    if 'acme_client_orders' not in existing:
        logger.info("[047] acme_client_orders absent, skipping")
        return

    cols = {c['name'] for c in insp.get_columns('acme_client_orders')}
    if 'acme_client_account_id' not in cols:
        conn.execute(text(
            "ALTER TABLE acme_client_orders ADD COLUMN acme_client_account_id INTEGER"
        ))
        logger.info("[047] added acme_client_orders.acme_client_account_id")

    conn.execute(text(
        "CREATE INDEX IF NOT EXISTS ix_acme_client_orders_ca_account_id "
        "ON acme_client_orders(acme_client_account_id)"
    ))

    if 'acme_client_accounts' in existing:
        staging_id = _account_id_for_url_pg(conn, LE_STAGING)
        production_id = _account_id_for_url_pg(conn, LE_PRODUCTION)
        default_id = _default_account_id_pg(conn)

        if staging_id is not None:
            conn.execute(
                text("UPDATE acme_client_orders SET acme_client_account_id = :a "
                     "WHERE acme_client_account_id IS NULL AND environment = 'staging'"),
                {"a": staging_id},
            )
        if production_id is not None:
            conn.execute(
                text("UPDATE acme_client_orders SET acme_client_account_id = :a "
                     "WHERE acme_client_account_id IS NULL AND environment = 'production'"),
                {"a": production_id},
            )
        # Custom CA orders (Actalis, ZeroSSL...) → configured custom directory
        # account, before the generic default fallback.
        custom_id = None
        if 'system_config' in existing:
            row = conn.execute(text(
                "SELECT value FROM system_config WHERE key = 'acme.client.directory_url'"
            )).fetchone()
            custom_url = row[0] if row and row[0] else None
            if custom_url and custom_url not in (LE_STAGING, LE_PRODUCTION):
                custom_id = _account_id_for_url_pg(conn, custom_url)
        if custom_id is not None:
            conn.execute(
                text("UPDATE acme_client_orders SET acme_client_account_id = :a "
                     "WHERE acme_client_account_id IS NULL "
                     "AND environment NOT IN ('staging', 'production')"),
                {"a": custom_id},
            )
        if default_id is not None:
            conn.execute(
                text("UPDATE acme_client_orders SET acme_client_account_id = :a "
                     "WHERE acme_client_account_id IS NULL"),
                {"a": default_id},
            )

    logger.info("[047] ACME client order CA-account link complete (PostgreSQL)")


def upgrade(conn):
    if isinstance(conn, sqlite3.Connection):
        _upgrade_sqlite(conn)
    else:
        _upgrade_pg(conn)


def downgrade(conn):
    """SQLite cannot DROP COLUMN cleanly; left as no-op (parity with 021)."""
    pass
