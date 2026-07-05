"""Migration 049: ACME key source (CSR / reuse) columns on client orders.

Adds key_source, csr_pem and source_certificate_id so ACME client orders
can finalize with an external CSR or reuse a private key on renewal.

Dual-backend (SQLite + PostgreSQL).
"""
import logging
import sqlite3

logger = logging.getLogger(__name__)
pg_compatible = True


def _column_exists_sqlite(conn, table, column):
    cur = conn.execute(f"PRAGMA table_info({table})")
    return any(row[1] == column for row in cur.fetchall())


def _upgrade_sqlite(conn):
    cur = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='acme_client_orders'"
    )
    if not cur.fetchone():
        logger.info("[049] acme_client_orders absent, skipping")
        return

    columns = [
        ('key_source', "VARCHAR(20) NOT NULL DEFAULT 'generate'"),
        ('csr_pem', 'TEXT'),
        ('source_certificate_id', 'INTEGER'),
    ]
    for col, typedef in columns:
        if not _column_exists_sqlite(conn, 'acme_client_orders', col):
            conn.execute(
                f"ALTER TABLE acme_client_orders ADD COLUMN {col} {typedef}"
            )
            logger.info("[049] added acme_client_orders.%s", col)


def upgrade(conn):
    if isinstance(conn, sqlite3.Connection):
        _upgrade_sqlite(conn)
        return

    from sqlalchemy import inspect, text

    insp = inspect(conn)
    if 'acme_client_orders' not in insp.get_table_names():
        logger.info("[049] acme_client_orders absent, skipping")
        return

    existing = {c['name'] for c in insp.get_columns('acme_client_orders')}
    specs = {
        'key_source': "VARCHAR(20) NOT NULL DEFAULT 'generate'",
        'csr_pem': 'TEXT',
        'source_certificate_id': 'INTEGER',
    }
    for col, typedef in specs.items():
        if col not in existing:
            conn.execute(text(f'ALTER TABLE acme_client_orders ADD COLUMN {col} {typedef}'))
            logger.info("[049] added acme_client_orders.%s", col)
