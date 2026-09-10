"""The mTLS PKCS#12 export must only ever hand out the key of the certificate
the caller enrolled -- and enrolling never grants a key the caller does not
already hold.

Before this fix ``download_mtls_certificate`` resolved the certificate row by
serial number alone, and ``enroll-import`` accepted any PEM without checking
who it belonged to. Any authenticated user (the read-only viewer included)
could therefore enrol a forged self-signed certificate bearing another
record's serial, or simply the victim's public certificate, and download the
victim's private key inside a PKCS#12.
"""

import base64
import json
from datetime import datetime, timedelta, timezone

import pytest
from cryptography import x509
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives.serialization import pkcs12
from cryptography.x509.oid import NameOID

from models import CA, Certificate, db
from models.auth_certificate import AuthCertificate


def _post(client, url, data):
    return client.post(url, data=json.dumps(data), content_type='application/json')


def _serial_int(stored: str) -> int:
    try:
        return int(stored)
    except ValueError:
        return int(stored, 16)


@pytest.fixture
def victim(app, create_ca):
    """A server certificate with a stored private key and no mTLS enrolment."""
    from services.cert_service import CertificateService
    ca_data = create_ca(cn='mTLS identity victim CA')
    with app.app_context():
        ca = db.session.get(CA, ca_data['id'])
        row = CertificateService.create_certificate(
            descr='victim server certificate', caref=ca.refid,
            dn={'CN': 'victim.example.test'}, cert_type='server_cert',
            key_type='2048', validity_days=30, username='admin',
        )
        db.session.commit()
        cert_pem = base64.b64decode(row.crt)
        cert = x509.load_pem_x509_certificate(cert_pem, default_backend())
        info = {
            'id': row.id, 'serial': row.serial_number, 'pem': cert_pem.decode(),
            'spki': cert.public_key().public_bytes(
                serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo
            ),
        }
    yield info
    with app.app_context():
        AuthCertificate.query.filter_by(cert_serial=info['serial']).delete()
        for c in Certificate.query.filter(Certificate.serial_number == info['serial']).all():
            db.session.delete(c)
        db.session.commit()


def _forged_cert_with_serial(serial: int) -> str:
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, 'forged.example.test')])
    now = datetime.now(timezone.utc)
    cert = (
        x509.CertificateBuilder()
        .subject_name(name).issuer_name(name)
        .public_key(key.public_key())
        .serial_number(serial)
        .not_valid_before(now - timedelta(days=1))
        .not_valid_after(now + timedelta(days=30))
        .sign(key, hashes.SHA256())
    )
    return cert.public_bytes(serialization.Encoding.PEM).decode()


def _download_p12(client, auth_cert_id):
    return _post(client, f'/api/v2/mtls/certificates/{auth_cert_id}/download',
                 {'format': 'p12', 'password': 'Sup3rSecretP12!'})


class TestPkcs12ExportIdentity:

    def test_forged_serial_does_not_unlock_another_records_key(self, app, viewer_client, victim):
        forged = _forged_cert_with_serial(_serial_int(victim['serial']))
        r = _post(viewer_client, '/api/v2/mtls/enroll-import', {'pem': forged, 'name': 'forged'})
        assert r.status_code == 201, r.get_json()
        auth_id = r.get_json()['data']['id']
        try:
            r = _download_p12(viewer_client, auth_id)
            assert r.status_code == 400, (r.status_code, r.data[:200])
            assert b'PKCS12' not in r.data or b'Private key not available' in r.data
        finally:
            with app.app_context():
                AuthCertificate.query.filter_by(id=auth_id).delete()
                db.session.commit()

    def test_importing_someone_elses_public_certificate_is_refused(self, app, viewer_client, victim):
        r = _post(viewer_client, '/api/v2/mtls/enroll-import',
                  {'pem': victim['pem'], 'name': 'stolen'})
        try:
            assert r.status_code == 403, (r.status_code, r.get_json())
        finally:
            with app.app_context():
                AuthCertificate.query.filter_by(cert_serial=victim['serial']).delete()
                db.session.commit()

    def test_own_generated_certificate_still_exports_with_its_key(self, app, auth_client, create_ca):
        ca_data = create_ca(cn='mTLS identity own CA')
        r = _post(auth_client, '/api/v2/mtls/certificates', {'ca_id': ca_data['id'], 'name': 'own'})
        assert r.status_code == 201, r.get_json()
        data = r.get_json()['data']
        try:
            r = _download_p12(auth_client, data['id'])
            assert r.status_code == 200, r.data[:200]
            key, cert, _ = pkcs12.load_key_and_certificates(r.data, b'Sup3rSecretP12!')
            own = x509.load_pem_x509_certificate(data['certificate'].encode(), default_backend())
            assert cert.public_bytes(serialization.Encoding.DER) == own.public_bytes(serialization.Encoding.DER)
            assert key.public_key().public_bytes(
                serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo
            ) == own.public_key().public_bytes(
                serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo
            )
        finally:
            with app.app_context():
                AuthCertificate.query.filter_by(id=data['id']).delete()
                row = db.session.get(Certificate, data['certificate_id'])
                if row:
                    db.session.delete(row)
                db.session.commit()


class TestAdminUserMtlsInputs:

    def test_validity_days_is_validated(self, auth_client, create_ca):
        ca_data = create_ca(cn='mTLS identity validity CA')
        for bad in ('abc', 0, -5, 99999):
            r = _post(auth_client, '/api/v2/users/1/mtls/certificates',
                      {'mode': 'generate', 'ca_id': ca_data['id'], 'validity_days': bad})
            assert r.status_code == 400, (bad, r.status_code, r.get_json())

    def test_non_numeric_ca_id_is_not_found(self, auth_client):
        r = _post(auth_client, '/api/v2/users/1/mtls/certificates',
                  {'mode': 'generate', 'ca_id': 'not-a-ca'})
        assert r.status_code in (400, 404)
