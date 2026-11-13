"""Migration 157: certificates.subject_key and its index with caref.

``subject_key`` is ``utils.dn_match.name_key`` of the certificate's subject, filled from ``crt``
here once and by the listener on every write after: an issuance under a common name pattern
finds the certificates of its CA carrying the same subject through the index, never a scan.
Idempotent, dual-backend (SQLite + PostgreSQL).
"""
import sqlite3

pg_compatible = True

INDEX = 'ix_certificates_caref_subject_key'
_PENDING = ("SELECT id, crt FROM certificates WHERE crt IS NOT NULL AND crt <> '' "
            "AND subject_key IS NULL AND id > {cursor} ORDER BY id")
_BATCH = 500


def _values(rows):
    """(subject_key, id) for the rows whose certificate can be read."""
    import base64
    from cryptography import x509
    from utils.dn_match import name_key
    out = []
    for row_id, crt in rows:
        try:
            out.append((name_key(x509.load_pem_x509_certificate(base64.b64decode(crt)).subject), row_id))
        except Exception:
            continue  # unreadable rows stay NULL, as the write path leaves them
    return out


def _backfill(fetch, write):
    """Batches of _BATCH rows, keyed on id so a row nothing can fill is read once."""
    cursor = 0
    while True:
        rows = fetch(cursor)
        if not rows:
            return
        cursor = rows[-1][0]
        values = _values(rows)
        if values:
            write(values)


def _upgrade_sqlite(conn):
    tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
    if 'certificates' not in tables:
        return
    if 'subject_key' not in {row[1] for row in conn.execute("PRAGMA table_info(certificates)")}:
        conn.execute("ALTER TABLE certificates ADD COLUMN subject_key VARCHAR(64)")
    _backfill(
        lambda c: conn.execute(_PENDING.format(cursor=int(c)) + f" LIMIT {_BATCH}").fetchall(),
        lambda values: conn.executemany("UPDATE certificates SET subject_key = ? WHERE id = ?", values))
    conn.execute(f"CREATE INDEX IF NOT EXISTS {INDEX} ON certificates (caref, subject_key)")
    conn.commit()


def _upgrade_pg(conn):
    from sqlalchemy import bindparam, inspect, text
    if 'certificates' not in set(inspect(conn).get_table_names()):
        return
    if 'subject_key' not in {c['name'] for c in inspect(conn).get_columns('certificates')}:
        conn.execute(text("ALTER TABLE certificates ADD COLUMN subject_key VARCHAR(64)"))
    update = text("UPDATE certificates SET subject_key = :key WHERE id = :id").bindparams(
        bindparam('key'), bindparam('id'))
    _backfill(
        lambda c: conn.execute(text(_PENDING.format(cursor=int(c)) + f" LIMIT {_BATCH}")).fetchall(),
        lambda values: conn.execute(update, [{'key': k, 'id': i} for k, i in values]))
    conn.execute(text(f"CREATE INDEX IF NOT EXISTS {INDEX} ON certificates (caref, subject_key)"))


def upgrade(conn):
    if isinstance(conn, sqlite3.Connection):
        _upgrade_sqlite(conn)
    else:
        _upgrade_pg(conn)


def downgrade(conn):
    """No downgrade: the column and the index are harmless to older versions."""
    pass
