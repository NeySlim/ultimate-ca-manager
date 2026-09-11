"""Migration 084: index on approval_requests (status, request_type).

The pending requests of a type are looked up on every direct signing,
renewal, revocation and deletion (a queued request made moot by the action
is closed) and by the renewal scheduler. The index keeps that lookup to the
pending rows whatever the table holds.
"""

import logging
import sqlite3

logger = logging.getLogger(__name__)
pg_compatible = True

_INDEX = ("CREATE INDEX IF NOT EXISTS ix_approval_requests_status_type "
          "ON approval_requests (status, request_type)")


def _upgrade_sqlite(conn):
    conn.execute(_INDEX)
    conn.commit()
    logger.info("084: ensured ix_approval_requests_status_type (SQLite)")


def _upgrade_pg(conn):
    from sqlalchemy import text
    conn.execute(text(_INDEX))
    logger.info("084: ensured ix_approval_requests_status_type (PostgreSQL)")


def upgrade(conn):
    if isinstance(conn, sqlite3.Connection):
        _upgrade_sqlite(conn)
    else:
        _upgrade_pg(conn)


def downgrade(conn):
    stmt = "DROP INDEX IF EXISTS ix_approval_requests_status_type"
    if isinstance(conn, sqlite3.Connection):
        conn.execute(stmt)
        conn.commit()
    else:
        from sqlalchemy import text
        conn.execute(text(stmt))
