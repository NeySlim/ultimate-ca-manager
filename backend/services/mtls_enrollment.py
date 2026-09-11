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
from typing import Optional, Tuple

from cryptography import x509
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import serialization

from models import CA, Certificate
from utils.serial_format import serial_variants


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
    """An integer number of days in 1..3650, or None when the value is not
    exactly that (booleans, fractions and free text included)."""
    if value is None:
        value = default
    if isinstance(value, bool):
        return None
    if isinstance(value, float):
        if not value.is_integer():
            return None
        value = int(value)
    if isinstance(value, str):
        value = value.strip()
        if not value.isdecimal():
            return None
        value = int(value)
    if not isinstance(value, int) or not 1 <= value <= 3650:
        return None
    return value


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
