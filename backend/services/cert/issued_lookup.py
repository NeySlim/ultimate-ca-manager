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


def find_issued_rows(ca: CA, cert: x509.Certificate) -> list:
    """Every row under ``ca`` holding exactly ``cert`` (normally one; a
    duplicate left by an inconsistent restore still counts)."""
    presented = cert.public_bytes(Encoding.DER)
    candidates = Certificate.query.filter(
        Certificate.caref == ca.refid,
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
    """The row under ``ca`` holding exactly ``cert``, or None."""
    rows = find_issued_rows(ca, cert)
    return rows[0] if rows else None


def issued_certificate_status(ca: CA, cert: x509.Certificate) -> Tuple[Optional[Certificate], str]:
    """``(row, status)`` with status one of OK, UNKNOWN, REVOKED, EXPIRED.

    A certificate revoked and then deleted keeps its persistent revocation
    record, and answers REVOKED rather than UNKNOWN."""
    rows = find_issued_rows(ca, cert)
    row = rows[0] if rows else None
    variants = serial_variants(cert.serial_number)
    persistent = RevokedSerial.query.filter(
        RevokedSerial.caref == ca.refid,
        RevokedSerial.serial_number.in_(variants),
    ).first()
    if row is None:
        return None, (REVOKED if persistent is not None else UNKNOWN)
    if any(r.revoked for r in rows) or persistent is not None:
        return row, REVOKED
    now = utc_now()
    if cert.not_valid_before_utc.replace(tzinfo=None) > now:
        return row, NOT_YET_VALID
    not_after = cert.not_valid_after_utc.replace(tzinfo=None)
    if not_after <= now or (row.valid_to and row.valid_to < now):
        return row, EXPIRED
    return row, OK


def _san_identity(cert_or_csr):
    try:
        ext = cert_or_csr.extensions.get_extension_for_oid(x509.ExtensionOID.SUBJECT_ALTERNATIVE_NAME)
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
