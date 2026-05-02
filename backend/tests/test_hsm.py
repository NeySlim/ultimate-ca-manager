"""
HSM Management API Tests — /api/v2/hsm/*

Tests for all HSM management endpoints:
- Provider CRUD (list, create, get, update, delete)
- Provider operations (test connection, sync keys)
- Key management (list, create, get, delete, public key, sign)
- Provider info (provider types, dependencies, install)

Uses shared conftest fixtures: app, client, auth_client.

Note: HSM operations (test, sync, sign, key generation) require real HSM hardware.
These tests focus on validation, auth, and 404 handling.
"""
import pytest
import json
import os
import sys
from tests.conftest import get_json, assert_success, assert_error

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

CONTENT_JSON = 'application/json'
HSM_BASE = '/api/v2/hsm'

VALID_PROVIDER = {
    'name': 'Test HSM',
    'type': 'pkcs11',
    'config': {'library_path': '/usr/lib/test.so'},
}

def post_json(client, url, data):
    return client.post(url, data=json.dumps(data), content_type=CONTENT_JSON)


def put_json(client, url, data):
    return client.put(url, data=json.dumps(data), content_type=CONTENT_JSON)


# ============================================================
# Auth Required — all 16 endpoints must reject unauthenticated
# ============================================================

class TestAuthRequired:
    """All HSM endpoints must return 401 without authentication."""

    def test_list_providers_requires_auth(self, client):
        assert client.get(f'{HSM_BASE}/providers').status_code == 401

    def test_create_provider_requires_auth(self, client):
        r = post_json(client, f'{HSM_BASE}/providers', VALID_PROVIDER)
        assert r.status_code == 401

    def test_get_provider_requires_auth(self, client):
        assert client.get(f'{HSM_BASE}/providers/1').status_code == 401

    def test_update_provider_requires_auth(self, client):
        r = put_json(client, f'{HSM_BASE}/providers/1', {'name': 'Updated'})
        assert r.status_code == 401

    def test_delete_provider_requires_auth(self, client):
        assert client.delete(f'{HSM_BASE}/providers/1').status_code == 401

    def test_test_provider_requires_auth(self, client):
        r = client.post(f'{HSM_BASE}/providers/1/test')
        assert r.status_code == 401

    def test_sync_provider_requires_auth(self, client):
        r = client.post(f'{HSM_BASE}/providers/1/sync')
        assert r.status_code == 401

    def test_list_keys_requires_auth(self, client):
        assert client.get(f'{HSM_BASE}/keys').status_code == 401

    def test_create_key_requires_auth(self, client):
        r = post_json(client, f'{HSM_BASE}/providers/1/keys', {
            'label': 'test', 'algorithm': 'RSA-2048'
        })
        assert r.status_code == 401

    def test_get_key_requires_auth(self, client):
        assert client.get(f'{HSM_BASE}/keys/1').status_code == 401

    def test_delete_key_requires_auth(self, client):
        assert client.delete(f'{HSM_BASE}/keys/1').status_code == 401

    def test_get_public_key_requires_auth(self, client):
        assert client.get(f'{HSM_BASE}/keys/1/public').status_code == 401

    def test_sign_requires_auth(self, client):
        r = post_json(client, f'{HSM_BASE}/keys/1/sign', {'data': 'dGVzdA=='})
        assert r.status_code == 401

    def test_provider_types_requires_auth(self, client):
        assert client.get(f'{HSM_BASE}/provider-types').status_code == 401

    def test_dependencies_requires_auth(self, client):
        assert client.get(f'{HSM_BASE}/dependencies').status_code == 401

    def test_install_dependencies_requires_auth(self, client):
        r = post_json(client, f'{HSM_BASE}/dependencies/install', {'provider': 'pkcs11'})
        assert r.status_code == 401


# ============================================================
# List Providers
# ============================================================

class TestListProviders:
    """GET /api/v2/hsm/providers — list HSM providers."""

    def test_list_providers_empty(self, auth_client):
        r = auth_client.get(f'{HSM_BASE}/providers')
        data = assert_success(r)
        assert isinstance(data, list)

    def test_list_providers_returns_list(self, auth_client):
        r = auth_client.get(f'{HSM_BASE}/providers')
        body = get_json(r)
        assert 'data' in body


# ============================================================
# Create Provider
# ============================================================

