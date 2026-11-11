"""Migration 151: a deploy binding a renewal left on the previous certificate says so.

Two nullable columns, empty on every existing binding: the reason and the id of the
successor certificate the binding could not follow (it has no key in UCM).
"""
import logging
import sqlite3

logger = logging.getLogger(__name__)
pg_compatible = True

TABLE = 'deploy_bindings'
INDEX = 'ix_deploy_bindings_attention_successor_id'
COLUMNS = (('attention_reason', 'VARCHAR(40)'), ('attention_successor_id', 'INTEGER'))


def _upgrade_sqlite(conn):
    tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    if TABLE not in tables:
        logger.info("151: no deploy_bindings table, nothing to do (SQLite)")
        return
    cols = {row[1] for row in conn.execute(f"PRAGMA table_info({TABLE})")}
    for name, sql_type in COLUMNS:
        if name not in cols:
            conn.execute(f"ALTER TABLE {TABLE} ADD COLUMN {name} {sql_type}")
    conn.execute(f"CREATE INDEX IF NOT EXISTS {INDEX} ON {TABLE} (attention_successor_id)")
    conn.commit()
    logger.info("151: deploy_bindings carries the left-behind state (SQLite)")


def _upgrade_pg(conn):
    from sqlalchemy import inspect, text
    inspector = inspect(conn)
    if TABLE not in inspector.get_table_names():
        logger.info("151: no deploy_bindings table, nothing to do (PostgreSQL)")
        return
    cols = {column['name'] for column in inspector.get_columns(TABLE)}
    for name, sql_type in COLUMNS:
        if name not in cols:
            conn.execute(text(f"ALTER TABLE {TABLE} ADD COLUMN {name} {sql_type}"))
    conn.execute(text(f"CREATE INDEX IF NOT EXISTS {INDEX} ON {TABLE} (attention_successor_id)"))
    logger.info("151: deploy_bindings carries the left-behind state (PostgreSQL)")


def upgrade(conn):
    if isinstance(conn, sqlite3.Connection):
        _upgrade_sqlite(conn)
    else:
        _upgrade_pg(conn)


def downgrade(conn):
    # Added columns are harmless if left behind, matching nearby migrations.
    pass
