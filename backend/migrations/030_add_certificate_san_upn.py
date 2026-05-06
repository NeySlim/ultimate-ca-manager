"""Migration 030: add san_upn column to certificates table.

Stores JSON array of UPN strings (Microsoft User Principal Name SAN entries,
OID 1.3.6.1.4.1.311.20.2.3, encoded as x509.OtherName with UTF8String DER).

Idempotent and multi-backend (SQLite + PostgreSQL).
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
        logger.info("030: certificates table absent, skipping")
        return

    cur = conn.execute("PRAGMA table_info(certificates)")
    cols = {row[1] for row in cur.fetchall()}
    if 'san_upn' in cols:
        logger.info("030: san_upn column already present, skipping")
        return

    conn.execute("ALTER TABLE certificates ADD COLUMN san_upn TEXT")
    conn.commit()
    logger.info("030: added san_upn column to certificates table (SQLite)")


def _upgrade_pg(conn):
    """Apply migration on PostgreSQL.

    The runner already opens a transaction via ``with engine.begin() as conn``
    and passes that Connection here. Calling ``conn.begin()`` (or
    ``engine.begin()`` against an already-bound connection) raises
    "transaction already begun". Use the passed connection directly.
    """
    from sqlalchemy import inspect, text

    insp = inspect(conn)
    if 'certificates' not in set(insp.get_table_names()):
        logger.info("030: certificates table absent, skipping")
        return

    cols = {c['name'] for c in insp.get_columns('certificates')}
    if 'san_upn' in cols:
        logger.info("030: san_upn column already present, skipping")
        return

    conn.execute(text("ALTER TABLE certificates ADD COLUMN san_upn TEXT"))
    logger.info("030: added san_upn column to certificates table (PostgreSQL)")


def upgrade(conn):
    if isinstance(conn, sqlite3.Connection):
        _upgrade_sqlite(conn)
    else:
        _upgrade_pg(conn)


def downgrade(conn):
    # SQLite has no simple DROP COLUMN — no-op
    pass
