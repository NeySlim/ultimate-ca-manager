"""Migration 048: per-CA ACME client timing settings.

Adds poll timeout, poll interval and HTTP timeout columns on
``acme_client_accounts`` so slow CAs can be tuned without
changing global defaults.

Dual-backend (SQLite + PostgreSQL).
"""
import logging
import sqlite3

logger = logging.getLogger(__name__)
pg_compatible = True

DEFAULT_POLL_TIMEOUT = 180
DEFAULT_POLL_INTERVAL = 3
DEFAULT_HTTP_TIMEOUT = 60


def _column_exists_sqlite(conn, table, column):
    cur = conn.execute(f"PRAGMA table_info({table})")
    return any(row[1] == column for row in cur.fetchall())


def _upgrade_sqlite(conn):
    cur = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='acme_client_accounts'"
    )
    if not cur.fetchone():
        logger.info("[048] acme_client_accounts absent, skipping")
        return

    columns = [
        ('order_poll_timeout_sec', f'INTEGER NOT NULL DEFAULT {DEFAULT_POLL_TIMEOUT}'),
        ('order_poll_interval_sec', f'INTEGER NOT NULL DEFAULT {DEFAULT_POLL_INTERVAL}'),
        ('http_timeout_sec', f'INTEGER NOT NULL DEFAULT {DEFAULT_HTTP_TIMEOUT}'),
    ]
    for col, typedef in columns:
        if not _column_exists_sqlite(conn, 'acme_client_accounts', col):
            conn.execute(
                f"ALTER TABLE acme_client_accounts ADD COLUMN {col} {typedef}"
            )
            logger.info("[048] added acme_client_accounts.%s", col)


def _downgrade_sqlite(conn):
    # SQLite cannot drop columns easily — no-op.
    pass


def upgrade(conn):
    if isinstance(conn, sqlite3.Connection):
        _upgrade_sqlite(conn)
        return

    from sqlalchemy import inspect, text

    insp = inspect(conn)
    if 'acme_client_accounts' not in insp.get_table_names():
        logger.info("[048] acme_client_accounts absent, skipping")
        return

    existing = {c['name'] for c in insp.get_columns('acme_client_accounts')}
    specs = {
        'order_poll_timeout_sec': f'INTEGER NOT NULL DEFAULT {DEFAULT_POLL_TIMEOUT}',
        'order_poll_interval_sec': f'INTEGER NOT NULL DEFAULT {DEFAULT_POLL_INTERVAL}',
        'http_timeout_sec': f'INTEGER NOT NULL DEFAULT {DEFAULT_HTTP_TIMEOUT}',
    }
    for col, typedef in specs.items():
        if col not in existing:
            conn.execute(text(f'ALTER TABLE acme_client_accounts ADD COLUMN {col} {typedef}'))
            logger.info("[048] added acme_client_accounts.%s", col)


def downgrade(conn):
    if isinstance(conn, sqlite3.Connection):
        _downgrade_sqlite(conn)
