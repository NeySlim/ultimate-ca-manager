"""Upgrade step 157: certificates.subject_key and its index with caref, certificates.subject_holder,
certificate_authorities.enforce_unique_subject.

``subject_key`` is ``utils.dn_match.name_key`` of the certificate's subject, filled from ``crt``
here once and by the listener on every write after: an issuance checked for a unique subject
finds the certificates of its CA carrying the same subject through the index, never a scan.
``subject_holder`` names who the subject was certified to; an ACME certificate takes its order's
account here, and the post-quantum member of an RFC 9763 pair the lineage of the classical one it
names, found through the index of acme_orders.certificate_id. ``enforce_unique_subject`` starts
off on every CA.
Idempotent, dual-backend (SQLite + PostgreSQL).
"""
import sqlite3

pg_compatible = True

INDEX = 'ix_certificates_caref_subject_key'
# The holders below find a certificate's orders through it, never by a scan per certificate
ORDER_INDEX = 'ix_acme_orders_certificate_id'
CREATE_ORDER_INDEX = f"CREATE INDEX IF NOT EXISTS {ORDER_INDEX} ON acme_orders (certificate_id)"
_PENDING = ("SELECT id, crt FROM certificates WHERE crt IS NOT NULL AND crt <> '' "
            "AND subject_key IS NULL AND id > {cursor} ORDER BY id")
_BATCH = 500
# The account of the order a certificate was issued for (the lowest order id when several name it)
_ACME_HOLDERS = ("UPDATE certificates SET subject_holder = 'acme:' || (SELECT o.account_id FROM acme_orders o "
                 "WHERE o.certificate_id = certificates.id ORDER BY o.id LIMIT 1) "
                 "WHERE subject_holder IS NULL AND EXISTS "
                 "(SELECT 1 FROM acme_orders o WHERE o.certificate_id = certificates.id)")
# B of a hybrid pair is the entity of the A it names (one issuance, one subject)
_PAIR_HOLDERS = ("UPDATE certificates SET subject_holder = 'cert:' || (SELECT a.refid FROM certificates a "
                 "WHERE a.id = certificates.related_certificate_id) "
                 "WHERE subject_holder IS NULL AND hybrid_role = 'pq' AND related_certificate_id IS NOT NULL "
                 "AND EXISTS (SELECT 1 FROM certificates a WHERE a.id = certificates.related_certificate_id)")


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
    columns = {row[1] for row in conn.execute("PRAGMA table_info(certificates)")}
    if 'subject_key' not in columns:
        conn.execute("ALTER TABLE certificates ADD COLUMN subject_key VARCHAR(64)")
    if 'subject_holder' not in columns:
        conn.execute("ALTER TABLE certificates ADD COLUMN subject_holder VARCHAR(100)")
    _backfill(
        lambda c: conn.execute(_PENDING.format(cursor=int(c)) + f" LIMIT {_BATCH}").fetchall(),
        lambda values: conn.executemany("UPDATE certificates SET subject_key = ? WHERE id = ?", values))
    conn.execute(f"CREATE INDEX IF NOT EXISTS {INDEX} ON certificates (caref, subject_key)")
    if 'acme_orders' in tables:
        conn.execute(CREATE_ORDER_INDEX)
        conn.execute(_ACME_HOLDERS)
    if {'hybrid_role', 'related_certificate_id'} <= columns:
        conn.execute(_PAIR_HOLDERS)
    if 'certificate_authorities' in tables and 'enforce_unique_subject' not in {
            row[1] for row in conn.execute("PRAGMA table_info(certificate_authorities)")}:
        conn.execute("ALTER TABLE certificate_authorities ADD COLUMN enforce_unique_subject "
                     "BOOLEAN NOT NULL DEFAULT 0")
    conn.commit()


def _upgrade_pg(conn):
    from sqlalchemy import bindparam, inspect, text
    tables = set(inspect(conn).get_table_names())
    if 'certificates' not in tables:
        return
    columns = {c['name'] for c in inspect(conn).get_columns('certificates')}
    if 'subject_key' not in columns:
        conn.execute(text("ALTER TABLE certificates ADD COLUMN subject_key VARCHAR(64)"))
    if 'subject_holder' not in columns:
        conn.execute(text("ALTER TABLE certificates ADD COLUMN subject_holder VARCHAR(100)"))
    update = text("UPDATE certificates SET subject_key = :key WHERE id = :id").bindparams(
        bindparam('key'), bindparam('id'))
    _backfill(
        lambda c: conn.execute(text(_PENDING.format(cursor=int(c)) + f" LIMIT {_BATCH}")).fetchall(),
        lambda values: conn.execute(update, [{'key': k, 'id': i} for k, i in values]))
    conn.execute(text(f"CREATE INDEX IF NOT EXISTS {INDEX} ON certificates (caref, subject_key)"))
    if 'acme_orders' in tables:
        conn.execute(text(CREATE_ORDER_INDEX))
        conn.execute(text(_ACME_HOLDERS))
    if {'hybrid_role', 'related_certificate_id'} <= columns:
        conn.execute(text(_PAIR_HOLDERS))
    if 'certificate_authorities' in tables and 'enforce_unique_subject' not in {
            c['name'] for c in inspect(conn).get_columns('certificate_authorities')}:
        conn.execute(text("ALTER TABLE certificate_authorities ADD COLUMN enforce_unique_subject "
                          "BOOLEAN NOT NULL DEFAULT FALSE"))


def upgrade(conn):
    if isinstance(conn, sqlite3.Connection):
        _upgrade_sqlite(conn)
    else:
        _upgrade_pg(conn)


def downgrade(conn):
    """No downgrade: the columns and the index are harmless to older versions."""
    pass
