"""Migration 115: related certificate pairs (RFC 9763).

``certificates.related_certificate_id`` names the other member of a pair and
``certificates.hybrid_role`` says which one this is (``classical`` or ``pq``).

Multi-backend convention: runs on both SQLite and PostgreSQL.
"""
import logging
import sqlite3

logger = logging.getLogger(__name__)
pg_compatible = True

TABLE = 'certificates'
_COLUMNS = (('related_certificate_id', 'INTEGER'), ('hybrid_role', 'VARCHAR(16)'))
# The name SQLAlchemy gives the model's index=True, so create_all and this agree
_INDEX = (f"CREATE INDEX IF NOT EXISTS ix_{TABLE}_related_certificate_id "
          f"ON {TABLE} (related_certificate_id)")


def _upgrade_sqlite(conn):
    exists = conn.execute("SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?",
                          (TABLE,)).fetchone()
    if not exists:
        return
    present = {row[1] for row in conn.execute(f"PRAGMA table_info({TABLE})")}
    for name, sql_type in _COLUMNS:
        if name not in present:
            conn.execute(f"ALTER TABLE {TABLE} ADD COLUMN {name} {sql_type}")
    conn.execute(_INDEX)
    conn.commit()


def _upgrade_pg(conn):
    from sqlalchemy import inspect, text

    inspector = inspect(conn)
    if TABLE not in inspector.get_table_names():
        return
    present = {c['name'] for c in inspector.get_columns(TABLE)}
    for name, sql_type in _COLUMNS:
        if name not in present:
            conn.execute(text(f"ALTER TABLE {TABLE} ADD COLUMN {name} {sql_type}"))
    conn.execute(text(_INDEX))


def upgrade(conn):
    if isinstance(conn, sqlite3.Connection):
        _upgrade_sqlite(conn)
    else:
        _upgrade_pg(conn)
    logger.info("Migration 115: ensured certificates.related_certificate_id and hybrid_role")


def downgrade(conn):
    if isinstance(conn, sqlite3.Connection):
        conn.execute(f"DROP INDEX IF EXISTS ix_{TABLE}_related_certificate_id")
        conn.commit()
    else:
        from sqlalchemy import text
        conn.execute(text(f"DROP INDEX IF EXISTS ix_{TABLE}_related_certificate_id"))
