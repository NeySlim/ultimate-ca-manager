"""Migration 117: relatedCertRequests already honoured (RFC 9763).

``related_cert_requests`` binds each request, by the hash of what its requester
signed and of the signature, to the first key B it was presented with, until it is
too old to be honoured.

Multi-backend convention: runs on both SQLite and PostgreSQL.
"""
import logging
import sqlite3

logger = logging.getLogger(__name__)
pg_compatible = True

TABLE = 'related_cert_requests'
# The name SQLAlchemy gives the model's index=True, so create_all and this agree
_INDEX = f"CREATE INDEX IF NOT EXISTS ix_{TABLE}_request_time ON {TABLE} (request_time)"


def _table(pk, ts):
    return f"""
    CREATE TABLE IF NOT EXISTS {TABLE} (
        id {pk},
        request_sha256 VARCHAR(64) NOT NULL UNIQUE,
        spki_sha256 VARCHAR(64) NOT NULL,
        request_time {ts} NOT NULL,
        created_at {ts}
    )"""


def _upgrade_sqlite(conn):
    conn.execute(_table('INTEGER PRIMARY KEY AUTOINCREMENT', 'DATETIME'))
    conn.execute(_INDEX)
    conn.commit()


def _upgrade_pg(conn):
    from sqlalchemy import text

    conn.execute(text(_table('SERIAL PRIMARY KEY', 'TIMESTAMP')))
    conn.execute(text(_INDEX))


def upgrade(conn):
    if isinstance(conn, sqlite3.Connection):
        _upgrade_sqlite(conn)
    else:
        _upgrade_pg(conn)
    logger.info("Migration 117: ensured related_cert_requests")


def downgrade(conn):
    if isinstance(conn, sqlite3.Connection):
        conn.execute(f"DROP TABLE IF EXISTS {TABLE}")
        conn.commit()
    else:
        from sqlalchemy import text
        conn.execute(text(f"DROP TABLE IF EXISTS {TABLE}"))
