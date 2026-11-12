"""Migration 136: delete the suspension records left behind a lifted hold.

Lifting a hold used to delete only the record of the row's spelling under the row's own
CA, so a record of the same serial in another spelling, or under a twin of the same key,
still linked to the row, outlived it. A record now always says revoked: such a leftover
is deleted once here. A record names the row's serial only in a spelling no other serial
has (``unambiguous_serial_spellings``). Idempotent.

Numbered in a gap 3.0 leaves free: 3.0 tracks migrations by name and skips its own copy
of this cleanup when this one ran, so a hold linked since then survives the upgrade.
"""
import base64
import logging
import sqlite3

from cryptography import x509
from cryptography.hazmat.primitives import serialization

from utils.serial_format import serial_to_int, unambiguous_serial_spellings

pg_compatible = True
logger = logging.getLogger(__name__)

RECORDS = 'revoked_serials'
CERTS = 'certificates'
CAS = 'certificate_authorities'
_CANDIDATES = (
    f"SELECT r.id, r.caref, r.serial_number, c.caref, c.serial_number, c.crt "
    f"FROM {RECORDS} r JOIN {CERTS} c ON c.id = r.certificate_id "
    "WHERE r.revoke_reason IN ('certificateHold', 'certificate_hold') "
    "AND (c.revoked IS NULL OR NOT c.revoked)")


def _key(crt):
    """(subject, public key) of a stored CA certificate, None when unreadable."""
    try:
        cert = x509.load_pem_x509_certificate(base64.b64decode(crt))
        return cert.subject.public_bytes(), cert.public_key().public_bytes(
            serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo)
    except Exception:
        return None


def _row_serial(column, crt):
    """The row's serial: its certificate's, else its column read as ``serial_to_int`` does."""
    if crt:
        try:
            return x509.load_pem_x509_certificate(base64.b64decode(crt)).serial_number
        except Exception:
            pass
    return serial_to_int(column)


def leftovers(candidates, ca_crt) -> list:
    """Ids of the candidates whose record names the row's serial under the row's CA or a
    record of its subject and key; ``ca_crt(refid)`` reads a CA's certificate."""
    keys, ids = {}, []

    def key(refid):
        if refid not in keys:
            crt = ca_crt(refid)
            keys[refid] = _key(crt) if crt else None
        return keys[refid]
    for record_id, record_caref, record_serial, row_caref, row_column, row_crt in candidates:
        if record_caref is None or row_caref is None or not record_serial:
            continue
        serial = _row_serial(row_column, row_crt)
        if serial is None or record_serial not in unambiguous_serial_spellings(serial):
            continue
        if record_caref == row_caref or (key(row_caref) is not None and key(record_caref) == key(row_caref)):
            ids.append(record_id)
    return ids


def _upgrade_sqlite(conn):
    tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
    if not {RECORDS, CERTS, CAS} <= tables:
        return

    def ca_crt(refid):
        row = conn.execute(f"SELECT crt FROM {CAS} WHERE refid = ?", (refid,)).fetchone()
        return row[0] if row else None
    ids = leftovers(conn.execute(_CANDIDATES).fetchall(), ca_crt)
    conn.executemany(f"DELETE FROM {RECORDS} WHERE id = ?", [(i,) for i in ids])
    conn.commit()
    if ids:
        logger.info("Migration 136: %d suspension record(s) of lifted holds deleted", len(ids))


def _upgrade_pg(conn):
    from sqlalchemy import inspect, text

    if not {RECORDS, CERTS, CAS} <= set(inspect(conn).get_table_names()):
        return

    def ca_crt(refid):
        return conn.execute(text(f"SELECT crt FROM {CAS} WHERE refid = :r"), {'r': refid}).scalar()
    ids = leftovers(conn.execute(text(_CANDIDATES)).fetchall(), ca_crt)
    if ids:
        conn.execute(text(f"DELETE FROM {RECORDS} WHERE id = :i"), [{'i': i} for i in ids])
        logger.info("Migration 136: %d suspension record(s) of lifted holds deleted", len(ids))


def upgrade(conn):
    if isinstance(conn, sqlite3.Connection):
        _upgrade_sqlite(conn)
    else:
        _upgrade_pg(conn)


def downgrade(conn):
    pass
