"""Migration 132: est_signer_certs, which certificate is the EST key generator of each CA.

That certificate signs the key packages of encrypted serverkeygen answers (RFC 7030 §4.4.2) in
place of the CA, whose certificate may lack digitalSignature. One row per CA, made on first use.
"""
import logging
import sqlite3

logger = logging.getLogger(__name__)
pg_compatible = True

TABLE = 'est_signer_certs'
# The names SQLAlchemy gives the model's unique=True, index=True, so create_all and this agree
_INDEX = f"CREATE UNIQUE INDEX IF NOT EXISTS ix_{TABLE}_ca_id ON {TABLE} (ca_id)"


def _table(pk, ts):
    return f"""
    CREATE TABLE IF NOT EXISTS {TABLE} (
        id {pk},
        ca_id INTEGER NOT NULL REFERENCES certificate_authorities (id) ON DELETE CASCADE,
        certificate_id INTEGER NOT NULL REFERENCES certificates (id) ON DELETE CASCADE,
        issuer_fingerprint VARCHAR(64) NOT NULL,
        created_at {ts}
    )"""


def upgrade(conn):
    if isinstance(conn, sqlite3.Connection):
        conn.execute(_table('INTEGER PRIMARY KEY AUTOINCREMENT', 'DATETIME'))
        conn.execute(_INDEX)
        conn.commit()
    else:
        from sqlalchemy import text
        conn.execute(text(_table('SERIAL PRIMARY KEY', 'TIMESTAMP')))
        conn.execute(text(_INDEX))
    logger.info("Migration 132: ensured est_signer_certs")


def downgrade(conn):
    """No downgrade: the delegates are made again on demand."""
    pass
