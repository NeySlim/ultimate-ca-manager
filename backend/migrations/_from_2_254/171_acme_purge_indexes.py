"""Upgrade step 171: the ACME purge finds rows by index.

The purge looks up an order's authorizations by ``order_id`` and an authorization's challenges
by ``authorization_id``; without an index each lookup scanned its table, inside the purge's write
transaction, which on SQLite kept every other reader waiting past its busy timeout.
"""
import logging
import sqlite3

logger = logging.getLogger(__name__)
pg_compatible = True

INDEXES = (
    ('acme_authorizations', "CREATE INDEX IF NOT EXISTS ix_acme_authorizations_order_id "
                            "ON acme_authorizations (order_id)"),
    ('acme_challenges', "CREATE INDEX IF NOT EXISTS ix_acme_challenges_authorization_id "
                        "ON acme_challenges (authorization_id)"),
)


def upgrade(conn):
    if isinstance(conn, sqlite3.Connection):
        tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
        for table, statement in INDEXES:
            if table in tables:
                conn.execute(statement)
        conn.commit()
        logger.info("[171] ACME purge indexes (SQLite)")
        return
    from sqlalchemy import inspect, text
    tables = set(inspect(conn).get_table_names())
    for table, statement in INDEXES:
        if table in tables:
            conn.execute(text(statement))
    logger.info("[171] ACME purge indexes (PostgreSQL)")


def downgrade(conn):
    """No downgrade: an index is harmless."""
    pass
