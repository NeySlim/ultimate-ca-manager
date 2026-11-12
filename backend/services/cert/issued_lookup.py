"""Which stored certificate a presented certificate is, and whether it may
still act on behalf of its holder.

Protocol renewals (EST /simplereenroll, SCEP RenewalReq, WSTEP renew)
authenticate the request with the certificate being renewed. Serial number
and subject are public, and the serial column mixes decimal and hexadecimal
forms, so each protocol used to answer the question its own way (byte
equality under the CA for WSTEP, decimal serial only for SCEP, nothing at all
for EST). One rule now: the presented certificate must be, byte for byte, a
certificate this CA issued and still holds, not revoked (row or persistent
revocation record) and not expired.
"""

import base64
from datetime import datetime
from typing import Optional, Tuple

from cryptography import x509
from utils.csr_extensions import extensions_of
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives.serialization import Encoding

from models import CA, Certificate, RevokedSerial
from utils.datetime_utils import utc_now
from utils.serial_format import canonical_serial, serial_variants

OK = 'ok'
UNKNOWN = 'unknown'
REVOKED = 'revoked'
EXPIRED = 'expired'
NOT_YET_VALID = 'not_yet_valid'
SUPERSEDED = 'superseded'


def find_issued_rows(ca: CA, cert: x509.Certificate) -> list:
    """Every row under ``ca``, or under another record of its subject and key,
    holding exactly ``cert`` (normally one; a duplicate left by an inconsistent
    restore still counts). Empty when ``ca``'s key did not sign ``cert``: a row
    linked to a CA is not proof that the CA issued what it holds."""
    from utils.cert_issuer import ca_signed, same_key_refids
    rows = _rows_holding(cert, Certificate.caref.in_(same_key_refids(ca)))
    return rows if rows and ca_signed(ca, cert) else []


def find_stored_rows(cert: x509.Certificate) -> list:
    """Every row, under any issuer, holding exactly ``cert``: its serial alone is public."""
    return _rows_holding(cert)


def acme_ordered_first(rows: list) -> list:
    """``rows`` with those an ACME order names first, then by id: a client order names its
    row, or the one its renewal moved off, and says which CA account to tell; a server order
    names the row it issued. A copy stored again never stands in for them."""
    from models.acme_models import AcmeClientOrder, AcmeOrder
    ids = [row.id for row in rows]
    named = set()
    for model in (AcmeClientOrder, AcmeOrder):
        named.update(cid for (cid,) in model.query.with_entities(model.certificate_id)
                     .filter(model.certificate_id.in_(ids)))
    rank = {row.id: 0 if row.id in named else 2 for row in rows}
    for row in rows:
        if row.id in named or not row.serial_number:
            continue
        for order in AcmeClientOrder.query.filter(
                AcmeClientOrder.replaced_certificates.contains(row.serial_number, autoescape=True)):
            if order.names_replaced(row):
                # The id a renewal recorded tells the row it moved from the copies of the same certificate
                recorded = any(e.get('certificate_id') == row.id for e in order._replaced_entries())
                rank[row.id] = min(rank[row.id], 0 if recorded else 1)
    return sorted(rows, key=lambda row: (rank[row.id], row.id))


def _rows_holding(cert: x509.Certificate, *criteria) -> list:
    presented = cert.public_bytes(Encoding.DER)
    candidates = Certificate.query.filter(
        *criteria,
        # Every spelling: rows migration 144 left pending may hold the revoked twin
        Certificate.serial_number.in_(serial_variants(cert.serial_number)),
        Certificate.crt.isnot(None),
    ).all()
    rows = []
    for row in candidates:
        try:
            stored = x509.load_pem_x509_certificate(base64.b64decode(row.crt), default_backend())
        except Exception:
            continue
        if stored.public_bytes(Encoding.DER) == presented:
            rows.append(row)
    return rows


def find_issued_row(ca: CA, cert: x509.Certificate) -> Optional[Certificate]:
    """The row under ``ca`` (or a record of its key) holding exactly ``cert``, or None."""
    rows = find_issued_rows(ca, cert)
    return rows[0] if rows else None


def revocation_order(record):
    """Sort key of a revocation record: a compromise first, then any final revocation,
    then a suspension; between equals the earliest date."""
    from utils.revocation_reasons import REASON_FLAGS
    flag = REASON_FLAGS.get(record.revoke_reason or 'unspecified', x509.ReasonFlags.unspecified)
    rank = {x509.ReasonFlags.key_compromise: 0, x509.ReasonFlags.ca_compromise: 0,
            x509.ReasonFlags.aa_compromise: 0, x509.ReasonFlags.certificate_hold: 2,
            x509.ReasonFlags.remove_from_crl: 3}.get(flag, 1)
    return rank, record.revoked_at or datetime.max, record.id or 0


def record_serial_clause(serial):
    """The records of ``serial``: the column is canonical decimal (migration 144), so only
    equality names it; another serial's all-digit hex spelling never does."""
    return RevokedSerial.serial_number == canonical_serial(serial)


