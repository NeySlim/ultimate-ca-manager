"""Migration 062: flexible per-CA protocol URL modes and overrides.

Adds:
  protocol_mode — inherit | http_protocol | https_admin | custom
  protocol_base_url_override — CA-level base when mode=custom
  cdp_base_url / ocsp_base_url / aia_base_url — optional per-endpoint bases

Backfills protocol_mode from legacy protocol_http (False → https_admin).
"""

import logging
import sqlite3

logger = logging.getLogger(__name__)
pg_compatible = True

_COLS_SQLITE = [
    ("protocol_mode", "VARCHAR(32) DEFAULT 'inherit'"),
    ("protocol_base_url_override", "VARCHAR(512)"),
    ("cdp_base_url", "VARCHAR(512)"),
    ("ocsp_base_url", "VARCHAR(512)"),
    ("aia_base_url", "VARCHAR(512)"),
]

_COLS_PG = [
    ("protocol_mode", "VARCHAR(32) DEFAULT 'inherit'"),
    ("protocol_base_url_override", "VARCHAR(512)"),
    ("cdp_base_url", "VARCHAR(512)"),
    ("ocsp_base_url", "VARCHAR(512)"),
    ("aia_base_url", "VARCHAR(512)"),
]


def _upgrade_sqlite(conn):
    cur = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' "
        "AND name='certificate_authorities'"
    )
    if not cur.fetchone():
        logger.info("062: certificate_authorities absent, skipping")
        return

    cols = {
        row[1] for row in conn.execute("PRAGMA table_info(certificate_authorities)")
    }
    for name, ddl in _COLS_SQLITE:
        if name in cols:
            continue
        conn.execute(
            f"ALTER TABLE certificate_authorities ADD COLUMN {name} {ddl}"
        )
        logger.info("062: added certificate_authorities.%s (SQLite)", name)

    # Backfill mode from legacy protocol_http
    if "protocol_http" in cols or "protocol_http" in {
        row[1] for row in conn.execute("PRAGMA table_info(certificate_authorities)")
    }:
        conn.execute(
            "UPDATE certificate_authorities SET protocol_mode = 'https_admin' "
            "WHERE protocol_http = 0 AND (protocol_mode IS NULL OR protocol_mode = 'inherit')"
        )
        conn.execute(
            "UPDATE certificate_authorities SET protocol_mode = 'inherit' "
            "WHERE protocol_mode IS NULL"
        )
    conn.commit()
    logger.info("062: protocol URL flexibility columns ready (SQLite)")


def _upgrade_pg(conn):
    from sqlalchemy import inspect, text

    insp = inspect(conn)
    if "certificate_authorities" not in set(insp.get_table_names()):
        logger.info("062: certificate_authorities absent, skipping")
        return

    existing = {c["name"] for c in insp.get_columns("certificate_authorities")}
    for name, ddl in _COLS_PG:
        if name in existing:
            continue
        conn.execute(
            text(f"ALTER TABLE certificate_authorities ADD COLUMN {name} {ddl}")
        )
        logger.info("062: added certificate_authorities.%s (PostgreSQL)", name)

    if "protocol_http" in existing:
        conn.execute(
            text(
                "UPDATE certificate_authorities SET protocol_mode = 'https_admin' "
                "WHERE protocol_http IS FALSE AND "
                "(protocol_mode IS NULL OR protocol_mode = 'inherit')"
            )
        )
        conn.execute(
            text(
                "UPDATE certificate_authorities SET protocol_mode = 'inherit' "
                "WHERE protocol_mode IS NULL"
            )
        )
    logger.info("062: protocol URL flexibility columns ready (PostgreSQL)")


def upgrade(conn):
    if isinstance(conn, sqlite3.Connection):
        _upgrade_sqlite(conn)
    else:
        _upgrade_pg(conn)


def downgrade(conn):
    # Non-destructive: leave columns in place (SQLite cannot DROP COLUMN reliably
    # on older versions; PG could DROP but we keep for safety).
    logger.info("062: downgrade is a no-op (columns retained)")
