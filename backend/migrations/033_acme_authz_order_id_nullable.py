"""Migration 033: make acme_authorizations.order_id nullable for pre-authz.

RFC 8555 §7.4.1 newAuthz endpoint allows a client to create a standalone
authorization (no order yet). Migration 016 added account_id but its
docstring's "make order_id nullable" promise was never implemented because
SQLite has no ALTER COLUMN. This migration recreates the table on SQLite
and drops the NOT NULL constraint on PostgreSQL.

Dual-backend (SQLite + PostgreSQL).
"""
import logging
import sqlite3

logger = logging.getLogger(__name__)
pg_compatible = True


def _upgrade_sqlite(conn):
    cursor = conn.execute("PRAGMA table_info(acme_authorizations)")
    cols = {row[1]: row for row in cursor.fetchall()}
    if 'order_id' not in cols:
        logger.info("[033] acme_authorizations.order_id absent, skipping")
        return
    # row layout: cid, name, type, notnull, dflt, pk
    if cols['order_id'][3] == 0:
        logger.info("[033] order_id already nullable, skipping")
        return

    conn.executescript("""
        CREATE TABLE _acme_authorizations_new (
            id INTEGER NOT NULL,
            authorization_id VARCHAR(64) NOT NULL,
            order_id VARCHAR(64),
            identifier TEXT NOT NULL,
            status VARCHAR(20) NOT NULL,
            expires DATETIME NOT NULL,
            wildcard BOOLEAN,
            created_at DATETIME NOT NULL,
            account_id VARCHAR(64),
            PRIMARY KEY (id),
            FOREIGN KEY(order_id) REFERENCES acme_orders (order_id)
        );
        INSERT INTO _acme_authorizations_new
            (id, authorization_id, order_id, identifier, status, expires,
             wildcard, created_at, account_id)
        SELECT id, authorization_id, order_id, identifier, status, expires,
               wildcard, created_at, account_id
        FROM acme_authorizations;
        DROP TABLE acme_authorizations;
        ALTER TABLE _acme_authorizations_new RENAME TO acme_authorizations;
        CREATE UNIQUE INDEX IF NOT EXISTS ix_acme_authorizations_authorization_id
            ON acme_authorizations (authorization_id);
    """)
    conn.commit()
    logger.info("[033] acme_authorizations.order_id made nullable (SQLite)")


def _upgrade_pg(conn):
    from sqlalchemy import inspect, text

    insp = inspect(conn)
    if 'acme_authorizations' not in set(insp.get_table_names()):
        logger.info("[033] acme_authorizations absent, skipping (fresh PG)")
        return

    cols = {c['name']: c for c in insp.get_columns('acme_authorizations')}
    if 'order_id' not in cols:
        logger.info("[033] acme_authorizations.order_id absent, skipping")
        return

    if cols['order_id'].get('nullable', True):
        logger.info("[033] order_id already nullable, skipping")
        return

    conn.execute(text("ALTER TABLE acme_authorizations ALTER COLUMN order_id DROP NOT NULL"))
    logger.info("[033] acme_authorizations.order_id made nullable (PostgreSQL)")


def upgrade(conn):
    if isinstance(conn, sqlite3.Connection):
        _upgrade_sqlite(conn)
    else:
        _upgrade_pg(conn)


def downgrade(conn):
    """No downgrade — would require deleting standalone authorizations."""
    pass
