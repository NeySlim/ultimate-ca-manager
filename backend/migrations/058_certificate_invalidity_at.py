"""Migration 058: add invalidity_at to certificates for CRL entry extension.

RFC 5280 §5.3.2 optional invalidityDate — the date on which it is known or
suspected that the private key was compromised or the certificate otherwise
became invalid (may precede revocationDate).
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
        logger.info("058: certificates table absent, skipping")
        return

    cur = conn.execute("PRAGMA table_info(certificates)")
    cols = {row[1] for row in cur.fetchall()}
    if 'invalidity_at' in cols:
        logger.info("058: invalidity_at already present, skipping")
        return

    conn.execute("ALTER TABLE certificates ADD COLUMN invalidity_at DATETIME")
    conn.commit()
    logger.info("058: added invalidity_at column to certificates (SQLite)")


def _upgrade_pg(conn):
    from sqlalchemy import inspect, text

    insp = inspect(conn)
    if 'certificates' not in set(insp.get_table_names()):
        logger.info("058: certificates table absent, skipping")
        return

    cols = {c['name'] for c in insp.get_columns('certificates')}
    if 'invalidity_at' in cols:
        logger.info("058: invalidity_at already present, skipping")
        return

    conn.execute(text("ALTER TABLE certificates ADD COLUMN invalidity_at TIMESTAMP"))
    logger.info("058: added invalidity_at column to certificates (PostgreSQL)")


def upgrade(conn):
    if isinstance(conn, sqlite3.Connection):
        _upgrade_sqlite(conn)
    else:
        _upgrade_pg(conn)


def downgrade(conn):
    if isinstance(conn, sqlite3.Connection):
        try:
            conn.execute("ALTER TABLE certificates DROP COLUMN invalidity_at")
            conn.commit()
        except Exception:
            pass
    else:
        from sqlalchemy import text
        conn.execute(text(
            "ALTER TABLE certificates DROP COLUMN IF EXISTS invalidity_at"
        ))
