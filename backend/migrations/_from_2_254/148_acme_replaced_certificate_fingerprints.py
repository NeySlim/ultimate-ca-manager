"""Upgrade step 148: the certificates an ACME order's renewals moved off, named by fingerprint.

Entries of ``acme_client_orders.replaced_certificates`` written before it name a row by
number, which a restore on another installation changes; each gets the SHA-256
fingerprint of the row it still names here (same id and serial). Running it again
changes nothing.
"""
import base64
import json
import logging
import sqlite3

logger = logging.getLogger(__name__)
pg_compatible = True

ORDERS = 'acme_client_orders'
_ORDERS = (f"SELECT id, replaced_certificates FROM {ORDERS} "
           "WHERE replaced_certificates IS NOT NULL AND replaced_certificates <> ''")


def fingerprint(crt):
    """Lower-case hex SHA-256 of the stored certificate (base64 of a PEM), or None."""
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes
    try:
        return x509.load_pem_x509_certificate(base64.b64decode(crt)).fingerprint(hashes.SHA256()).hex()
    except Exception:
        return None


def rewrite(text, certificate):
    """The entries with a fingerprint added where ``certificate(id)`` gives (serial, crt), or None."""
    try:
        entries = json.loads(text)
    except ValueError:
        return None
    if not isinstance(entries, list):
        return None
    changed = False
    for entry in entries:
        if not isinstance(entry, dict) or entry.get('fingerprint') or entry.get('certificate_id') is None:
            continue
        row = certificate(entry['certificate_id'])
        if row is None or row[0] != entry.get('serial'):
            continue
        value = fingerprint(row[1]) if row[1] else None
        if value:
            entry['fingerprint'] = value
            changed = True
    return json.dumps(entries) if changed else None


def _tables_sqlite(conn):
    return {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}


def _upgrade_sqlite(conn):
    if not {ORDERS, 'certificates'} <= _tables_sqlite(conn):
        return
    if 'replaced_certificates' not in {r[1] for r in conn.execute(f"PRAGMA table_info({ORDERS})")}:
        return

    def certificate(cert_id):
        return conn.execute('SELECT serial_number, crt FROM certificates WHERE id = ?',
                            (cert_id,)).fetchone()

    for order_id, text in conn.execute(_ORDERS).fetchall():
        value = rewrite(text, certificate)
        if value is not None:
            conn.execute(f'UPDATE {ORDERS} SET replaced_certificates = ? WHERE id = ?',
                         (value, order_id))
    conn.commit()


def _upgrade_pg(conn):
    from sqlalchemy import inspect, text

    inspector = inspect(conn)
    if not {ORDERS, 'certificates'} <= set(inspector.get_table_names()):
        return
    if 'replaced_certificates' not in {c['name'] for c in inspector.get_columns(ORDERS)}:
        return

    def certificate(cert_id):
        return conn.execute(text('SELECT serial_number, crt FROM certificates WHERE id = :id'),
                            {'id': cert_id}).fetchone()

    for order_id, value in conn.execute(text(_ORDERS)).fetchall():
        value = rewrite(value, certificate)
        if value is not None:
            conn.execute(text(f'UPDATE {ORDERS} SET replaced_certificates = :v WHERE id = :id'),
                         {'v': value, 'id': order_id})


def upgrade(conn):
    if isinstance(conn, sqlite3.Connection):
        _upgrade_sqlite(conn)
    else:
        _upgrade_pg(conn)


def downgrade(conn):
    """No downgrade: older versions ignore the extra key."""
