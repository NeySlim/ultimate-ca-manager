"""What an mTLS enrolment (an ``AuthCertificate`` row) is bound to.

An enrolment names a certificate; the private key that may travel with it
(PKCS#12, PEM or JKS export) belongs to exactly one ``Certificate`` row. Every
route that joins the two used to do so by serial number alone, so any
authenticated user could enrol a forged certificate bearing another record's
serial and export that record's key. The lookup here is shared by the mTLS
account routes and the user-certificates routes so the rule cannot drift.
"""

import base64
import hashlib
import logging
from typing import Optional, Tuple

from cryptography import x509
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import serialization

from models import CA, Certificate
from utils.serial_format import serial_variants

logger = logging.getLogger(__name__)


def normalized_fingerprint(value) -> Optional[Tuple[str, str]]:
    """``(algorithm, HEX)`` for a stored or presented fingerprint, or None.

    Proxies present SHA-1 (nginx ``$ssl_client_fingerprint``, 40 hex digits)
    as readily as SHA-256 (64); colons and case vary. Anything else is
    ignored rather than trusted.
    """
    if not value:
        return None
    digits = ''.join(ch for ch in str(value) if ch not in ': ').upper()
    if len(digits) == 40:
        return 'sha1', digits
    if len(digits) == 64:
        return 'sha256', digits
    return None


def _fingerprint(der: bytes, algorithm: str) -> str:
    return (hashlib.sha1(der) if algorithm == 'sha1' else hashlib.sha256(der)).hexdigest().upper()


def _load(pem) -> Optional[x509.Certificate]:
    if not pem:
        return None
    try:
        return x509.load_pem_x509_certificate(bytes(pem), default_backend())
    except Exception:
        return None


def parse_validity_days(value, default: int = 365) -> Optional[int]:
    """An integer number of days within the issuance bounds, or None when the
    value is not exactly that (booleans, fractions and free text included).

    The shape rule lives in :mod:`utils.validity` now, where the other
    issuance doors read it from too: this was the only one that refused a
    JSON boolean, so the same body was a 400 here and a one-day certificate
    at ``POST /api/v2/certificates``."""
    from utils.validity import coerce_validity_days, validity_days_in_range

    if value is None:
        value = default
    days = coerce_validity_days(value)
    if days is None or not validity_days_in_range(days):
        return None
    return days


def issuing_ca_for(cert: x509.Certificate) -> Optional[CA]:
    """The CA row that really signed ``cert`` (signature verified), or None.

    Enrolling a certificate no CA of this server issued proves nothing and
    only serves to squat a serial number: the mTLS trusted CA is always one
    of the server's CAs, so such a certificate could never authenticate.
    """
    issuer_dn = cert.issuer.rfc4514_string()
    for ca in CA.query.filter(CA.subject == issuer_dn).all():
        ca_cert = _load(base64.b64decode(ca.crt)) if ca.crt else None
        if ca_cert is None:
            continue
        try:
            cert.verify_directly_issued_by(ca_cert)
            return ca
        except Exception:
            continue
    return None


def certificate_row_for(auth_cert) -> Optional[Certificate]:
    """The ``Certificate`` row an enrolment is bound to, or None.

    The row must be the very certificate that was enrolled: byte-identical
    to the stored PEM when the enrolment kept one, else matching its
    fingerprint, else (enrolments made before either was stored) carrying
    the same serial number AND issuer, the serial being read back from the
    row's own certificate so that a decimal string and a hexadecimal one
    never designate two different certificates. The stored serial is read
    as decimal first; hexadecimal is tried only when no row exists for the
    decimal reading.
    """
    raw = (auth_cert.cert_serial or '').strip()
    enrolled = _load(auth_cert.cert_pem)
    enrolled_der = enrolled.public_bytes(serialization.Encoding.DER) if enrolled else None
    fingerprint = normalized_fingerprint(auth_cert.cert_fingerprint)

    for base in (10, 16):
        try:
            serial = int(raw, base)
        except ValueError:
            continue
        rows = Certificate.query.filter(
            Certificate.serial_number.in_(serial_variants(serial))
        ).all()
        if not rows:
            continue
        for row in rows:
            row_cert = _load(base64.b64decode(row.crt)) if row.crt else None
            if row_cert is None:
                continue
            row_der = row_cert.public_bytes(serialization.Encoding.DER)
            if enrolled_der is not None:
                if row_der == enrolled_der:
                    return row
                continue
            if fingerprint is not None:
                if _fingerprint(row_der, fingerprint[0]) == fingerprint[1]:
                    return row
                continue
            if (row_cert.serial_number == serial and auth_cert.cert_issuer
                    and row.issuer == auth_cert.cert_issuer):
                return row
        return None
    return None