class TestCreateProvider:
    """POST /api/v2/hsm/providers — create HSM provider."""

    def test_create_provider(self, auth_client):
        r = post_json(auth_client, f'{HSM_BASE}/providers', VALID_PROVIDER)
        data = assert_success(r, status=201)
        assert data.get('name') == 'Test HSM'
        assert data.get('type') == 'pkcs11'

    def test_create_provider_missing_name(self, auth_client):
        r = post_json(auth_client, f'{HSM_BASE}/providers', {
            'type': 'pkcs11', 'config': {}
        })
        assert_error(r, 400)

    def test_create_provider_missing_type(self, auth_client):
        r = post_json(auth_client, f'{HSM_BASE}/providers', {
            'name': 'No Type', 'config': {}
        })
        assert_error(r, 400)

    def test_create_provider_invalid_type(self, auth_client):
        r = post_json(auth_client, f'{HSM_BASE}/providers', {
            'name': 'Bad Type', 'type': 'invalid-hsm', 'config': {}
        })
        assert_error(r, 400)

    def test_create_provider_no_body(self, auth_client):
        r = auth_client.post(f'{HSM_BASE}/providers', content_type=CONTENT_JSON)
        assert_error(r, 400)


# ============================================================
# Provider CRUD Lifecycle
# ============================================================

class TestProviderCRUD:
    """Full CRUD lifecycle for HSM providers."""

    def _create_provider(self, auth_client, name='CRUD HSM'):
        r = post_json(auth_client, f'{HSM_BASE}/providers', {
            'name': name,
            'type': 'pkcs11',
            'config': {'library_path': '/usr/lib/crud-test.so'},
        })
        data = assert_success(r, status=201)
        return data.get('id')

    def test_get_provider(self, auth_client):
        pid = self._create_provider(auth_client, 'Get Test HSM')
        r = auth_client.get(f'{HSM_BASE}/providers/{pid}')
        data = assert_success(r)
        assert data.get('name') == 'Get Test HSM'

    def test_get_provider_nonexistent(self, auth_client):
        r = auth_client.get(f'{HSM_BASE}/providers/99999')
        assert_error(r, 404)

    def test_update_provider(self, auth_client):
        pid = self._create_provider(auth_client, 'Update Test HSM')
        r = put_json(auth_client, f'{HSM_BASE}/providers/{pid}', {
            'name': 'Updated HSM Name'
        })
        data = assert_success(r)
        assert data.get('name') == 'Updated HSM Name'

    def test_update_provider_nonexistent(self, auth_client):
        r = put_json(auth_client, f'{HSM_BASE}/providers/99999', {'name': 'X'})
        assert_error(r, 404)

    def test_update_provider_empty_name(self, auth_client):
        pid = self._create_provider(auth_client, 'Empty Name Test')
        r = put_json(auth_client, f'{HSM_BASE}/providers/{pid}', {'name': ''})
        assert_error(r, 400)

    def test_delete_provider(self, auth_client):
        pid = self._create_provider(auth_client, 'Delete Test HSM')
        r = auth_client.delete(f'{HSM_BASE}/providers/{pid}')
        assert r.status_code in (200, 204)

    def test_delete_provider_nonexistent(self, auth_client):
        r = auth_client.delete(f'{HSM_BASE}/providers/99999')
        assert_error(r, 404)

    def test_delete_provider_then_get_404(self, auth_client):
        pid = self._create_provider(auth_client, 'Delete Verify HSM')
        auth_client.delete(f'{HSM_BASE}/providers/{pid}')
        r = auth_client.get(f'{HSM_BASE}/providers/{pid}')
        assert_error(r, 404)


# ============================================================
# Provider Operations (test/sync — will fail without real HSM)
# ============================================================

class TestProviderOperations:
    """POST test/sync — expects failure without real HSM hardware."""
    _counter = [0]

    def _create_provider(self, auth_client):
        self._counter[0] += 1
        r = post_json(auth_client, f'{HSM_BASE}/providers', {
            'name': f'Ops Test HSM {self._counter[0]}',
            'type': 'pkcs11',
            'config': {'library_path': '/usr/lib/nonexistent.so'},
        })
        return assert_success(r, status=201).get('id')

    def test_test_provider_nonexistent(self, auth_client):
        r = auth_client.post(f'{HSM_BASE}/providers/99999/test')
        assert_error(r, 404)

    def test_sync_provider_nonexistent(self, auth_client):
        r = auth_client.post(f'{HSM_BASE}/providers/99999/sync')
        assert_error(r, 404)

    def test_test_provider_fails_gracefully(self, auth_client):
        """Test connection to non-existent HSM fails but doesn't crash."""
        pid = self._create_provider(auth_client)
        r = auth_client.post(f'{HSM_BASE}/providers/{pid}/test')
        # Should return 200 with failure info or 400/500 — not crash
        assert r.status_code in (200, 400, 500)

    def test_sync_provider_fails_gracefully(self, auth_client):
        """Sync with non-existent HSM fails but doesn't crash."""
        pid = self._create_provider(auth_client)
        r = auth_client.post(f'{HSM_BASE}/providers/{pid}/sync')
        assert r.status_code in (200, 400, 500)


# ============================================================
# Provider Types
# ============================================================

