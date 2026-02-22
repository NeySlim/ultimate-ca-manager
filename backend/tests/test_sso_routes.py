"""
SSO Routes Tests — /api/v2/sso/*

Tests SSO provider CRUD, sessions, SAML metadata/certificates,
available providers, SSO login initiation, callback, and LDAP login.

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
class TestSSOAuthRequired:
    """Protected endpoints must return 401 without auth."""

    def test_list_providers_requires_auth(self, app):
        r = app.test_client().get('/api/v2/sso/providers')
        assert r.status_code == 401

    def test_create_provider_requires_auth(self, app):
        r = _post(app.test_client(), '/api/v2/sso/providers', {'name': 'x'})
        assert r.status_code == 401

    def test_get_provider_requires_auth(self, app):
        r = app.test_client().get('/api/v2/sso/providers/1')
        assert r.status_code == 401

    def test_update_provider_requires_auth(self, app):
        r = _put(app.test_client(), '/api/v2/sso/providers/1', {'name': 'x'})
        assert r.status_code == 401

    def test_delete_provider_requires_auth(self, app):
        r = app.test_client().delete('/api/v2/sso/providers/1')
        assert r.status_code == 401

    def test_toggle_provider_requires_auth(self, app):
        r = _post(app.test_client(), '/api/v2/sso/providers/1/toggle')
        assert r.status_code == 401

    def test_test_provider_requires_auth(self, app):
        r = _post(app.test_client(), '/api/v2/sso/providers/1/test')
        assert r.status_code == 401

    def test_test_mapping_requires_auth(self, app):
        r = _post(app.test_client(), '/api/v2/sso/providers/1/test-mapping')
        assert r.status_code == 401

    def test_sessions_requires_auth(self, app):
        r = app.test_client().get('/api/v2/sso/sessions')
        assert r.status_code == 401

    def test_saml_metadata_fetch_requires_auth(self, app):
        r = _post(app.test_client(), '/api/v2/sso/saml/metadata/fetch')
        assert r.status_code == 401

    def test_saml_certificates_requires_auth(self, app):
        r = app.test_client().get('/api/v2/sso/saml/certificates')
        assert r.status_code == 401


# ============================================================
# Provider CRUD — SAML
# ============================================================
class TestSSOProviderCRUDSaml:
    """Create / Read / Update / Toggle / Delete a SAML provider."""

    def test_create_saml_provider(self, auth_client):
        r = _post(auth_client, '/api/v2/sso/providers', {
            'name': 'Test SAML',
            'provider_type': 'saml',
            'enabled': False,
            'saml_entity_id': 'test',
            'saml_sso_url': 'https://idp.example.com/sso',
            'saml_certificate': 'test',
        })
        assert r.status_code in (200, 201), f'Create SAML failed: {r.data}'
        data = get_json(r).get('data', {})
        assert data['name'] == 'Test SAML'
        assert data['provider_type'] == 'saml'
        assert data['enabled'] is False

    def test_list_providers_includes_saml(self, auth_client):
        r = auth_client.get('/api/v2/sso/providers')
        assert r.status_code == 200
        providers = get_json(r).get('data', [])
        assert isinstance(providers, list)
        names = [p['name'] for p in providers]
        assert 'Test SAML' in names

    def test_get_provider_by_id(self, auth_client):
        r = auth_client.get('/api/v2/sso/providers')
        providers = get_json(r).get('data', [])
        saml = next((p for p in providers if p['name'] == 'Test SAML'), None)
        assert saml is not None
        r = auth_client.get(f'/api/v2/sso/providers/{saml["id"]}')
        assert r.status_code == 200
        data = get_json(r).get('data', {})
        assert data['name'] == 'Test SAML'

    def test_get_provider_not_found(self, auth_client):
        r = auth_client.get('/api/v2/sso/providers/99999')
        assert r.status_code == 404

    def test_update_provider(self, auth_client):
        r = auth_client.get('/api/v2/sso/providers')
        providers = get_json(r).get('data', [])
        saml = next((p for p in providers if p['name'] == 'Test SAML'), None)
        assert saml is not None
        r = _put(auth_client, f'/api/v2/sso/providers/{saml["id"]}', {
            'display_name': 'Updated SAML Display',
        })
        assert r.status_code == 200
        data = get_json(r).get('data', {})
        assert data['display_name'] == 'Updated SAML Display'

    def test_update_provider_by_type_name(self, auth_client):
        r = _put(auth_client, '/api/v2/sso/providers/saml', {
            'display_name': 'Via Type Name',
        })
        assert r.status_code == 200
        data = get_json(r).get('data', {})
        assert data['display_name'] == 'Via Type Name'

    def test_update_provider_not_found(self, auth_client):
        r = _put(auth_client, '/api/v2/sso/providers/99999', {'name': 'x'})
        assert r.status_code == 404

    def test_update_provider_type_not_found(self, auth_client):
        r = _put(auth_client, '/api/v2/sso/providers/nonexistent_type', {'name': 'x'})
        assert r.status_code == 404

    def test_toggle_provider(self, auth_client):
        r = auth_client.get('/api/v2/sso/providers')
        providers = get_json(r).get('data', [])
        saml = next((p for p in providers if p['name'] == 'Test SAML'), None)
        assert saml is not None
        original = saml['enabled']
        r = _post(auth_client, f'/api/v2/sso/providers/{saml["id"]}/toggle')
        assert r.status_code == 200
        data = get_json(r).get('data', {})
        assert data['enabled'] != original

    def test_toggle_provider_not_found(self, auth_client):
        r = _post(auth_client, '/api/v2/sso/providers/99999/toggle')
        assert r.status_code == 404

    def test_delete_provider(self, auth_client):
        # Create a throwaway provider to delete
        r = _post(auth_client, '/api/v2/sso/providers', {
            'name': 'To Delete OIDC',
            'provider_type': 'oauth2',
            'enabled': False,
            'oauth2_client_id': 'del-client',
            'oauth2_client_secret': 'del-secret',
            'oauth2_auth_url': 'https://auth.example.com/authorize',
            'oauth2_token_url': 'https://auth.example.com/token',
            'oauth2_userinfo_url': 'https://auth.example.com/userinfo',
        })
        assert r.status_code in (200, 201)
        pid = get_json(r).get('data', {}).get('id')
        assert pid is not None
        r = auth_client.delete(f'/api/v2/sso/providers/{pid}')
        assert r.status_code == 200

    def test_delete_provider_not_found(self, auth_client):
        r = auth_client.delete('/api/v2/sso/providers/99999')
        assert r.status_code == 404


# ============================================================
# Provider Validation
# ============================================================
class TestSSOProviderValidation:
    """Test input validation on create/update."""

    def test_create_missing_name(self, auth_client):
        r = _post(auth_client, '/api/v2/sso/providers', {
            'provider_type': 'saml',
        })
        assert r.status_code == 400

    def test_create_missing_type(self, auth_client):
        r = _post(auth_client, '/api/v2/sso/providers', {
            'name': 'Missing Type',
        })
        assert r.status_code == 400

    def test_create_invalid_type(self, auth_client):
        r = _post(auth_client, '/api/v2/sso/providers', {
            'name': 'Bad Type',
            'provider_type': 'kerberos',
        })
        assert r.status_code == 400

    def test_create_duplicate_name(self, auth_client):
        r = _post(auth_client, '/api/v2/sso/providers', {
            'name': 'Test SAML',
            'provider_type': 'saml',
        })
        assert r.status_code == 400

    def test_create_duplicate_type(self, auth_client):
        """Only one provider per type allowed."""
        r = _post(auth_client, '/api/v2/sso/providers', {
            'name': 'Another SAML',
            'provider_type': 'saml',
        })
        assert r.status_code == 400


# ============================================================
# Test Provider Connection
# ============================================================
class TestSSOProviderTest:
    """Test the provider test endpoint."""

    def test_test_provider_not_found(self, auth_client):
        r = _post(auth_client, '/api/v2/sso/providers/99999/test')
        assert r.status_code == 404

    def test_test_mapping_not_found(self, auth_client):
        r = _post(auth_client, '/api/v2/sso/providers/99999/test-mapping')
        assert r.status_code == 404


# ============================================================
# Sessions
# ============================================================
class TestSSOSessions:
    """Test SSO sessions list endpoint."""

    def test_list_sessions(self, auth_client):
        r = auth_client.get('/api/v2/sso/sessions')
        assert r.status_code == 200
        data = get_json(r).get('data', [])
        assert isinstance(data, list)


# ============================================================
# SAML Metadata & Certificates
# ============================================================
class TestSAMLMetadata:
    """Test SAML metadata and certificate endpoints."""

    def test_fetch_metadata_missing_url(self, auth_client):
        r = _post(auth_client, '/api/v2/sso/saml/metadata/fetch', {})
        assert r.status_code == 400

    def test_fetch_metadata_unreachable_url(self, auth_client):
        r = _post(auth_client, '/api/v2/sso/saml/metadata/fetch', {
            'metadata_url': 'https://unreachable.invalid/metadata',
        })
        assert r.status_code == 400

    def test_saml_certificates_list(self, auth_client):
        r = auth_client.get('/api/v2/sso/saml/certificates')
        assert r.status_code == 200
        data = get_json(r).get('data', [])
        assert isinstance(data, list)
        # Should have at least the HTTPS cert entry
        if len(data) > 0:
            assert 'id' in data[0]
            assert 'label' in data[0]

    def test_sp_metadata_returns_xml(self, client):
        """GET /sso/saml/metadata is public, returns XML."""
        r = client.get('/api/v2/sso/saml/metadata')
        assert r.status_code == 200
        assert b'EntityDescriptor' in r.data or b'entityID' in r.data


# ============================================================
# Available Providers (Public)
# ============================================================
class TestSSOAvailable:
    """Public endpoint — no auth required."""

    def test_available_returns_200(self, client):
        r = client.get('/api/v2/sso/available')
        assert r.status_code == 200

    def test_available_returns_list(self, client):
        r = client.get('/api/v2/sso/available')
        data = get_json(r).get('data', [])
        assert isinstance(data, list)

    def test_available_provider_structure(self, client):
        """Enabled providers should have expected keys."""
        r = client.get('/api/v2/sso/available')
        data = get_json(r).get('data', [])
        for p in data:
            assert 'id' in p
            assert 'provider_type' in p
            assert 'display_name' in p


# ============================================================
# SSO Login Initiation
# ============================================================
class TestSSOLogin:
    """Test SSO login initiation endpoint."""

    def test_login_ldap_returns_error(self, client):
        """LDAP uses /sso/ldap/login, not /sso/login/ldap."""
        r = client.get('/api/v2/sso/login/ldap')
        assert r.status_code == 400

    def test_login_invalid_type(self, client):
        r = client.get('/api/v2/sso/login/kerberos')
        assert r.status_code in (400, 404)


# ============================================================
# SSO Callback
# ============================================================
class TestSSOCallback:
    """Test SSO callback endpoint."""

    def test_callback_invalid_type_redirects(self, client):
        r = client.get('/api/v2/sso/callback/kerberos')
        assert r.status_code == 302
        assert 'error' in r.headers.get('Location', '')

    def test_callback_oauth2_no_provider(self, client):
        """No enabled OAuth2 provider → redirect with error."""
        r = client.get('/api/v2/sso/callback/oauth2')
        assert r.status_code == 302


# ============================================================
# LDAP Login
# ============================================================
class TestLDAPLoginRoutes:
    """Test LDAP login endpoint."""

    def test_ldap_login_missing_credentials(self, client):
        r = _post(client, '/api/v2/sso/ldap/login', {})
        assert r.status_code == 400

    def test_ldap_login_missing_password(self, client):
        r = _post(client, '/api/v2/sso/ldap/login', {'username': 'alice'})
        assert r.status_code == 400

    def test_ldap_login_no_enabled_provider(self, client):
        """No enabled LDAP provider → 400."""
        r = _post(client, '/api/v2/sso/ldap/login', {
            'username': 'alice',
            'password': 'test123',
        })
        assert r.status_code == 400

    def test_ldap_login_error_is_generic(self, client):
        """Error messages should not reveal user existence."""
        r = _post(client, '/api/v2/sso/ldap/login', {
            'username': 'alice',
            'password': 'wrong',
        })
        if r.status_code == 401:
            msg = get_json(r).get('message', '').lower()
            assert 'not found' not in msg
            assert 'invalid password' not in msg
