"""Migration 061: per-CA protocol_http for CDP/OCSP/AIA URL scheme.

When True (default), auto-generated CDP/OCSP/AIA URLs use the HTTP protocol
listener (typically :8080). When False, they use the admin HTTPS URL (:8443).
"""

import logging
import sqlite3

logger = logging.getLogger(__name__)
pg_compatible = True


def _upgrade_sqlite(conn):
    cur = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' "
        "AND name='certificate_authorities'"
    )
    if not cur.fetchone():
        logger.info("061: certificate_authorities absent, skipping")
        return

    cols = {
        row[1] for row in conn.execute("PRAGMA table_info(certificate_authorities)")
    }
    if "protocol_http" in cols:
        logger.info("061: protocol_http already present, skipping")
        return

    conn.execute(
        "ALTER TABLE certificate_authorities "
        "ADD COLUMN protocol_http BOOLEAN DEFAULT 1"
    )
    conn.commit()
    logger.info("061: added certificate_authorities.protocol_http (SQLite)")


def _upgrade_pg(conn):
    from sqlalchemy import inspect, text

    insp = inspect(conn)
    if "certificate_authorities" not in set(insp.get_table_names()):
        logger.info("061: certificate_authorities absent, skipping")
        return

    existing = {c["name"] for c in insp.get_columns("certificate_authorities")}
    if "protocol_http" in existing:
        logger.info("061: protocol_http already present, skipping")
        return

    conn.execute(
        text(
            "ALTER TABLE certificate_authorities "
            "ADD COLUMN protocol_http BOOLEAN DEFAULT TRUE"
        )
    )
    logger.info("061: added certificate_authorities.protocol_http (PostgreSQL)")


def upgrade(conn):
    if isinstance(conn, sqlite3.Connection):
        _upgrade_sqlite(conn)
    else:
        _upgrade_pg(conn)


def downgrade(conn):
    if isinstance(conn, sqlite3.Connection):
        try:
            conn.execute(
                "ALTER TABLE certificate_authorities DROP COLUMN protocol_http"
            )
            conn.commit()
        except Exception:
            pass
    else:
        from sqlalchemy import text

        conn.execute(
            text(
                "ALTER TABLE certificate_authorities "
                "DROP COLUMN IF EXISTS protocol_http"
            )
        )
