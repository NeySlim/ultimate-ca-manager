"""Migration 059: full CRL schedule per CA (discussion #207).

Adds to certificate_authorities:
  crl_validity_days          — CRL nextUpdate window (NULL = default 7 days)
  crl_publish_interval_hours — publish cadence, decoupled from validity
                               (NULL = legacy regenerate-near-expiry behaviour)
  crl_digest                 — CRL signature digest (NULL = sha256)
"""
import logging
import sqlite3

logger = logging.getLogger(__name__)
pg_compatible = True

_COLUMNS = (
    ("crl_validity_days", "INTEGER"),
    ("crl_publish_interval_hours", "INTEGER"),
    ("crl_digest", "VARCHAR(20)"),
)


def _upgrade_sqlite(conn):
    cur = conn.execute("PRAGMA table_info(certificate_authorities)")
    existing = {row[1] for row in cur.fetchall()}
    for name, coltype in _COLUMNS:
        if name not in existing:
            conn.execute(
                f"ALTER TABLE certificate_authorities ADD COLUMN {name} {coltype}"
            )
    conn.commit()
    logger.info("[059] added CRL schedule columns to certificate_authorities (SQLite)")


def _upgrade_pg(conn):
    from sqlalchemy import text
    for name, coltype in _COLUMNS:
        conn.execute(text(
            f"ALTER TABLE certificate_authorities ADD COLUMN IF NOT EXISTS {name} {coltype}"
        ))
    logger.info("[059] added CRL schedule columns to certificate_authorities (PostgreSQL)")


def upgrade(conn):
    if isinstance(conn, sqlite3.Connection):
        _upgrade_sqlite(conn)
    else:
        _upgrade_pg(conn)


def downgrade(conn):
    if isinstance(conn, sqlite3.Connection):
        for name, _ in _COLUMNS:
            try:
                conn.execute(f"ALTER TABLE certificate_authorities DROP COLUMN {name}")
            except Exception:
                pass
        conn.commit()
    else:
        from sqlalchemy import text
        for name, _ in _COLUMNS:
            conn.execute(text(
                f"ALTER TABLE certificate_authorities DROP COLUMN IF EXISTS {name}"
            ))