# Withdrawing a certificate from service, RFC 5280 §5.3.1.
REMOVAL_REASON = 'cessationOfOperation'


def _revocation_held(auth_cert, actor) -> bool:
    """Whether the revocation policies apply: removing one's own enrolment
    stays a single gesture, administrators bypass, anyone else is gated."""
    if actor is None or getattr(actor, 'role', None) == 'admin':
        return False
    return auth_cert.user_id != getattr(actor, 'id', None)


def remove_enrolment(auth_cert, username: str = 'system', actor=None):
    """Revoke the certificate an enrolment names, then delete both.

    Returns ``(True, None)`` or ``(False, response)``. Deleting the
    ``AuthCertificate`` row is what withdraws access to UCM, and that is all
    these routes used to do: the certificate stayed valid for every other
    service trusting the same authority, with nothing on the CRL or at the
    responder to say otherwise. It is revoked first so the withdrawal is
    published, and the operator keeps a single gesture.
    """
    from models import db
    from services.cert_service import CertificateService
    from utils.datetime_utils import utc_now
    from utils.db_transaction import safe_commit
    from utils.response import error_response

    certificate = certificate_row_for(auth_cert)
    certificate_id = certificate.id if certificate else None

    needs_revoking = bool(
        certificate is not None
        and certificate.crt
        and not certificate.revoked
        and (not certificate.valid_to or certificate.valid_to >= utc_now())
    )
    if needs_revoking and _revocation_held(auth_cert, actor):
        try:
            from services.approval_gate import revocation_policy_for
            policy = revocation_policy_for(certificate)
        except Exception as error:
            logger.error('Enrolment %s: policy evaluation failed: %s', auth_cert.id, error)
            return False, error_response(
                'Policy evaluation failed; the enrolment was not removed', 500)
        if policy is not None:
            return False, error_response(
                f'Revoking this certificate requires approval per policy "{policy.name}": '
                'request its revocation, then remove the enrolment once it is revoked', 409)
    if needs_revoking:
        try:
            CertificateService.revoke_certificate(
                cert_id=certificate_id, reason=REMOVAL_REASON, username=username)
        except Exception as error:
            # An authority that cannot sign right now is not a reason to make
            # the certificate disappear without a trace; say so instead.
            logger.error('Enrolment %s: revocation refused: %s',
                         auth_cert.id, error)
            db.session.rollback()
            return False, error_response(
                'The certificate could not be revoked, so it was not deleted: '
                'it would stay valid for anything else trusting its authority. '
                'Check that the issuing CA can sign, then try again', 409)

    # The enrolment goes first: it is what mTLS authenticates against.
    db.session.delete(auth_cert)
    committed, failure = safe_commit(
        logger, 'Failed to delete the certificate enrolment')
    if not committed:
        return False, failure

    if certificate_id and not CertificateService.delete_certificate(
            certificate_id, username=username):
        # The access is withdrawn either way; saying it all worked would put
        # a success in the ledger for a certificate that is still there.
        return False, error_response(
            'The enrolment was removed but its certificate could not be '
            'deleted; it is still listed under Certificates', 500)
    return True, None
