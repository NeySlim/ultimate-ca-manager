"""
Migration 027: Backfill san_email (and san_dns / san_ip / san_uri) from
the stored X.509 certificate for any row where the DB column is out of sync.

Root cause: certificates.py used data.get('san_email', []) when writing
san_email to the DB.  Auto-added SANs (CN → RFC822Name for email/combined
certs, subject email → RFC822Name) were inserted into the X.509 extension
but the DB column was never updated to match, leaving it as '[]' or NULL.

This migration re-derives all four SAN columns from the actual certificate
for every row in the certificates table and writes the corrected values.
Rows where all four columns already match are left untouched.

Multi-backend: runs on both SQLite and PostgreSQL.
"""
import base64
import json
import logging
import sqlite3

logger = logging.getLogger(__name__)
pg_compatible = True


def _extract_sans(pem_b64: str):
    """Return (dns, ip, email, uri) lists from a base64-encoded PEM cert."""
    from cryptography import x509
    try:
        pem = base64.b64decode(pem_b64)
        cert = x509.load_pem_x509_certificate(pem)
    except Exception:
        return None, None, None, None

    try:
        san_ext = cert.extensions.get_extension_for_class(x509.SubjectAlternativeName)
        dns = [n.value for n in san_ext.value if isinstance(n, x509.DNSName)]
        ip = [str(n.value) for n in san_ext.value if isinstance(n, x509.IPAddress)]
        email = [n.value for n in san_ext.value if isinstance(n, x509.RFC822Name)]
        uri = [n.value for n in san_ext.value if isinstance(n, x509.UniformResourceIdentifier)]
    except x509.ExtensionNotFound:
        dns, ip, email, uri = [], [], [], []

    return dns, ip, email, uri


def _backfill(rows, update_fn):
    """Core logic shared between SQLite and PostgreSQL paths."""
    updated = 0
    skipped = 0

    for row in rows:
        cert_id, crt, db_dns, db_ip, db_email, db_uri = row

        if not crt:
            skipped += 1
            continue

        dns, ip, email, uri = _extract_sans(crt)
        if dns is None:
            skipped += 1
            continue

        def _load(v):
            if not v:
                return []
            try:
                return json.loads(v)
            except Exception:
                return []

        needs_update = (
            sorted(_load(db_dns)) != sorted(dns) or
            sorted(_load(db_ip)) != sorted(ip) or
            sorted(_load(db_email)) != sorted(email) or
            sorted(_load(db_uri)) != sorted(uri)
        )

        if needs_update:
            update_fn(cert_id, dns, ip, email, uri)
            updated += 1
        else:
            skipped += 1

    logger.info(f"Migration 027: updated {updated} rows, {skipped} already correct / skipped")


def _upgrade_sqlite(conn):
    cur = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='certificates'"
    )
    if not cur.fetchone():
        logger.info("Migration 027: certificates table absent, skipping")
        return

    rows = conn.execute(
        "SELECT id, crt, san_dns, san_ip, san_email, san_uri FROM certificates"
    ).fetchall()

    def update_fn(cert_id, dns, ip, email, uri):
        conn.execute(
            "UPDATE certificates SET san_dns=?, san_ip=?, san_email=?, san_uri=? WHERE id=?",
            (json.dumps(dns), json.dumps(ip), json.dumps(email), json.dumps(uri), cert_id)
        )

    _backfill(rows, update_fn)
    conn.commit()


def _upgrade_pg(engine):
    from sqlalchemy import inspect, text

    insp = inspect(engine)
    if 'certificates' not in set(insp.get_table_names()):
        logger.info("Migration 027: certificates table absent, skipping")
        return

    with engine.begin() as conn:
        result = conn.execute(text(
            "SELECT id, crt, san_dns, san_ip, san_email, san_uri FROM certificates"
        ))
        rows = result.fetchall()

        def update_fn(cert_id, dns, ip, email, uri):
            conn.execute(text(
                "UPDATE certificates SET san_dns=:dns, san_ip=:ip, san_email=:email, san_uri=:uri WHERE id=:id"
            ), {"dns": json.dumps(dns), "ip": json.dumps(ip), "email": json.dumps(email), "uri": json.dumps(uri), "id": cert_id})

        _backfill(rows, update_fn)


def upgrade(conn):
    if isinstance(conn, sqlite3.Connection):
        _upgrade_sqlite(conn)
    else:
        _upgrade_pg(conn)


def downgrade(conn):
    pass
