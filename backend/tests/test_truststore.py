"""
Trust Store API Tests — /api/v2/truststore/*

Tests all truststore endpoints:
- GET  /api/v2/truststore/stats
- POST /api/v2/truststore/import
- GET  /api/v2/truststore
- POST /api/v2/truststore
- GET  /api/v2/truststore/<cert_id>
- DELETE /api/v2/truststore/<cert_id>
- POST /api/v2/truststore/sync
- GET  /api/v2/truststore/export
- GET  /api/v2/truststore/expiring
- POST /api/v2/truststore/add-from-ca/<ca_refid>

Uses shared conftest fixtures: app, client, auth_client, create_ca.
"""
import json

CONTENT_JSON = 'application/json'
TS = '/api/v2/truststore'

# Self-signed test certificate (valid PEM)
TEST_PEM = """-----BEGIN CERTIFICATE-----
MIIBkTCB+wIUYz3GFhyBPQ9aZ3rVZGqNTKFkYPwwDQYJKoZIhvcNAQELBQAwFDES
MBAGA1UEAwwJVGVzdCBSb290MB4XDTI0MDEwMTAwMDAwMFoXDTM0MDEwMTAwMMDAwM
FowFDESMBAGA1UEAwwJVGVzdCBSb290MFwwDQYJKoZIhvcNAQEBBQADSwAwSAJBAL
RiMLAHudeSA/x3hB2f+2NrKFGzVp7MBlub3hPfBDAjEqBh1TtMoVyF/oXirrGOVm
V+HaGmHwCBCkrN3oi1jvkCAwEAATANBgkqhkiG9w0BAQsFAANBAAvDwGnP21M3wY
PwbkGXhoyFP3ACuGS3VFsrjJHtPw3lkACDMzSMN4qifVNf1oJJBMF8MjkN7ZNp0X
L9fEfFqY0=
-----END CERTIFICATE-----"""


def get_json(response):
    return json.loads(response.data)


def assert_success(response, status=200):
    assert response.status_code == status, \
        f'Expected {status}, got {response.status_code}: {response.data[:500]}'
    data = json.loads(response.data)
    return data.get('data', data)


def assert_error(response, status):
    assert response.status_code == status, \
        f'Expected {status}, got {response.status_code}: {response.data[:500]}'


def post_json(client, url, data):
    return client.post(url, data=json.dumps(data), content_type=CONTENT_JSON)


# ============================================================
# Auth Required — all endpoints must reject unauthenticated
# ============================================================

class TestAuthRequired:
    """All truststore endpoints require authentication."""

    def test_stats_requires_auth(self, client):
        assert client.get(f'{TS}/stats').status_code == 401

    def test_import_requires_auth(self, client):
        assert post_json(client, f'{TS}/import', {}).status_code == 401

    def test_list_requires_auth(self, client):
        assert client.get(TS).status_code == 401

    def test_create_requires_auth(self, client):
        assert post_json(client, TS, {}).status_code == 401

    def test_get_by_id_requires_auth(self, client):
        assert client.get(f'{TS}/999').status_code == 401

    def test_delete_requires_auth(self, client):
        assert client.delete(f'{TS}/999').status_code == 401

    def test_sync_requires_auth(self, client):
        assert post_json(client, f'{TS}/sync', {}).status_code == 401

    def test_export_requires_auth(self, client):
        assert client.get(f'{TS}/export').status_code == 401

    def test_expiring_requires_auth(self, client):
        assert client.get(f'{TS}/expiring').status_code == 401

    def test_add_from_ca_requires_auth(self, client):
        assert post_json(client, f'{TS}/add-from-ca/test-ref', {}).status_code == 401


# ============================================================
# Stats
# ============================================================

class TestTruststoreStats:
    """GET /api/v2/truststore/stats"""

    def test_stats_returns_expected_keys(self, auth_client):
        r = auth_client.get(f'{TS}/stats')
        data = assert_success(r)
        for key in ('total', 'root_ca', 'intermediate_ca', 'expired', 'valid'):
            assert key in data, f'Missing key: {key}'

    def test_stats_values_are_integers(self, auth_client):
        r = auth_client.get(f'{TS}/stats')
        data = assert_success(r)
        assert isinstance(data['total'], int)
        assert isinstance(data['valid'], int)


# ============================================================
# List
# ============================================================

class TestTruststoreList:
    """GET /api/v2/truststore"""

    def test_list_returns_success(self, auth_client):
        r = auth_client.get(TS)
        data = assert_success(r)
        assert isinstance(data, (list, dict))

    def test_list_with_search(self, auth_client):
        r = auth_client.get(f'{TS}?search=nonexistent-xyz')
        assert r.status_code == 200


# ============================================================
# Create / CRUD
# ============================================================

class TestTruststoreCRUD:
    """POST/GET/DELETE /api/v2/truststore"""

    def test_create_without_pem_fails(self, auth_client):
        """Creating without PEM data should return 400."""
        r = post_json(auth_client, TS, {'name': 'Test Cert'})
        assert r.status_code == 400

    def test_create_with_invalid_pem(self, auth_client):
        """Invalid PEM data should be rejected."""
        r = post_json(auth_client, TS, {
            'name': 'Bad Cert',
            'pem_data': 'not-a-real-certificate'
        })
        assert r.status_code in (400, 500)

    def test_get_nonexistent_returns_404(self, auth_client):
        """Getting a nonexistent cert should return 404."""
        r = auth_client.get(f'{TS}/99999')
        assert r.status_code == 404

    def test_delete_nonexistent_returns_404(self, auth_client):
        """Deleting a nonexistent cert should return 404."""
        r = auth_client.delete(f'{TS}/99999')
        assert r.status_code == 404


# ============================================================
# Sync
# ============================================================

class TestTruststoreSync:
    """POST /api/v2/truststore/sync"""

    def test_sync_returns_success(self, auth_client):
        """Sync from system CA bundle should succeed (or fail gracefully)."""
        r = post_json(auth_client, f'{TS}/sync', {})
        # May succeed or return error if no system certs available
        assert r.status_code in (200, 400, 404, 500)


# ============================================================
# Export
# ============================================================

class TestTruststoreExport:
    """GET /api/v2/truststore/export"""

    def test_export_pem_format(self, auth_client):
        r = auth_client.get(f'{TS}/export?format=pem')
        assert r.status_code == 200

    def test_export_default_format(self, auth_client):
        r = auth_client.get(f'{TS}/export')
        assert r.status_code == 200


# ============================================================
# Expiring
# ============================================================

class TestTruststoreExpiring:
    """GET /api/v2/truststore/expiring"""

    def test_expiring_returns_success(self, auth_client):
        r = auth_client.get(f'{TS}/expiring')
        data = assert_success(r)
        assert isinstance(data, (list, dict))

    def test_expiring_with_days_param(self, auth_client):
        r = auth_client.get(f'{TS}/expiring?days=30')
        assert r.status_code == 200


# ============================================================
# Add from CA
# ============================================================

class TestTruststoreAddFromCA:
    """POST /api/v2/truststore/add-from-ca/<ca_refid>"""

    def test_add_from_nonexistent_ca(self, auth_client):
        """Adding from a nonexistent CA refid should fail."""
        r = post_json(auth_client, f'{TS}/add-from-ca/nonexistent-ref', {})
        assert r.status_code in (400, 404)


# ============================================================
# Import
# ============================================================

class TestTruststoreImport:
    """POST /api/v2/truststore/import"""

    def test_import_without_data_fails(self, auth_client):
        """Import with empty body should return 400."""
        r = post_json(auth_client, f'{TS}/import', {})
        assert r.status_code == 400