def revocation_records(ca: CA, serial: int) -> list:
    """Every record of ``ca``'s key (or a record of the same subject and key) for
    ``serial`` (``record_serial_clause``), gravest first."""
    from utils.cert_issuer import same_key_refids
    return sorted(RevokedSerial.query.filter(
        RevokedSerial.caref.in_(same_key_refids(ca)),
        record_serial_clause(serial),
    ).all(), key=revocation_order)


def persisted_revocation(ca: CA, serial: int):
    """The record that says ``serial`` is revoked under ``ca``, or None. Any record does,
    whichever row it is linked to: lifting a suspension deletes it."""
    records = revocation_records(ca, serial)
    return records[0] if records else None


def lift_persisted_revocation(ca: CA, serial: int) -> int:
    """Delete every record of ``serial`` under ``ca``'s key (``record_serial_clause``). No commit."""
    from utils.cert_issuer import same_key_refids
    return RevokedSerial.query.filter(
        RevokedSerial.caref.in_(same_key_refids(ca)),
        record_serial_clause(serial),
    ).delete(synchronize_session='fetch')


def _row_serial(row: Certificate) -> Optional[int]:
    try:
        return x509.load_pem_x509_certificate(base64.b64decode(row.crt), default_backend()).serial_number
    except Exception:
        return None


def row_persisted_revocation(row: Certificate, ca: Optional[CA] = None):
    """The record that says ``row``'s certificate is revoked under ``ca`` (default: its
    ``caref``), or None; a row whose certificate cannot be read has none."""
    if ca is None:
        ca = CA.query.filter_by(refid=row.caref).first() if row.caref else None
    if ca is None or not row.crt:
        return None
    serial = _row_serial(row)
    return None if serial is None else persisted_revocation(ca, serial)


def row_revoked(row: Certificate) -> bool:
    """Whether ``row`` is revoked, by its own columns or by the record of its serial."""
    return bool(row.revoked) or row_persisted_revocation(row) is not None


def apply_persisted_revocation(row: Certificate) -> bool:
    """Mark ``row`` revoked from the record its CA still holds for its serial: a certificate
    revoked, deleted and imported again comes back revoked. No commit; returns whether one applied."""
    if row.revoked:
        return False
    record = row_persisted_revocation(row)
    if record is None:
        return False
    row.revoked = True
    row.revoked_at = record.revoked_at
    row.revoke_reason = record.revoke_reason
    row.invalidity_at = record.invalidity_at
    return True


def apply_persisted_revocations() -> int:
    """Mark revoked every linked, unrevoked row holding a serial its CA recorded as revoked
    (rows stored by an earlier release). No commit; returns how many."""
    from sqlalchemy import or_
    # Both columns are canonical (migration 144): a record names the rows of its own serial only
    columns = sorted({column for (column,) in RevokedSerial.query.with_entities(
        RevokedSerial.serial_number).distinct() if column})
    applied = 0
    for start in range(0, len(columns), 500):
        for row in Certificate.query.filter(
                Certificate.serial_number.in_(columns[start:start + 500]),
                Certificate.caref.isnot(None), Certificate.crt.isnot(None),
                or_(Certificate.revoked.is_(False), Certificate.revoked.is_(None))).all():
            applied += apply_persisted_revocation(row)
    return applied


def issued_certificate_status(ca: CA, cert: x509.Certificate) -> Tuple[Optional[Certificate], str]:
    """``(row, status)`` with status one of OK, UNKNOWN, REVOKED, EXPIRED,
    NOT_YET_VALID, SUPERSEDED.

    A certificate revoked and then deleted keeps its persistent revocation
    record, and answers REVOKED rather than UNKNOWN."""
    rows = find_issued_rows(ca, cert)
    row = rows[0] if rows else None
    persistent = persisted_revocation(ca, cert.serial_number)
    if row is None:
        return None, (REVOKED if persistent is not None else UNKNOWN)
    if any(r.revoked for r in rows) or persistent is not None:
        return row, REVOKED
    if all(r.archived for r in rows):
        # Replaced by a renewal: the holder presents the newer certificate,
        # the replaced one must not go on producing certificates
        return row, SUPERSEDED
    # A restored duplicate may sit beside the archived original: the live row answers
    row = next(r for r in rows if not r.archived)
    now = utc_now()
    if cert.not_valid_before_utc.replace(tzinfo=None) > now:
        return row, NOT_YET_VALID
    not_after = cert.not_valid_after_utc.replace(tzinfo=None)
    if not_after <= now or (row.valid_to and row.valid_to < now):
        return row, EXPIRED
    return row, OK


def _san_identity(cert_or_csr):
    try:
        ext = extensions_of(cert_or_csr).get_extension_for_oid(x509.ExtensionOID.SUBJECT_ALTERNATIVE_NAME)
    except x509.ExtensionNotFound:
        return None
    return {(type(name).__name__, str(getattr(name, 'value', name))) for name in ext.value}


def san_identity_matches(cert: x509.Certificate, csr: x509.CertificateSigningRequest) -> bool:
    """A renewal keeps its identity: the CSR's SAN set equals the renewed
    certificate's (order and criticality aside); a CSR without SAN is
    accepted, as on EST re-enrolment."""
    requested = _san_identity(csr)
    if requested is None:
        return True
    return requested == (_san_identity(cert) or set())
