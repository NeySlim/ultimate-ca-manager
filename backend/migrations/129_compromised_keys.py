"""Migration 129: compromised_keys, the keys revoked as compromised whatever CA issued them.

One row per SHA-256 of a SubjectPublicKeyInfo, with no foreign key: deleting a certificate or
a CA never forgets a compromised key. Filled from the certificates revoked as compromised, then
from the revocation records that already know such a key.
"""
import logging
import sqlite3

logger = logging.getLogger(__name__)
pg_compatible = True

TABLE = 'compromised_keys'
# The name SQLAlchemy gives the model's unique=True, index=True, so create_all and this agree
_INDEX = f"CREATE UNIQUE INDEX IF NOT EXISTS ix_{TABLE}_public_key_sha256 ON {TABLE} (public_key_sha256)"
_COMPROMISED = "TRIM(LOWER({column})) IN ('keycompromise', 'key_compromise')"
_FROM_RECORDS = f"""
    INSERT INTO {TABLE} (public_key_sha256, revoked_at, source, created_at)
    SELECT rs.public_key_sha256, MIN(rs.revoked_at), 'local', {{now}}
    FROM revoked_serials rs
    WHERE rs.public_key_sha256 IS NOT NULL AND {_COMPROMISED.format(column='rs.revoke_reason')}
      AND NOT EXISTS (SELECT 1 FROM {TABLE} ck WHERE ck.public_key_sha256 = rs.public_key_sha256)
    GROUP BY rs.public_key_sha256
"""
_NOW = {'sqlite': 'CURRENT_TIMESTAMP', 'pg': "(CURRENT_TIMESTAMP AT TIME ZONE 'UTC')"}
# Read when present: an older schema may lack some of them
_OPTIONAL = ('revoked_at', 'caref', 'source', 'refid', 'subject')


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


def _select_certificates(columns, revoked_true):
    picked = ', '.join(c if c in columns else f'NULL AS {c}' for c in _OPTIONAL)
    return (f"SELECT crt, {picked} FROM certificates WHERE {revoked_true} AND crt IS NOT NULL"
            f" AND {_COMPROMISED.format(column='revoke_reason')}")


def _keys_of(rows):
    """(digest, revoked_at, source, refid, subject) of each readable certificate, once per key."""
    from utils.spki_digest import certificate_key_sha256
    seen = set()
    for crt, revoked_at, caref, source, refid, subject in rows:
        digest = certificate_key_sha256(crt)  # None when unreadable here
        if digest is None or digest in seen:
            continue
        seen.add(digest)
        kind = 'local' if caref else (source if source in ('acme_client', 'msca') else 'external')
        yield digest, revoked_at, kind, refid, subject


def _upgrade_sqlite(conn):
    conn.execute(_table('INTEGER PRIMARY KEY AUTOINCREMENT', 'DATETIME'))
    conn.execute(_INDEX)
    certificates = {row[1] for row in conn.execute("PRAGMA table_info(certificates)")}
    if {'crt', 'revoked', 'revoke_reason'} <= certificates:
        rows = conn.execute(_select_certificates(certificates, 'revoked = 1')).fetchall()
        conn.executemany(
            f"INSERT INTO {TABLE} (public_key_sha256, revoked_at, source, cert_refid, subject, created_at)"
            f" SELECT ?, COALESCE(?, CURRENT_TIMESTAMP), ?, ?, ?, CURRENT_TIMESTAMP"
            f" WHERE NOT EXISTS (SELECT 1 FROM {TABLE} WHERE public_key_sha256 = ?)",
            [(*key, key[0]) for key in _keys_of(rows)])
    records = {row[1] for row in conn.execute("PRAGMA table_info(revoked_serials)")}
    if 'public_key_sha256' in records:
        conn.execute(_FROM_RECORDS.format(now=_NOW['sqlite']))
    conn.commit()


def _upgrade_pg(conn):
    from sqlalchemy import inspect, text

    conn.execute(text(_table('SERIAL PRIMARY KEY', 'TIMESTAMP')))
    conn.execute(text(_INDEX))
    inspector = inspect(conn)
    tables = set(inspector.get_table_names())
    certificates = {c['name'] for c in inspector.get_columns('certificates')} if 'certificates' in tables else set()
    if {'crt', 'revoked', 'revoke_reason'} <= certificates:
        rows = conn.execute(text(_select_certificates(certificates, 'revoked IS TRUE'))).fetchall()
        for digest, revoked_at, kind, refid, subject in _keys_of(rows):
            conn.execute(text(
                f"INSERT INTO {TABLE} (public_key_sha256, revoked_at, source, cert_refid, subject, created_at)"
                f" VALUES (:digest, COALESCE(CAST(:revoked_at AS TIMESTAMP), {_NOW['pg']}), :kind,"
                f" :refid, :subject, {_NOW['pg']})"
                " ON CONFLICT (public_key_sha256) DO NOTHING"),
                {'digest': digest, 'revoked_at': revoked_at, 'kind': kind, 'refid': refid, 'subject': subject})
    if 'revoked_serials' in tables and 'public_key_sha256' in {
            c['name'] for c in inspector.get_columns('revoked_serials')}:
        conn.execute(text(_FROM_RECORDS.format(now=_NOW['pg'])))


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
