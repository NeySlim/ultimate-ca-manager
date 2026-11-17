"""EST re-enrolment and SCEP renewal authenticate the request with the
certificate being renewed: it must be one this CA issued and still holds,
not revoked, not expired, and the CSR must keep its identity.
"""

import base64
from datetime import datetime, timedelta, timezone

import pytest
from cryptography import x509
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives.serialization import pkcs7
from cryptography.x509.oid import NameOID

from models import CA, Certificate, RevokedSerial, db
from services.cert.issued_lookup import EXPIRED, OK, REVOKED, UNKNOWN, issued_certificate_status
from tests.test_est_rfc7030 import (  # noqa: F401  (EST harness)
    EST_BASE, _basic_auth, _post_csr, est_config,
)


def _csr(cn, key=None, sans=None):
    key = key or rsa.generate_private_key(public_exponent=65537, key_size=2048)
    builder = x509.CertificateSigningRequestBuilder().subject_name(
        x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, cn)])
    )
    if sans:
        builder = builder.add_extension(
            x509.SubjectAlternativeName([x509.DNSName(s) for s in sans]), critical=False
        )
    return builder.sign(key, hashes.SHA256()), key


def _enrol(client, cn):
    csr, key = _csr(cn)
    r = _post_csr(client, 'simpleenroll', csr, headers=_basic_auth())
    assert r.status_code == 200, r.data
    certs = pkcs7.load_der_pkcs7_certificates(base64.b64decode(r.data))
    leaf = [c for c in certs if not c.extensions.get_extension_for_oid(
        x509.ExtensionOID.BASIC_CONSTRAINTS).value.ca][0]
    return leaf, key


def _reenrol(client, leaf, key, cn=None, sans=None):
    csr, _ = _csr(cn or leaf.subject.get_attributes_for_oid(NameOID.COMMON_NAME)[0].value,
                  key=key, sans=sans)
    return _post_csr(client, 'simplereenroll', csr,
                     client_cert_pem=leaf.public_bytes(serialization.Encoding.PEM).decode())


def _foreign_leaf(cn):
    ca_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    now = datetime.now(timezone.utc)
    cert = (
        x509.CertificateBuilder()
        .subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, cn)]))
        .issuer_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, 'Foreign CA')]))
        .public_key(key.public_key()).serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(days=1)).not_valid_after(now + timedelta(days=30))
        .add_extension(x509.ExtendedKeyUsage([x509.ObjectIdentifier('1.3.6.1.4.1.311.10.3.12')]), critical=False)
        .sign(ca_key, hashes.SHA256())
    )
    return cert, key


class TestEstReenrolAuthenticatesTheRenewedCertificate:

    def test_legitimate_reenrol_still_works(self, client, app, est_config):
        leaf, key = _enrol(client, 'est-legit.example.test')
        r = _reenrol(client, leaf, key)
        assert r.status_code == 200, r.data
        with app.app_context():
            ca = db.session.get(CA, est_config['id'])
            row, status = issued_certificate_status(ca, leaf)
            assert row is not None and row.archived is True

    def test_revoked_certificate_cannot_reenrol(self, client, app, est_config):
        leaf, key = _enrol(client, 'est-revoked.example.test')
        with app.app_context():
            ca = db.session.get(CA, est_config['id'])
            row, status = issued_certificate_status(ca, leaf)
            assert status == OK
            row.revoked = True
            db.session.commit()
        r = _reenrol(client, leaf, key)
        assert r.status_code == 403, r.data

    def test_certificate_of_another_ca_cannot_reenrol(self, client, app, est_config):
        foreign, key = _foreign_leaf('est-foreign.example.test')
        r = _reenrol(client, foreign, key)
        assert r.status_code == 403, r.data

    def test_deleted_then_revoked_record_still_refuses(self, client, app, est_config):
        leaf, key = _enrol(client, 'est-deleted.example.test')
        with app.app_context():
            ca = db.session.get(CA, est_config['id'])
            row, _ = issued_certificate_status(ca, leaf)
            db.session.add(RevokedSerial(caref=ca.refid, serial_number=row.serial_number,
                                         revoked_at=datetime.now(timezone.utc).replace(tzinfo=None),
                                         revoke_reason='keyCompromise', valid_to=row.valid_to))
            db.session.delete(row)
            db.session.commit()
            _, status = issued_certificate_status(ca, leaf)
            assert status == REVOKED
        r = _reenrol(client, leaf, key)
        assert r.status_code == 403, r.data


class TestScepRenewalValidation:

    def test_hex_stored_revoked_signer_is_refused(self, app, create_ca):
        """A signer whose row stores the serial in hexadecimal (issue form,
        approval, renewal) and is revoked must be refused too."""
        from services.cert_service import CertificateService
        ca_data = create_ca(cn='SCEP renewal identity CA')
        with app.app_context():
            ca = db.session.get(CA, ca_data['id'])
            row = CertificateService.create_certificate(
                descr='scep-signer', caref=ca.refid, dn={'CN': 'scep-signer.example.test'},
                cert_type='server_cert', key_type='2048', validity_days=30, username='admin',
            )
            db.session.commit()
            signer = x509.load_pem_x509_certificate(base64.b64decode(row.crt), default_backend())
            row.serial_number = format(signer.serial_number, 'x')  # hex, as the issue form stores it
            row.revoked = True
            db.session.commit()
            _, status = issued_certificate_status(ca, signer)
            assert status == REVOKED
            row_id = row.id
        with app.app_context():
            db.session.delete(db.session.get(Certificate, row_id))
            db.session.commit()

    def test_status_of_a_foreign_certificate_is_unknown(self, app, create_ca):
        ca_data = create_ca(cn='SCEP renewal unknown CA')
        foreign, _ = _foreign_leaf('unknown.example.test')
        with app.app_context():
            ca = db.session.get(CA, ca_data['id'])
            assert issued_certificate_status(ca, foreign) == (None, UNKNOWN)
