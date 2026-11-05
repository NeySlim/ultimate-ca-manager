"""Migration 124: unique names for DNS providers, ACME CA accounts and webhooks.

Two rows with the same name were told apart by nothing a restore could use,
so it merged them and kept one secret. The later duplicates get " (2)",
" (3)"... and a unique index then holds the column.
"""
import logging
import sqlite3

from utils.unique_names import dedupe

logger = logging.getLogger(__name__)
pg_compatible = True

# (table, column, index): the index names match the models' __table_args__.
TARGETS = (
    ('dns_providers', 'name', 'uq_dns_providers_name'),
    ('acme_client_accounts', 'label', 'uq_acme_client_accounts_label'),
    ('webhook_endpoints', 'name', 'uq_webhook_endpoints_name'),
)


def _upgrade_sqlite(conn):
    for table, column, index in TARGETS:
        if conn.execute("SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?",
                        (table,)).fetchone() is None:
            continue
        if column not in {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}:
            continue
        rows = conn.execute(f"SELECT id, {column} FROM {table} ORDER BY id").fetchall()
        renames = dedupe(rows)
        for row_id, name in renames:
            conn.execute(f"UPDATE {table} SET {column} = ? WHERE id = ?", (name, row_id))
        conn.execute(f"CREATE UNIQUE INDEX IF NOT EXISTS {index} ON {table} ({column})")
        if renames:
            logger.info("Migration 124: renamed %s duplicate %s.%s value(s)",
                        len(renames), table, column)
    conn.commit()


def _upgrade_pg(conn):
    from sqlalchemy import inspect, text

    inspector = inspect(conn)
    tables = set(inspector.get_table_names())
    for table, column, index in TARGETS:
        if table not in tables:
            continue
        if column not in {c['name'] for c in inspector.get_columns(table)}:
            continue
        rows = conn.execute(text(f"SELECT id, {column} FROM {table} ORDER BY id")).fetchall()
        renames = dedupe([tuple(row) for row in rows])
        for row_id, name in renames:
            conn.execute(text(f"UPDATE {table} SET {column} = :name WHERE id = :id"),
                         {'name': name, 'id': row_id})
        conn.execute(text(f"CREATE UNIQUE INDEX IF NOT EXISTS {index} ON {table} ({column})"))
        if renames:
            logger.info("Migration 124: renamed %s duplicate %s.%s value(s)",
                        len(renames), table, column)


def upgrade(conn):
    if isinstance(conn, sqlite3.Connection):
        _upgrade_sqlite(conn)
    else:
        _upgrade_pg(conn)


def downgrade(conn):
    pass
