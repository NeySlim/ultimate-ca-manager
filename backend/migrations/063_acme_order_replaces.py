"""Migration 063: add RFC 9773 replacement CertID to ACME orders.

Dual-backend (SQLite + PostgreSQL).
"""

import logging
import sqlite3

logger = logging.getLogger(__name__)
pg_compatible = True


def _upgrade_sqlite(conn):
    tables = {
        row[0] for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
    }
    if 'acme_orders' not in tables:
        logger.info('[063] acme_orders absent, skipping (SQLite)')
        return

    columns = {
        row[1] for row in conn.execute('PRAGMA table_info(acme_orders)').fetchall()
    }
    if 'replaces' not in columns:
        conn.execute('ALTER TABLE acme_orders ADD COLUMN replaces VARCHAR(255)')
    conn.execute(
        'CREATE INDEX IF NOT EXISTS ix_acme_orders_replaces '
        'ON acme_orders(replaces)'
    )
    conn.commit()
    logger.info('[063] added ACME order replaces identifier (SQLite)')


def _upgrade_pg(conn):
    from sqlalchemy import inspect, text

    inspector = inspect(conn)
    if 'acme_orders' not in set(inspector.get_table_names()):
        logger.info('[063] acme_orders absent, skipping (PostgreSQL)')
        return

    columns = {
        column['name'] for column in inspector.get_columns('acme_orders')
    }
    if 'replaces' not in columns:
        conn.execute(text(
            'ALTER TABLE acme_orders ADD COLUMN replaces VARCHAR(255)'
        ))
    conn.execute(text(
        'CREATE INDEX IF NOT EXISTS ix_acme_orders_replaces '
        'ON acme_orders(replaces)'
    ))
    logger.info('[063] added ACME order replaces identifier (PostgreSQL)')


def upgrade(conn):
    if isinstance(conn, sqlite3.Connection):
        _upgrade_sqlite(conn)
    else:
        _upgrade_pg(conn)


def downgrade(conn):
    """Keep replacement history when rolling application code back."""
    pass
