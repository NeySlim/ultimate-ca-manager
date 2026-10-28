"""Migration 114: certificates that cross-sign a CA's key under another issuer.

``ca_cross_certificates`` keeps them beside the CA's own certificate instead
of in place of it; ``deploy_bindings.chain_variant`` records which chain a
binding deploys (``auto`` = the one the CA serves).

Multi-backend convention: runs on both SQLite and PostgreSQL.
"""
import logging
import sqlite3

logger = logging.getLogger(__name__)
pg_compatible = True

TABLE = 'ca_cross_certificates'
_BINDINGS = 'deploy_bindings'
_COLUMN = 'chain_variant'

_INDEXES = (
    f"CREATE INDEX IF NOT EXISTS ix_{TABLE}_ca_id ON {TABLE} (ca_id)",
    f"CREATE INDEX IF NOT EXISTS ix_{TABLE}_issuer_caref ON {TABLE} (issuer_caref)",
)


def _table(pk, ts, false):
    return f"""
    CREATE TABLE IF NOT EXISTS {TABLE} (
        id {pk},
        ca_id INTEGER NOT NULL REFERENCES certificate_authorities (id) ON DELETE CASCADE,
        crt TEXT NOT NULL,
        fingerprint_sha256 VARCHAR(64) NOT NULL UNIQUE,
        subject TEXT,
        issuer TEXT,
        issuer_caref VARCHAR(36),
        serial_number VARCHAR(100),
        aki VARCHAR(200),
        valid_from {ts},
        valid_to {ts},
        served BOOLEAN NOT NULL DEFAULT {false},
        revoked BOOLEAN NOT NULL DEFAULT {false},
        revoked_at {ts},
        revoke_reason VARCHAR(100),
        created_at {ts} DEFAULT CURRENT_TIMESTAMP,
        created_by VARCHAR(80)
    )"""


def _upgrade_sqlite(conn):
    conn.execute(_table('INTEGER PRIMARY KEY AUTOINCREMENT', 'DATETIME', '0'))
    for stmt in _INDEXES:
        conn.execute(stmt)
    exists = conn.execute("SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?",
                          (_BINDINGS,)).fetchone()
    if exists and _COLUMN not in {row[1] for row in conn.execute(f"PRAGMA table_info({_BINDINGS})")}:
        conn.execute(f"ALTER TABLE {_BINDINGS} ADD COLUMN {_COLUMN} VARCHAR(40) NOT NULL DEFAULT 'auto'")
    conn.commit()


def _upgrade_pg(conn):
    from sqlalchemy import inspect, text

    conn.execute(text(_table('SERIAL PRIMARY KEY', 'TIMESTAMP', 'FALSE')))
    for stmt in _INDEXES:
        conn.execute(text(stmt))
    inspector = inspect(conn)
    if _BINDINGS in inspector.get_table_names() and \
            _COLUMN not in {c['name'] for c in inspector.get_columns(_BINDINGS)}:
        conn.execute(text(f"ALTER TABLE {_BINDINGS} ADD COLUMN {_COLUMN} "
                          "VARCHAR(40) NOT NULL DEFAULT 'auto'"))


def upgrade(conn):
    if isinstance(conn, sqlite3.Connection):
        _upgrade_sqlite(conn)
    else:
        _upgrade_pg(conn)
    logger.info("Migration 114: ensured ca_cross_certificates and deploy_bindings.chain_variant")


def downgrade(conn):
    if isinstance(conn, sqlite3.Connection):
        conn.execute(f"DROP TABLE IF EXISTS {TABLE}")
        conn.commit()
    else:
        from sqlalchemy import text
        conn.execute(text(f"DROP TABLE IF EXISTS {TABLE}"))
