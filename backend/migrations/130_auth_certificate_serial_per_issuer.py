"""Migration 130: an mTLS enrolment's serial is unique per issuer, not globally.

X.509 guarantees a serial number only within its issuer (RFC 5280 §4.1.2.2):
the unique index on ``auth_certificates.cert_serial`` refused a second CA's
certificate that happened to share it. The issuer is first filled from the
stored PEM where it was missing (``''`` when unreadable, never NULL, so the
new ``UNIQUE (cert_issuer, cert_serial)`` index still holds every row).
"""
import logging
import sqlite3

logger = logging.getLogger(__name__)
pg_compatible = True

TABLE = 'auth_certificates'
# The names the model gives them, so create_all and this agree
_UNIQUE = f"CREATE UNIQUE INDEX IF NOT EXISTS uq_{TABLE}_issuer_serial ON {TABLE} (cert_issuer, cert_serial)"
_SERIAL = f"CREATE INDEX IF NOT EXISTS ix_{TABLE}_cert_serial ON {TABLE} (cert_serial)"
_FINGERPRINT = f"CREATE INDEX IF NOT EXISTS ix_{TABLE}_cert_fingerprint ON {TABLE} (cert_fingerprint)"

_SQLITE_TABLE = f"""
CREATE TABLE _{TABLE}_new (
    id INTEGER PRIMARY KEY NOT NULL,
    user_id INTEGER NOT NULL,
    cert_serial VARCHAR(128) NOT NULL,
    cert_subject TEXT NOT NULL,
    cert_issuer TEXT,
    cert_fingerprint VARCHAR(128),
    name VARCHAR(128),
    enabled BOOLEAN NOT NULL,
    valid_from DATETIME,
    valid_until DATETIME,
    created_at DATETIME,
    last_used_at DATETIME,
    cert_pem BLOB,
    FOREIGN KEY(user_id) REFERENCES users(id)
)"""
_COLUMNS = ('id', 'user_id', 'cert_serial', 'cert_subject', 'cert_issuer', 'cert_fingerprint', 'name',
            'enabled', 'valid_from', 'valid_until', 'created_at', 'last_used_at', 'cert_pem')


def _issuer_of(pem):
    from cryptography import x509
    try:
        return x509.load_pem_x509_certificate(bytes(pem)).issuer.rfc4514_string()
    except Exception:
        return None


def _missing_issuers(rows):
    """(issuer, id) for each row without an issuer: the PEM's, else ''."""
    for row_id, pem in rows:
        yield (_issuer_of(pem) if pem else None) or '', row_id


def _upgrade_sqlite(conn):
    if conn.execute("SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?", (TABLE,)).fetchone() is None:
        return
    rows = conn.execute(f"SELECT id, cert_pem FROM {TABLE} WHERE cert_issuer IS NULL OR cert_issuer = ''").fetchall()
    conn.executemany(f"UPDATE {TABLE} SET cert_issuer = ? WHERE id = ?", list(_missing_issuers(rows)))

    rebuild = False
    for _seq, name, unique, origin, *_ in conn.execute(f"PRAGMA index_list({TABLE})").fetchall():
        columns = [r[2] for r in conn.execute(f'PRAGMA index_info("{name}")')]
        if not unique or columns != ['cert_serial']:
            continue
        if origin == 'c':
            conn.execute(f'DROP INDEX "{name}"')
        else:  # a column-level UNIQUE: SQLite cannot drop it, the table is rebuilt
            rebuild = True
    if rebuild:
        present = {r[1] for r in conn.execute(f"PRAGMA table_info({TABLE})")}
        copied = ', '.join(c for c in _COLUMNS if c in present)
        conn.execute(_SQLITE_TABLE)
        conn.execute(f"INSERT INTO _{TABLE}_new ({copied}) SELECT {copied} FROM {TABLE}")
        conn.execute(f"DROP TABLE {TABLE}")
        conn.execute(f"ALTER TABLE _{TABLE}_new RENAME TO {TABLE}")
        conn.execute(_FINGERPRINT)
    conn.execute(_SERIAL)
    conn.execute(_UNIQUE)
    conn.commit()
    logger.info("[130] auth_certificates serial unique per issuer (SQLite)")


def _upgrade_pg(conn):
    from sqlalchemy import inspect, text

    inspector = inspect(conn)
    if TABLE not in set(inspector.get_table_names()):
        return
    rows = conn.execute(text(
        f"SELECT id, cert_pem FROM {TABLE} WHERE cert_issuer IS NULL OR cert_issuer = ''")).fetchall()
    for issuer, row_id in _missing_issuers(rows):
        conn.execute(text(f"UPDATE {TABLE} SET cert_issuer = :issuer WHERE id = :id"),
                     {'issuer': issuer, 'id': row_id})

    for constraint in inspector.get_unique_constraints(TABLE):
        if constraint.get('column_names') == ['cert_serial'] and constraint.get('name'):
            conn.execute(text(f'ALTER TABLE {TABLE} DROP CONSTRAINT IF EXISTS "{constraint["name"]}"'))
    for index in inspector.get_indexes(TABLE):
        if index.get('unique') and index.get('column_names') == ['cert_serial'] and index.get('name'):
            conn.execute(text(f'DROP INDEX IF EXISTS "{index["name"]}"'))
    conn.execute(text(_SERIAL))
    conn.execute(text(_UNIQUE))
    logger.info("[130] auth_certificates serial unique per issuer (PostgreSQL)")


def upgrade(conn):
    if isinstance(conn, sqlite3.Connection):
        _upgrade_sqlite(conn)
    else:
        _upgrade_pg(conn)


def downgrade(conn):
    """No downgrade: two issuers may hold the same serial once this has run."""
    pass
