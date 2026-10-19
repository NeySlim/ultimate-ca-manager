"""Migration 098: audit entries name how they are sealed.

``hash_version`` is NULL or 1 for SHA-256 (every entry written so far, which
stays verifiable as it is) and 2 for HMAC-SHA256 under a key derived from the
master key, named by ``hash_key_id``. ``chain_start`` records the first id the
ledger holds, on the first entry under a key and on each purge record.

Dual-backend (SQLite + PostgreSQL).
"""
import logging
import sqlite3

logger = logging.getLogger(__name__)
pg_compatible = True

_COLUMNS = (
    ('hash_version', 'INTEGER'),
    ('hash_key_id', 'VARCHAR(16)'),
    ('chain_start', 'INTEGER'),
)


def _upgrade_sqlite(conn):
    if not conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' "
                        "AND name='audit_logs'").fetchone():
        return
    cols = {row[1] for row in conn.execute("PRAGMA table_info(audit_logs)")}
    for name, sql_type in _COLUMNS:
        if name not in cols:
            conn.execute(f"ALTER TABLE audit_logs ADD COLUMN {name} {sql_type}")
    conn.commit()


def _upgrade_pg(conn):
    from sqlalchemy import inspect, text

    # Migrations run before create_all: a new installation gets the columns
    # from the model.
    if not inspect(conn).has_table('audit_logs'):
        return
    for name, sql_type in _COLUMNS:
        conn.execute(text(
            f"ALTER TABLE audit_logs ADD COLUMN IF NOT EXISTS {name} {sql_type}"))


def upgrade(conn):
    if isinstance(conn, sqlite3.Connection):
        _upgrade_sqlite(conn)
    else:
        _upgrade_pg(conn)


def downgrade(conn):
    # Kept: dropping them would lose how each entry was sealed.
    pass
