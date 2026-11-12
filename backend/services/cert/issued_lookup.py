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
from typing import Optional, Tuple

from cryptography import x509
from utils.csr_extensions import extensions_of
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives.serialization import Encoding

from models import CA, Certificate, RevokedSerial
from utils.datetime_utils import utc_now
from utils.serial_format import serial_variants

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


def _rows_holding(cert: x509.Certificate, *criteria) -> list:
    presented = cert.public_bytes(Encoding.DER)
    candidates = Certificate.query.filter(
        *criteria,
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


def persisted_revocation(ca: CA, serial: int, live: Optional[Certificate] = None):
    """The earliest revocation record of ``ca``'s key for ``serial``, or None. A record
    linked to ``live``, a row that is not revoked, was lifted with it (as on the CRL)."""
    from sqlalchemy import or_
    from utils.cert_issuer import same_key_refids
    query = RevokedSerial.query.filter(
        RevokedSerial.caref.in_(same_key_refids(ca)),
        RevokedSerial.serial_number.in_(serial_variants(serial)),
    )
    if live is not None and live.id is not None:
        query = query.filter(or_(RevokedSerial.certificate_id.is_(None),
                                 RevokedSerial.certificate_id != live.id))
    return query.order_by(RevokedSerial.revoked_at, RevokedSerial.id).first()


def row_persisted_revocation(row: Certificate, ca: Optional[CA] = None):
    """The record that says ``row``'s certificate is revoked under ``ca`` (default: its
    ``caref``), or None; a row whose certificate cannot be read has none."""
    if ca is None:
        ca = CA.query.filter_by(refid=row.caref).first() if row.caref else None
    if ca is None or not row.crt:
        return None
    try:
        serial = x509.load_pem_x509_certificate(base64.b64decode(row.crt), default_backend()).serial_number
    except Exception:
        return None
    return persisted_revocation(ca, serial, live=row)


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


def issued_certificate_status(ca: CA, cert: x509.Certificate) -> Tuple[Optional[Certificate], str]:
    """``(row, status)`` with status one of OK, UNKNOWN, REVOKED, EXPIRED,
    NOT_YET_VALID, SUPERSEDED.

    A certificate revoked and then deleted keeps its persistent revocation
    record, and answers REVOKED rather than UNKNOWN."""
    rows = find_issued_rows(ca, cert)
    row = rows[0] if rows else None
    variants = serial_variants(cert.serial_number)
    from utils.cert_issuer import same_key_refids
    persistent = RevokedSerial.query.filter(
        RevokedSerial.caref.in_(same_key_refids(ca)),
        RevokedSerial.serial_number.in_(variants),
    ).first()
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
