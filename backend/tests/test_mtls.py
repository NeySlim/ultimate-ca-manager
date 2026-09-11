"""
mTLS Routes Tests — /api/v2/mtls/*

Tests mTLS settings, certificate CRUD, enrollment, available certificates,
and certificate assignment.

Uses shared fixtures from conftest.py:
  - app, client (unauthenticated), auth_client (admin session)
"""
import pytest
import base64
import json
from tests.conftest import get_json

def _post(client, url, data=None):
    return client.post(
        url,
        data=json.dumps(data) if data else '{}',
        content_type='application/json',
    )


def _put(client, url, data=None):
    return client.put(
        url,
        data=json.dumps(data) if data else '{}',
        content_type='application/json',
    )


# ============================================================
# Auth Required
# ============================================================
class TestMTLSAuthRequired:
    """Protected endpoints must return 401 without auth."""

    def test_settings_get_requires_auth(self, app):
        r = app.test_client().get('/api/v2/mtls/settings')
        assert r.status_code == 401

    def test_settings_put_requires_auth(self, app):
        r = _put(app.test_client(), '/api/v2/mtls/settings', {'enabled': False})
        assert r.status_code == 401

    def test_certificates_list_requires_auth(self, app):
        r = app.test_client().get('/api/v2/mtls/certificates')
        assert r.status_code == 401

    def test_certificates_create_requires_auth(self, app):
        r = _post(app.test_client(), '/api/v2/mtls/certificates')
        assert r.status_code == 401

    def test_certificates_delete_requires_auth(self, app):
        r = app.test_client().delete('/api/v2/mtls/certificates/1')
        assert r.status_code == 401

    def test_certificates_download_requires_auth(self, app):
        r = app.test_client().get('/api/v2/mtls/certificates/1/download')
        assert r.status_code == 401

    def test_enroll_requires_auth(self, app):
        r = _post(app.test_client(), '/api/v2/mtls/enroll')
        assert r.status_code == 401

    def test_enroll_import_requires_auth(self, app):
        r = _post(app.test_client(), '/api/v2/mtls/enroll-import')
        assert r.status_code == 401

    def test_enroll_import_valid_pem_succeeds(self, app, auth_client, create_ca):
        """Regression: enroll-import 500ed with NameError (cert_pem undefined)
        on every valid non-duplicate PEM."""
        from datetime import datetime, timedelta, timezone
        from cryptography import x509
        from cryptography.hazmat.primitives import hashes, serialization
        from cryptography.hazmat.primitives.asymmetric import ec
        from cryptography.x509.oid import NameOID

        # Only a certificate issued by one of the server's CAs can be enrolled
        from models import CA, db
        from services.cert_service import CertificateService
        ca_data = create_ca(cn='enroll-import regression CA')
        with app.app_context():
            ca = db.session.get(CA, ca_data['id'])
            row = CertificateService.create_certificate(
                descr='enroll-import-regression', caref=ca.refid,
                dn={'CN': 'enroll-import.example.com'}, cert_type='usr_cert',
                key_type='2048', validity_days=30, username='admin',
            )
            db.session.commit()
            pem = base64.b64decode(row.crt).decode()

        r = _post(auth_client, '/api/v2/mtls/enroll-import',
                  {'pem': pem, 'name': 'enroll-import-regression'})
        assert r.status_code in (200, 201), r.get_json()
        data = r.get_json()['data']
        assert 'enroll-import.example.com' in data['cert_subject']

        # Shared session-scoped DB: remove the enrollment so later tests that
        # assume the admin has no mTLS certificate keep passing.
        r = auth_client.delete(f"/api/v2/mtls/certificates/{data['id']}")
        assert r.status_code == 200

    def test_available_certificates_requires_auth(self, app):
        r = app.test_client().get('/api/v2/mtls/available-certificates')
        assert r.status_code == 401

    def test_assign_requires_auth(self, app):
        r = _post(app.test_client(), '/api/v2/mtls/assign')
        assert r.status_code == 401


# ============================================================
# Settings
# ============================================================
class TestMTLSSettings:
    """Test mTLS settings get/put."""

    def test_get_settings(self, auth_client):
        r = auth_client.get('/api/v2/mtls/settings')
        assert r.status_code == 200
        data = get_json(r).get('data', {})
        assert 'enabled' in data
        assert 'required' in data
        assert 'trusted_ca_id' in data

    def test_update_settings_no_data(self, auth_client):
        r = auth_client.put('/api/v2/mtls/settings',
                            data='',
                            content_type='application/json')
        assert r.status_code == 400

    def test_update_settings_disable(self, auth_client):
        r = _put(auth_client, '/api/v2/mtls/settings', {
            'enabled': False,
            'required': False,
        })
        assert r.status_code == 200
        data = get_json(r).get('data', {})
        assert data['enabled'] is False

    def test_require_mtls_without_admin_cert(self, auth_client):
        """Cannot require mTLS when no admin has an enrolled cert."""
        r = _put(auth_client, '/api/v2/mtls/settings', {
            'enabled': True,
            'required': True,
        })
        assert r.status_code == 400


