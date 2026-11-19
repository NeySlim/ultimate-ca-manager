"""Migration 131: deploy targets can push a certificate to an HTTP API.

A target is SSH/SFTP (``kind = 'ssh'``, the only kind before this) or HTTP
(``kind = 'http'``): URL, method, encrypted headers, a body template and an
explicit opt-in before the private key may leave in a request body.
"""
import logging
import sqlite3

logger = logging.getLogger(__name__)
pg_compatible = True

TABLE = 'deploy_targets'
# (column, SQLite definition, PostgreSQL definition)
_COLUMNS = (
    ('kind', "VARCHAR(8) NOT NULL DEFAULT 'ssh'", "VARCHAR(8) NOT NULL DEFAULT 'ssh'"),
    ('url', 'VARCHAR(2048)', 'VARCHAR(2048)'),
    ('http_method', 'VARCHAR(8)', 'VARCHAR(8)'),
    ('http_headers', 'TEXT', 'TEXT'),
    ('body_template', 'TEXT', 'TEXT'),
    ('tls_ca_pem', 'TEXT', 'TEXT'),
    ('allow_private_key', 'BOOLEAN NOT NULL DEFAULT 0', 'BOOLEAN NOT NULL DEFAULT FALSE'),
)


def _upgrade_sqlite(conn):
    if conn.execute("SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?",
                    (TABLE,)).fetchone() is None:
        return
    present = {row[1] for row in conn.execute(f"PRAGMA table_info({TABLE})")}
    for name, sqlite_def, _ in _COLUMNS:
        if name not in present:
            conn.execute(f"ALTER TABLE {TABLE} ADD COLUMN {name} {sqlite_def}")
    conn.commit()
    logger.info("[131] deploy_targets HTTP columns (SQLite)")


def _upgrade_pg(conn):
    from sqlalchemy import inspect, text

    inspector = inspect(conn)
    if TABLE not in set(inspector.get_table_names()):
        return
    present = {column['name'] for column in inspector.get_columns(TABLE)}
    for name, _, pg_def in _COLUMNS:
        if name not in present:
            conn.execute(text(f"ALTER TABLE {TABLE} ADD COLUMN {name} {pg_def}"))
    logger.info("[131] deploy_targets HTTP columns (PostgreSQL)")


def upgrade(conn):
    if isinstance(conn, sqlite3.Connection):
        _upgrade_sqlite(conn)
    else:
        _upgrade_pg(conn)


def downgrade(conn):
    """No downgrade: an HTTP target has no SSH credentials to fall back on."""
    pass
