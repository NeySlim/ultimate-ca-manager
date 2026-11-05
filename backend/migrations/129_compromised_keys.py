"""Migration 129: compromised_keys, the keys revoked as compromised whatever CA issued them.

One row per SHA-256 of a SubjectPublicKeyInfo, with no foreign key: deleting a certificate or
a CA never forgets a compromised key. Filled from the revocation records that already know one.
"""
import logging
import sqlite3

logger = logging.getLogger(__name__)
pg_compatible = True

TABLE = 'compromised_keys'
# The name SQLAlchemy gives the model's unique=True, index=True, so create_all and this agree
_INDEX = f"CREATE UNIQUE INDEX IF NOT EXISTS ix_{TABLE}_public_key_sha256 ON {TABLE} (public_key_sha256)"
_BACKFILL = f"""
    INSERT INTO {TABLE} (public_key_sha256, revoked_at, source, created_at)
    SELECT rs.public_key_sha256, MIN(rs.revoked_at), 'local', CURRENT_TIMESTAMP
    FROM revoked_serials rs
    WHERE rs.public_key_sha256 IS NOT NULL
      AND LOWER(rs.revoke_reason) IN ('keycompromise', 'key_compromise')
      AND NOT EXISTS (SELECT 1 FROM {TABLE} ck WHERE ck.public_key_sha256 = rs.public_key_sha256)
    GROUP BY rs.public_key_sha256
"""


def _table(pk, ts):
    return f"""
    CREATE TABLE IF NOT EXISTS {TABLE} (
        id {pk},
        public_key_sha256 VARCHAR(64) NOT NULL,
        revoked_at {ts} NOT NULL,
        source VARCHAR(20) NOT NULL,
        cert_refid VARCHAR(36),
        subject TEXT,
        created_at {ts}
    )"""


def _upgrade_sqlite(conn):
    conn.execute(_table('INTEGER PRIMARY KEY AUTOINCREMENT', 'DATETIME'))
    conn.execute(_INDEX)
    columns = {row[1] for row in conn.execute("PRAGMA table_info(revoked_serials)")}
    if 'public_key_sha256' in columns:
        conn.execute(_BACKFILL)
    conn.commit()


def _upgrade_pg(conn):
    from sqlalchemy import inspect, text

    conn.execute(text(_table('SERIAL PRIMARY KEY', 'TIMESTAMP')))
    conn.execute(text(_INDEX))
    inspector = inspect(conn)
    if 'revoked_serials' in inspector.get_table_names() and 'public_key_sha256' in {
            c['name'] for c in inspector.get_columns('revoked_serials')}:
        conn.execute(text(_BACKFILL))


def upgrade(conn):
    if isinstance(conn, sqlite3.Connection):
        _upgrade_sqlite(conn)
    else:
        _upgrade_pg(conn)
    logger.info("Migration 129: ensured compromised_keys")


def downgrade(conn):
    if isinstance(conn, sqlite3.Connection):
        conn.execute(f"DROP TABLE IF EXISTS {TABLE}")
        conn.commit()
    else:
        from sqlalchemy import text
        conn.execute(text(f"DROP TABLE IF EXISTS {TABLE}"))
