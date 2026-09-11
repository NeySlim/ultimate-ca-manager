"""Migration 086: scep_requests.renewal_of.

A SCEP RenewalReq is signed with the certificate being renewed. The request
now keeps that certificate (base64 PEM), so that approving it by hand
archives the renewed record exactly as auto-approval does. Existing rows
keep NULL and are approved as initial enrolments, as before.
"""

import logging
import sqlite3

logger = logging.getLogger(__name__)
pg_compatible = True


def _upgrade_sqlite(conn):
    cols = [row[1] for row in conn.execute("PRAGMA table_info(scep_requests)").fetchall()]
    if 'renewal_of' not in cols:
        conn.execute("ALTER TABLE scep_requests ADD COLUMN renewal_of TEXT")
        logger.info("086: added scep_requests.renewal_of (SQLite)")
    conn.commit()


def _upgrade_pg(conn):
    from sqlalchemy import inspect, text
    cols = {col['name'] for col in inspect(conn).get_columns('scep_requests')}
    if 'renewal_of' not in cols:
        conn.execute(text("ALTER TABLE scep_requests ADD COLUMN renewal_of TEXT"))
        logger.info("086: added scep_requests.renewal_of (PostgreSQL)")


def upgrade(conn):
    if isinstance(conn, sqlite3.Connection):
        _upgrade_sqlite(conn)
    else:
        _upgrade_pg(conn)


def downgrade(conn):
    if isinstance(conn, sqlite3.Connection):
        logger.info("086: downgrade is a no-op on SQLite (column kept)")
        return
    from sqlalchemy import text
    conn.execute(text("ALTER TABLE scep_requests DROP COLUMN IF EXISTS renewal_of"))
