"""Migration 060: certificates.friendly_name (discussion #207 batch-2).

Operator-editable display label independent of CN — useful when several
certs share the same CN (e.g. OCSP responder certs per CA).
"""

import logging
import sqlite3

logger = logging.getLogger(__name__)
pg_compatible = True


def _upgrade_sqlite(conn):
    cur = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='certificates'"
    )
    if not cur.fetchone():
        logger.info("060: certificates table absent, skipping")
        return

    cols = {row[1] for row in conn.execute("PRAGMA table_info(certificates)")}
    if "friendly_name" in cols:
        logger.info("060: friendly_name already present, skipping")
        return

    conn.execute(
        "ALTER TABLE certificates ADD COLUMN friendly_name VARCHAR(255)"
    )
    conn.commit()
    logger.info("060: added certificates.friendly_name (SQLite)")


def _upgrade_pg(conn):
    from sqlalchemy import inspect, text

    insp = inspect(conn)
    if "certificates" not in set(insp.get_table_names()):
        logger.info("060: certificates table absent, skipping")
        return

    existing = {c["name"] for c in insp.get_columns("certificates")}
    if "friendly_name" in existing:
        logger.info("060: friendly_name already present, skipping")
        return

    conn.execute(
        text("ALTER TABLE certificates ADD COLUMN friendly_name VARCHAR(255)")
    )
    logger.info("060: added certificates.friendly_name (PostgreSQL)")


def upgrade(conn):
    if isinstance(conn, sqlite3.Connection):
        _upgrade_sqlite(conn)
    else:
        _upgrade_pg(conn)


def downgrade(conn):
    if isinstance(conn, sqlite3.Connection):
        try:
            conn.execute("ALTER TABLE certificates DROP COLUMN friendly_name")
            conn.commit()
        except Exception:
            pass
    else:
        from sqlalchemy import text

        conn.execute(
            text("ALTER TABLE certificates DROP COLUMN IF EXISTS friendly_name")
        )
