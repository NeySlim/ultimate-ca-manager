"""Upgrade step 163: an SSH CA can keep its key on an HSM token.

``ssh_cas.key_source`` ('software' on every existing row) and ``ssh_cas.hsm_key_id`` (NULL),
a foreign key to ``hsm_keys.id``; the unique index ``uq_ssh_cas_hsm_key_id`` binds a key to
one SSH CA at most (NULLs stay distinct on both backends). 2.254 has no HSM SSH CA: no row moves.
Idempotent, dual-backend (SQLite + PostgreSQL).
"""
import logging
import sqlite3

logger = logging.getLogger(__name__)
pg_compatible = True

TABLE = 'ssh_cas'
INDEX = ('CREATE UNIQUE INDEX IF NOT EXISTS uq_ssh_cas_hsm_key_id '
         'ON ssh_cas (hsm_key_id)')
_COLUMNS = (
    ('key_source', "VARCHAR(20) NOT NULL DEFAULT 'software'"),
    ('hsm_key_id', 'INTEGER REFERENCES hsm_keys (id)'),
)


def _upgrade_sqlite(conn):
    tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
    if TABLE not in tables:
        logger.info("163: no ssh_cas table, nothing to do (SQLite)")
        return
    columns = {row[1] for row in conn.execute(f"PRAGMA table_info({TABLE})")}
    for name, ddl in _COLUMNS:
        if name not in columns:
            conn.execute(f"ALTER TABLE {TABLE} ADD COLUMN {name} {ddl}")
    conn.execute(INDEX)
    conn.commit()
    logger.info("163: ssh_cas can name an HSM key (SQLite)")


def _upgrade_pg(conn):
    from sqlalchemy import inspect, text
    inspector = inspect(conn)
    if TABLE not in inspector.get_table_names():
        logger.info("163: no ssh_cas table, nothing to do (PostgreSQL)")
        return
    columns = {c['name'] for c in inspector.get_columns(TABLE)}
    for name, ddl in _COLUMNS:
        if name not in columns:
            conn.execute(text(f"ALTER TABLE {TABLE} ADD COLUMN {name} {ddl}"))
    conn.execute(text(INDEX))
    logger.info("163: ssh_cas can name an HSM key (PostgreSQL)")


def upgrade(conn):
    if isinstance(conn, sqlite3.Connection):
        _upgrade_sqlite(conn)
    else:
        _upgrade_pg(conn)


def downgrade(conn):
    """No downgrade: 2.254 never reads the two columns."""
    pass
