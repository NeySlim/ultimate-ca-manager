"""
mTLS Routes Tests — /api/v2/mtls/*

Tests mTLS settings, certificate CRUD, enrollment, available certificates,
and certificate assignment.

Uses shared fixtures from conftest.py:
  - app, client (unauthenticated), auth_client (admin session)
"""
import pytest
import json


def get_json(response):
    return json.loads(response.data)


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


# ============================================================
# Enrollment
# ============================================================
class TestMTLSEnroll:
    """Test mTLS enrollment endpoints."""

    def test_enroll_no_client_cert(self, auth_client):
        """Enroll without a presented client cert → 400."""
        r = _post(auth_client, '/api/v2/mtls/enroll', {})
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
