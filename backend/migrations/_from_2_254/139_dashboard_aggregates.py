"""Upgrade step 139: columns and indexes for the dashboard aggregates.

``certificates.key_bits`` and ``certificates.sig_hash`` hold the key size and
the signature hash, filled from ``crt`` here once and on every write after, so
the compliance counters never parse a certificate. The indexes serve the
expiry window and the issuance range on certificates, and the recently
failed ACME orders.
"""
import sqlite3

pg_compatible = True

COLUMNS = (('key_bits', 'INTEGER'), ('sig_hash', 'VARCHAR(20)'))
INDEXES = (
    ('certificates', 'ix_certificates_valid_to', ('valid_to',)),
    ('certificates', 'ix_certificates_created_at', ('created_at',)),
    ('acme_orders', 'ix_acme_orders_status_created_at', ('status', 'created_at')),
)
_PENDING = ("SELECT id, crt FROM certificates WHERE crt IS NOT NULL AND crt <> '' "
            "AND key_bits IS NULL AND sig_hash IS NULL AND id > {cursor} ORDER BY id")
_UPDATE = "UPDATE certificates SET key_bits = {p}, sig_hash = {p} WHERE id = {p}"
_BATCH = 500


def _values(rows):
    """(key_bits, sig_hash, id) for the rows whose certificate can be read."""
    import base64
    from cryptography import x509
    from models.certificate import key_bits_for_certificate, sig_hash_for_certificate
    out = []
    for row_id, crt in rows:
        try:
            cert = x509.load_pem_x509_certificate(base64.b64decode(crt))
        except Exception:
            continue  # unreadable rows stay NULL, as the write path leaves them
        try:
            bits = key_bits_for_certificate(cert)
        except Exception:
            bits = None
        out.append((bits, sig_hash_for_certificate(cert), row_id))
    return out


def _backfill(fetch, write):
    """Batches of _BATCH rows, keyed on id so a row nothing can fill is read once."""
    cursor = 0
    while True:
        rows = fetch(cursor)
        if not rows:
            return
        cursor = rows[-1][0]
        values = [v for v in _values(rows) if v[0] is not None or v[1] is not None]
        if values:
            write(values)


def _upgrade_sqlite(conn):
    tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
    if 'certificates' in tables:
        present = {row[1] for row in conn.execute("PRAGMA table_info(certificates)")}
        for name, sql_type in COLUMNS:
            if name not in present:
                conn.execute(f"ALTER TABLE certificates ADD COLUMN {name} {sql_type}")
        _backfill(
            lambda c: conn.execute(_PENDING.format(cursor=int(c)) + f" LIMIT {_BATCH}").fetchall(),
            lambda values: conn.executemany(_UPDATE.format(p='?'), values))
    for table, index, cols in INDEXES:
        if table in tables:
            conn.execute(f"CREATE INDEX IF NOT EXISTS {index} ON {table} ({', '.join(cols)})")
    conn.commit()


def _upgrade_pg(conn):
    from sqlalchemy import bindparam, inspect, text

    tables = set(inspect(conn).get_table_names())
    if 'certificates' in tables:
        present = {c['name'] for c in inspect(conn).get_columns('certificates')}
        for name, sql_type in COLUMNS:
            if name not in present:
                conn.execute(text(f"ALTER TABLE certificates ADD COLUMN {name} {sql_type}"))
        update = text("UPDATE certificates SET key_bits = :bits, sig_hash = :hash WHERE id = :id").bindparams(
            bindparam('bits'), bindparam('hash'), bindparam('id'))
        _backfill(
            lambda c: conn.execute(text(_PENDING.format(cursor=int(c)) + f" LIMIT {_BATCH}")).fetchall(),
            lambda values: conn.execute(update, [{'bits': b, 'hash': h, 'id': i} for b, h, i in values]))
    for table, index, cols in INDEXES:
        if table in tables:
            conn.execute(text(f"CREATE INDEX IF NOT EXISTS {index} ON {table} ({', '.join(cols)})"))


def upgrade(conn):
    if isinstance(conn, sqlite3.Connection):
        _upgrade_sqlite(conn)
    else:
        _upgrade_pg(conn)


def downgrade(conn):
    """No downgrade: the columns and indexes are harmless to older versions."""
    pass