# ============================================================
# Certificates
# ============================================================
class TestMTLSCertificates:
    """Test mTLS certificate CRUD."""

    def test_create_reads_encrypted_private_key_from_database(
        self, app, auth_client, create_ca, encryption_enabled
    ):
        from cryptography.hazmat.primitives.serialization import load_pem_private_key

        from models import AuthCertificate, CA, CRLMetadata, Certificate, OCSPResponse, db
        from utils.file_naming import ca_cert_path, ca_key_path, cert_cert_path, cert_key_path

        ca_data = create_ca(cn='mTLS encrypted key source')
        response = _post(auth_client, '/api/v2/mtls/certificates', {
            'ca_id': ca_data['id'],
            'name': 'Encrypted mTLS enrollment',
        })
        assert response.status_code == 201, response.get_json()
        data = response.get_json()['data']

        try:
            key_pem = data['private_key'].encode()
            assert key_pem.startswith(b'-----BEGIN')
            assert b'PRIVATE KEY-----' in key_pem.splitlines()[0]
            load_pem_private_key(key_pem, password=None)

            with app.app_context():
                cert = db.session.get(Certificate, data['certificate_id'])
                assert cert is not None
                assert not cert_key_path(cert).exists()
        finally:
            with app.app_context():
                AuthCertificate.query.filter_by(id=data['id']).delete()
                cert = db.session.get(Certificate, data['certificate_id'])
                if cert:
                    cert_cert_path(cert).unlink(missing_ok=True)
                    cert_key_path(cert).unlink(missing_ok=True)
                    db.session.delete(cert)
                CRLMetadata.query.filter_by(ca_id=ca_data['id']).delete()
                OCSPResponse.query.filter_by(ca_id=ca_data['id']).delete()
                ca = db.session.get(CA, ca_data['id'])
                if ca:
                    ca_cert_path(ca).unlink(missing_ok=True)
                    ca_key_path(ca).unlink(missing_ok=True)
                    db.session.delete(ca)
                db.session.commit()

    def test_list_certificates_empty(self, auth_client):
        r = auth_client.get('/api/v2/mtls/certificates')
        assert r.status_code == 200
        data = get_json(r).get('data', [])
        assert isinstance(data, list)

    def test_delete_certificate_not_found(self, auth_client):
        r = auth_client.delete('/api/v2/mtls/certificates/99999')
        assert r.status_code == 404

    def test_download_certificate_not_found(self, auth_client):
        r = auth_client.get('/api/v2/mtls/certificates/99999/download')
        assert r.status_code == 404

    def test_download_pkcs12_requires_post(self, auth_client):
        r = auth_client.get('/api/v2/mtls/certificates/1/download?format=pkcs12&password=secret123')
        assert r.status_code == 400


# ============================================================
# Enrollment
# ============================================================
class TestMTLSEnroll:
    """Test mTLS enrollment endpoints."""

    def test_enroll_no_client_cert(self, auth_client):
        """Enroll without a presented client cert → 400."""
        r = _post(auth_client, '/api/v2/mtls/enroll', {})
        assert r.status_code == 400

    def test_enroll_rejects_spoofed_proxy_headers_from_untrusted_peer(
        self, auth_client, monkeypatch,
    ):
        """Untrusted peers must not enroll via forged X-SSL-Client-* headers."""
        monkeypatch.setattr(
            'utils.trusted_proxy.is_request_from_trusted_proxy',
            lambda: False,
        )
        r = auth_client.post(
            '/api/v2/mtls/enroll',
            data='{}',
            content_type='application/json',
            headers={
                'X-SSL-Client-Verify': 'SUCCESS',
                'X-SSL-Client-S-DN': 'CN=Spoofed Victim,O=Test',
                'X-SSL-Client-Serial': 'aabbccdd',
            },
        )
        assert r.status_code == 400

    def test_enroll_import_empty_pem(self, auth_client):
        """Import with no PEM data → 400."""
        r = _post(auth_client, '/api/v2/mtls/enroll-import', {})
        assert r.status_code == 400

    def test_enroll_import_invalid_pem(self, auth_client):
        """Import with invalid PEM → 400."""
        r = _post(auth_client, '/api/v2/mtls/enroll-import', {
            'pem': 'not-a-real-certificate',
        })
        assert r.status_code == 400

    def test_enroll_import_garbage_base64(self, auth_client):
        """Import with garbage base64 → 400."""
        r = _post(auth_client, '/api/v2/mtls/enroll-import', {
            'pem': 'dGhpcyBpcyBub3QgYSBjZXJ0',
        })
        assert r.status_code == 400


# ============================================================
# Available Certificates
# ============================================================
class TestMTLSAvailableCertificates:
    """Test available certificates listing."""

    def test_available_certificates_returns_list(self, auth_client):
        r = auth_client.get('/api/v2/mtls/available-certificates')
        assert r.status_code == 200
        data = get_json(r).get('data', [])
        assert isinstance(data, list)


# ============================================================
# Assign Certificate
# ============================================================
class TestMTLSAssign:
    """Test certificate assignment."""

    def test_assign_missing_cert_id(self, auth_client):
        r = _post(auth_client, '/api/v2/mtls/assign', {})
        assert r.status_code == 400

    def test_assign_cert_not_found(self, auth_client):
        r = _post(auth_client, '/api/v2/mtls/assign', {'cert_id': 99999})
        assert r.status_code == 404
