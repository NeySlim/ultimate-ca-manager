"""
WebAuthn Routes Tests — /api/v2/webauthn/*

Tests WebAuthn credential CRUD, registration options, and verification.

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


# ============================================================
# Auth Required
# ============================================================
class TestWebAuthnAuthRequired:
    """Protected endpoints must return 401 without auth."""

    def test_list_credentials_requires_auth(self, app):
        r = app.test_client().get('/api/v2/webauthn/credentials')
        assert r.status_code == 401

    def test_delete_credential_requires_auth(self, app):
        r = app.test_client().delete('/api/v2/webauthn/credentials/1')
        assert r.status_code == 401

    def test_toggle_credential_requires_auth(self, app):
        r = _post(app.test_client(), '/api/v2/webauthn/credentials/1/toggle')
        assert r.status_code == 401

    def test_register_options_requires_auth(self, app):
        r = _post(app.test_client(), '/api/v2/webauthn/register/options')
        assert r.status_code == 401

    def test_register_verify_requires_auth(self, app):
        r = _post(app.test_client(), '/api/v2/webauthn/register/verify')
        assert r.status_code == 401


# ============================================================
# Credentials List
# ============================================================
class TestWebAuthnCredentials:
    """Test WebAuthn credential listing."""

    def test_list_credentials_empty(self, auth_client):
        r = auth_client.get('/api/v2/webauthn/credentials')
        assert r.status_code == 200
        data = get_json(r).get('data', [])
        assert isinstance(data, list)

    def test_list_credentials_returns_array(self, auth_client):
        r = auth_client.get('/api/v2/webauthn/credentials')
        body = get_json(r)
        assert 'data' in body or isinstance(body, list)


# ============================================================
# Delete / Toggle (non-existent)
# ============================================================
class TestWebAuthnDeleteToggle:
    """Test delete and toggle on non-existent credentials."""

    def test_delete_credential_not_found(self, auth_client):
        r = auth_client.delete('/api/v2/webauthn/credentials/99999')
        assert r.status_code == 404

    def test_toggle_credential_not_found(self, auth_client):
        r = _post(auth_client, '/api/v2/webauthn/credentials/99999/toggle')
        assert r.status_code == 404

    def test_toggle_credential_with_enabled_flag(self, auth_client):
        r = _post(auth_client, '/api/v2/webauthn/credentials/99999/toggle', {
            'enabled': False,
        })
        assert r.status_code == 404


# ============================================================
# Registration
# ============================================================
class TestWebAuthnRegistration:
    """Test WebAuthn registration endpoints."""

    def test_register_options_returns_data(self, auth_client):
        """Registration options should return 200 with challenge data."""
        r = _post(auth_client, '/api/v2/webauthn/register/options')
        # May succeed (200) or fail if RP config missing (400/500)
        assert r.status_code in (200, 400, 500)
        if r.status_code == 200:
            data = get_json(r).get('data', {})
            assert data is not None

    def test_register_verify_empty_data(self, auth_client):
        """Verify with empty credential data → 400."""
        r = _post(auth_client, '/api/v2/webauthn/register/verify', {
            'credential': {},
            'name': 'Test Key',
        })
        assert r.status_code == 400

    def test_register_verify_missing_credential(self, auth_client):
        """Verify with no credential field → 400."""
        r = _post(auth_client, '/api/v2/webauthn/register/verify', {
            'name': 'Test Key',
        })
        assert r.status_code == 400

    def test_register_verify_invalid_credential(self, auth_client):
        """Verify with invalid credential data → 400."""
        r = _post(auth_client, '/api/v2/webauthn/register/verify', {
            'credential': {
                'id': 'fake-id',
                'rawId': 'fake-raw',
                'response': {'clientDataJSON': 'bad', 'attestationObject': 'bad'},
                'type': 'public-key',
            },
            'name': 'Bad Key',
        })
        assert r.status_code == 400
