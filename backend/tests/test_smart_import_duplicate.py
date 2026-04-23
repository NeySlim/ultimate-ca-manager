"""Tests for issue #85 — duplicate detection should not have false positives.

Two certs with the same serial number but different issuers must NOT be
considered duplicates. Same DER bytes (modulo PEM reformatting) MUST be
detected as duplicates.
"""
import datetime
import base64
import pytest
from cryptography import x509
from cryptography.x509.oid import NameOID
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa


def _make_cert(cn: str, issuer_cn: str, serial: int) -> str:
    """Generate a self-signed-ish PEM cert with a given subject/issuer/serial."""
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    subject = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, cn)])
    issuer = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, issuer_cn)])
    now = datetime.datetime.now(datetime.timezone.utc)
    cert = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(issuer)
        .public_key(key.public_key())
        .serial_number(serial)
        .not_valid_before(now - datetime.timedelta(days=1))
        .not_valid_after(now + datetime.timedelta(days=365))
        .sign(key, hashes.SHA256())
    )
    return cert.public_bytes(serialization.Encoding.PEM).decode()


def test_same_serial_different_issuer_is_not_duplicate(app):
    """RFC 5280 says serial+issuer is the unique pair, not serial alone."""
    from models import Certificate, db
    from services.smart_import.validator import find_existing_cert_by_identity

    with app.app_context():
        pem_a = _make_cert('cert-a', 'CN=Issuer A', serial=12345)
        existing = Certificate(
            refid='aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa',
            descr='cert-a',
            crt=base64.b64encode(pem_a.encode()).decode(),
            subject='CN=cert-a', issuer='CN=Issuer A',
            serial_number='12345',
        )
        db.session.add(existing)
        db.session.commit()

        try:
            # Same serial, DIFFERENT issuer — not a duplicate
            pem_b = _make_cert('cert-b', 'CN=Issuer B', serial=12345)
            match = find_existing_cert_by_identity(
                Certificate, '12345', 'CN=Issuer B', pem_b
            )
            assert match is None, "Different issuer must not match"

            # Same serial, SAME issuer DN, but DIFFERENT cert bytes — not a duplicate
            pem_c = _make_cert('cert-c', 'CN=Issuer A', serial=12345)
            match = find_existing_cert_by_identity(
                Certificate, '12345', 'CN=Issuer A', pem_c
            )
            assert match is None, "Different fingerprint must not match"
        finally:
            db.session.delete(existing)
            db.session.commit()


def test_same_cert_is_duplicate(app):
    """Re-importing the exact same cert MUST be detected as duplicate."""
    from models import Certificate, db
    from services.smart_import.validator import find_existing_cert_by_identity

    with app.app_context():
        pem = _make_cert('cert-dup', 'CN=Issuer Dup', serial=99999)

        existing = Certificate(
            refid='bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb',
            descr='cert-dup',
            crt=base64.b64encode(pem.encode()).decode(),
            subject='CN=cert-dup', issuer='CN=Issuer Dup',
            serial_number='99999',
        )
        db.session.add(existing)
        db.session.commit()

        try:
            match = find_existing_cert_by_identity(
                Certificate, '99999', 'CN=Issuer Dup', pem
            )
            assert match is not None
            assert match.id == existing.id
        finally:
            db.session.delete(existing)
            db.session.commit()


def test_no_serial_returns_none(app):
    from services.smart_import.validator import find_existing_cert_by_identity
    from models import Certificate
    with app.app_context():
        assert find_existing_cert_by_identity(Certificate, None, None, None) is None
        assert find_existing_cert_by_identity(Certificate, '', 'CN=X', 'pem') is None