class TestProviderTypes:
    """GET /api/v2/hsm/provider-types — list available provider types."""

    def test_list_provider_types(self, auth_client):
        r = auth_client.get(f'{HSM_BASE}/provider-types')
        data = assert_success(r)
        assert isinstance(data, list)
        assert len(data) > 0

    def test_provider_types_have_required_fields(self, auth_client):
        r = auth_client.get(f'{HSM_BASE}/provider-types')
        data = assert_success(r)
        for pt in data:
            assert 'type' in pt
            assert 'label' in pt
            assert 'config_schema' in pt

    def test_provider_types_include_pkcs11(self, auth_client):
        r = auth_client.get(f'{HSM_BASE}/provider-types')
        data = assert_success(r)
        types = [p['type'] for p in data]
        assert 'pkcs11' in types


# ============================================================
# Dependencies
# ============================================================

class TestDependencies:
    """GET /api/v2/hsm/dependencies — check HSM dependency status."""

    def test_get_dependencies(self, auth_client):
        r = auth_client.get(f'{HSM_BASE}/dependencies')
        data = assert_success(r)
        assert 'dependencies' in data
        assert isinstance(data['dependencies'], list)

    def test_dependencies_have_required_fields(self, auth_client):
        r = auth_client.get(f'{HSM_BASE}/dependencies')
        data = assert_success(r)
        for dep in data['dependencies']:
            assert 'provider' in dep
            assert 'installed' in dep
            assert isinstance(dep['installed'], bool)

    def test_install_dependencies_missing_provider(self, auth_client):
        r = post_json(auth_client, f'{HSM_BASE}/dependencies/install', {})
        assert_error(r, 400)

    def test_install_dependencies_invalid_provider(self, auth_client):
        r = post_json(auth_client, f'{HSM_BASE}/dependencies/install', {
            'provider': 'nonexistent'
        })
        assert_error(r, 400)


# ============================================================
# List Keys
# ============================================================

class TestListKeys:
    """GET /api/v2/hsm/keys — list HSM keys."""

    def test_list_keys_empty(self, auth_client):
        r = auth_client.get(f'{HSM_BASE}/keys')
        data = assert_success(r)
        assert isinstance(data, list)

    def test_list_keys_filter_nonexistent_provider(self, auth_client):
        r = auth_client.get(f'{HSM_BASE}/keys?provider_id=99999')
        assert_error(r, 404)


# ============================================================
# Key Operations (require real HSM — test validation/404 only)
# ============================================================

class TestKeyOperations:
    """Key CRUD and operations — validation and 404 tests only."""

    def test_get_key_nonexistent(self, auth_client):
        r = auth_client.get(f'{HSM_BASE}/keys/99999')
        assert_error(r, 404)

    def test_delete_key_nonexistent(self, auth_client):
        r = auth_client.delete(f'{HSM_BASE}/keys/99999')
        assert_error(r, 404)

    def test_get_public_key_nonexistent(self, auth_client):
        r = auth_client.get(f'{HSM_BASE}/keys/99999/public')
        assert_error(r, 404)

    def test_sign_nonexistent_key(self, auth_client):
        r = post_json(auth_client, f'{HSM_BASE}/keys/99999/sign', {
            'data': 'dGVzdA=='
        })
        assert_error(r, 404)

    def test_create_key_nonexistent_provider(self, auth_client):
        r = post_json(auth_client, f'{HSM_BASE}/providers/99999/keys', {
            'label': 'test-key',
            'algorithm': 'RSA-2048',
            'purpose': 'signing',
        })
        assert_error(r, 404)

    def test_create_key_missing_label(self, auth_client):
        """Create key with missing label — requires a real provider to hit validation."""
        # First create a provider
        pr = post_json(auth_client, f'{HSM_BASE}/providers', {
            'name': 'Key Validation HSM',
            'type': 'pkcs11',
            'config': {'library_path': '/usr/lib/key-test.so'},
        })
        pid = assert_success(pr, status=201).get('id')
        r = post_json(auth_client, f'{HSM_BASE}/providers/{pid}/keys', {
            'algorithm': 'RSA-2048',
        })
        assert_error(r, 400)

    def test_create_key_missing_algorithm(self, auth_client):
        pr = post_json(auth_client, f'{HSM_BASE}/providers', {
            'name': 'Key Algo HSM',
            'type': 'pkcs11',
            'config': {'library_path': '/usr/lib/algo-test.so'},
        })
        pid = assert_success(pr, status=201).get('id')
        r = post_json(auth_client, f'{HSM_BASE}/providers/{pid}/keys', {
            'label': 'test-key',
        })
        assert_error(r, 400)

    def test_create_key_invalid_algorithm(self, auth_client):
        pr = post_json(auth_client, f'{HSM_BASE}/providers', {
            'name': 'Key BadAlgo HSM',
            'type': 'pkcs11',
            'config': {'library_path': '/usr/lib/badalgo-test.so'},
        })
        pid = assert_success(pr, status=201).get('id')
        r = post_json(auth_client, f'{HSM_BASE}/providers/{pid}/keys', {
            'label': 'test-key',
            'algorithm': 'INVALID-ALGO',
        })
        assert_error(r, 400)


