"""Migration 064: add the selected certificate profile to ACME orders.

ACME Profiles Extension (draft-ietf-acme-profiles): a client may pick a
server-advertised profile in newOrder; the name is recorded on the order so
finalize applies the matching issuance parameters.

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
        logger.info('[064] acme_orders absent, skipping (SQLite)')
        return

    columns = {
        row[1] for row in conn.execute('PRAGMA table_info(acme_orders)').fetchall()
    }
    if 'profile' not in columns:
        conn.execute('ALTER TABLE acme_orders ADD COLUMN profile VARCHAR(64)')
    conn.commit()
    logger.info('[064] added ACME order profile (SQLite)')


def _upgrade_pg(conn):
    from sqlalchemy import inspect, text

    inspector = inspect(conn)
    if 'acme_orders' not in set(inspector.get_table_names()):
        logger.info('[064] acme_orders absent, skipping (PostgreSQL)')
        return

    columns = {
        column['name'] for column in inspector.get_columns('acme_orders')
    }
    if 'profile' not in columns:
        conn.execute(text(
            'ALTER TABLE acme_orders ADD COLUMN profile VARCHAR(64)'
        ))
    logger.info('[064] added ACME order profile (PostgreSQL)')


def upgrade(conn):
    if isinstance(conn, sqlite3.Connection):
        _upgrade_sqlite(conn)
    else:
        _upgrade_pg(conn)


def downgrade(conn):
    """Keep the recorded profile when rolling application code back."""
    pass
