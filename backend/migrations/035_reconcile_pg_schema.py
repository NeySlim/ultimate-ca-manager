"""Migration 035: reconcile schema for installs that silently skipped 031-034.

Issue #115: migrations 031, 032, 033, 034 shipped without `pg_compatible=True`,
so the runner silently marked them applied on PostgreSQL without executing
them — leaving the schema out of sync with the models. Additionally,
migration 032 referenced a non-existent table name (`cas` instead of
`certificate_authorities`), so it was effectively a no-op on SQLite too.

This migration is fully idempotent on both backends: every operation is
guarded by an existence check. It is safe to run on:
  * Fresh PG installs (no-op, all schema already created by create_all)
  * PG installs upgraded from <2.155 that have stale 031-034 rows
  * SQLite installs that had 032 silently no-op

Dual-backend (SQLite + PostgreSQL).
"""
import logging
import sqlite3

logger = logging.getLogger(__name__)
pg_compatible = True


# -------------------- SQLite path --------------------

def _table_exists_sqlite(conn, name):
    cur = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,)
    )
    return cur.fetchone() is not None


def _columns_sqlite(conn, table):
    cur = conn.execute(f"PRAGMA table_info({table})")
    return {row[1] for row in cur.fetchall()}


def _upgrade_sqlite(conn):
    # 1) Heal the 032 table-name bug: create the unique index on the real table.
    if _table_exists_sqlite(conn, "certificate_authorities"):
        # Check for duplicates before creating the unique index.
        cur = conn.execute(
            "SELECT hsm_key_id, COUNT(*) FROM certificate_authorities "
            "WHERE hsm_key_id IS NOT NULL "
            "GROUP BY hsm_key_id HAVING COUNT(*) > 1"
        )
        dupes = cur.fetchall()
        if dupes:
            for hsm_key_id, count in dupes:
                logger.error(
                    f"[035] HSM key {hsm_key_id} bound to {count} CAs — manual cleanup required"
                )
            raise RuntimeError(
                "Migration 035 aborted: duplicate hsm_key_id in certificate_authorities. "
                "Reconcile manually before retrying."
            )
        conn.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS uq_ca_hsm_key_id "
            "ON certificate_authorities(hsm_key_id) WHERE hsm_key_id IS NOT NULL"
        )
        logger.info("[035] ensured uq_ca_hsm_key_id on certificate_authorities (SQLite)")

    # 2) On SQLite, 031/033/034 either ran correctly or this is a fresh
    #    install where create_all() already built the schema. Nothing else
    #    to heal here.
    conn.commit()


# -------------------- PostgreSQL path --------------------

def _upgrade_pg(conn):
    from sqlalchemy import inspect, text

    insp = inspect(conn)
    tables = set(insp.get_table_names())

    # 1) acme_client_accounts (migration 031)
    if "acme_client_accounts" not in tables:
        conn.execute(text("""
            CREATE TABLE acme_client_accounts (
                id SERIAL PRIMARY KEY,
                directory_url VARCHAR(500) NOT NULL UNIQUE,
                label VARCHAR(100) NOT NULL,
                email VARCHAR(255) NOT NULL,
                account_url VARCHAR(500),
                account_key TEXT,
                account_key_algorithm VARCHAR(20) NOT NULL DEFAULT 'ES256',
                eab_kid VARCHAR(255),
                eab_hmac_key TEXT,
                is_default BOOLEAN NOT NULL DEFAULT FALSE,
                created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
        """))
        conn.execute(text(
            "CREATE INDEX IF NOT EXISTS idx_acme_client_accounts_default "
            "ON acme_client_accounts(is_default)"
        ))
        logger.info("[035] created acme_client_accounts (PostgreSQL)")
        # Refresh after CREATE
        insp = inspect(conn)
        tables = set(insp.get_table_names())

    # 2) Unique partial index on certificate_authorities.hsm_key_id (migration 032)
    if "certificate_authorities" in tables:
        # Check for duplicates first
        dupes = conn.execute(text(
            "SELECT hsm_key_id, COUNT(*) FROM certificate_authorities "
            "WHERE hsm_key_id IS NOT NULL "
            "GROUP BY hsm_key_id HAVING COUNT(*) > 1"
        )).fetchall()
        if dupes:
            for row in dupes:
                logger.error(
                    f"[035] HSM key {row[0]} bound to {row[1]} CAs — manual cleanup required"
                )
            raise RuntimeError(
                "Migration 035 aborted: duplicate hsm_key_id in certificate_authorities. "
                "Reconcile manually before retrying."
            )
        conn.execute(text(
            "CREATE UNIQUE INDEX IF NOT EXISTS uq_ca_hsm_key_id "
            "ON certificate_authorities(hsm_key_id) WHERE hsm_key_id IS NOT NULL"
        ))
        logger.info("[035] ensured uq_ca_hsm_key_id on certificate_authorities (PostgreSQL)")

        # 4) certificate_authorities offline columns (migration 034)
        existing = {c["name"] for c in insp.get_columns("certificate_authorities")}
        for name, ddl in (
            ("offline", "BOOLEAN DEFAULT FALSE"),
            ("offline_reason", "TEXT"),
            ("offline_mode", "TEXT"),
        ):
            if name not in existing:
                conn.execute(text(f"ALTER TABLE certificate_authorities ADD COLUMN {name} {ddl}"))
                logger.info(f"[035] added certificate_authorities.{name} (PostgreSQL)")

    # 3) acme_authorizations.order_id nullable (migration 033)
    if "acme_authorizations" in tables:
        cols = {c["name"]: c for c in insp.get_columns("acme_authorizations")}
        if "order_id" in cols and not cols["order_id"].get("nullable", True):
            conn.execute(text(
                "ALTER TABLE acme_authorizations ALTER COLUMN order_id DROP NOT NULL"
            ))
            logger.info("[035] made acme_authorizations.order_id nullable (PostgreSQL)")


def upgrade(conn):
    if isinstance(conn, sqlite3.Connection):
        _upgrade_sqlite(conn)
    else:
        _upgrade_pg(conn)


def downgrade(conn):
    """No downgrade — reconcile is a forward-only heal."""
    pass
