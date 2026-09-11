"""Migration 085: scep_requests.profile_id.

A SCEP request now records the profile it came through, so that approving
it by hand applies that profile's template (validity, key usages) exactly
as auto-approval does. Existing rows keep NULL and are approved with the
CA defaults, as before.
"""

import logging
import sqlite3

logger = logging.getLogger(__name__)
pg_compatible = True


def _upgrade_sqlite(conn):
    cols = [row[1] for row in conn.execute("PRAGMA table_info(scep_requests)").fetchall()]
    if 'profile_id' not in cols:
        conn.execute("ALTER TABLE scep_requests ADD COLUMN profile_id INTEGER")
        logger.info("085: added scep_requests.profile_id (SQLite)")
    conn.commit()


def _upgrade_pg(conn):
    from sqlalchemy import inspect, text
    cols = {col['name'] for col in inspect(conn).get_columns('scep_requests')}
    if 'profile_id' not in cols:
        conn.execute(text("ALTER TABLE scep_requests ADD COLUMN profile_id INTEGER"))
        logger.info("085: added scep_requests.profile_id (PostgreSQL)")


def upgrade(conn):
    if isinstance(conn, sqlite3.Connection):
        _upgrade_sqlite(conn)
    else:
        _upgrade_pg(conn)


def downgrade(conn):
    if isinstance(conn, sqlite3.Connection):
        logger.info("085: downgrade is a no-op on SQLite (column kept)")
        return
    from sqlalchemy import text
    conn.execute(text("ALTER TABLE scep_requests DROP COLUMN IF EXISTS profile_id"))