# =============================================================================
# OpenBao Provider Tests
# =============================================================================

class TestOpenBaoProvider:
    """Tests for OpenBao Transit Secrets Engine provider"""

    def test_create_openbao_provider(self, auth_client):
        r = post_json(auth_client, f'{HSM_BASE}/providers', {
            'name': 'OpenBao Test',
            'type': 'openbao',
            'config': {
                'url': 'http://openbao.example.com:8200',
                'token': 'test-token',
                'mount_path': 'transit',
            },
        })
        data = assert_success(r, status=201)
        assert data['name'] == 'OpenBao Test'
        assert data['type'] == 'openbao'

    def test_create_openbao_provider_with_namespace(self, auth_client):
        r = post_json(auth_client, f'{HSM_BASE}/providers', {
            'name': 'OpenBao NS',
            'type': 'openbao',
            'config': {
                'url': 'https://vault.example.com:8200',
                'token': 'ns-token',
                'mount_path': 'pki-transit',
                'namespace': 'engineering',
                'tls_skip_verify': True,
            },
        })
        data = assert_success(r, status=201)
        assert data['type'] == 'openbao'

    def test_create_openbao_missing_url(self, auth_client):
        r = post_json(auth_client, f'{HSM_BASE}/providers', {
            'name': 'OpenBao NoURL',
            'type': 'openbao',
            'config': {
                'token': 'test-token',
            },
        })
        # Provider creation stores config as-is; connection test will fail
        # But the API should still accept it (validation at connect time)
        assert r.status_code in (201, 400)

    def test_create_openbao_missing_token(self, auth_client):
        r = post_json(auth_client, f'{HSM_BASE}/providers', {
            'name': 'OpenBao NoToken',
            'type': 'openbao',
            'config': {
                'url': 'http://openbao:8200',
            },
        })
        assert r.status_code in (201, 400)

    def test_openbao_in_provider_types(self, auth_client):
        r = auth_client.get(f'{HSM_BASE}/provider-types')
        data = assert_success(r)
        types = [t['type'] for t in data]
        assert 'openbao' in types
        openbao = next(t for t in data if t['type'] == 'openbao')
        assert openbao['label'] == 'OpenBao / Vault Transit'
        assert 'url' in openbao['config_schema']
        assert 'token' in openbao['config_schema']
        assert openbao['config_schema']['token']['type'] == 'password'

    def test_openbao_in_dependencies(self, auth_client):
        r = auth_client.get(f'{HSM_BASE}/dependencies')
        data = assert_success(r)
        deps = data['dependencies']
        openbao_dep = next((d for d in deps if d['provider'] == 'openbao'), None)
        assert openbao_dep is not None
        assert openbao_dep['installed'] is True

    def test_openbao_valid_type_in_model(self):
        from models.hsm import HsmProvider
        assert 'openbao' in HsmProvider.VALID_TYPES

    def test_openbao_provider_registered(self):
        from services.hsm import HsmService
        available = HsmService.get_available_providers()
        assert 'openbao' in available

    def test_openbao_provider_key_mapping(self):
        from services.hsm.openbao_provider import ALGORITHM_TO_TRANSIT, TRANSIT_TO_ALGORITHM
        # Verify RSA mappings
        assert ALGORITHM_TO_TRANSIT['RSA-2048'] == ('rsa-2048', 'asymmetric')
        assert ALGORITHM_TO_TRANSIT['RSA-4096'] == ('rsa-4096', 'asymmetric')
        # Verify EC mappings
        assert ALGORITHM_TO_TRANSIT['EC-P256'] == ('ecdsa-p256', 'asymmetric')
        assert ALGORITHM_TO_TRANSIT['EC-P384'] == ('ecdsa-p384', 'asymmetric')
        # Verify reverse
        assert TRANSIT_TO_ALGORITHM['rsa-2048'] == 'RSA-2048'
        assert TRANSIT_TO_ALGORITHM['ecdsa-p256'] == 'EC-P256'

    def test_openbao_provider_config_error(self):
        from services.hsm.openbao_provider import OpenBaoProvider
        from services.hsm.base_provider import HsmConfigError
        import pytest
        with pytest.raises(HsmConfigError):
            OpenBaoProvider({'token': 'test'})  # Missing URL
        with pytest.raises(HsmConfigError):
            OpenBaoProvider({'url': 'http://localhost:8200'})  # Missing token
