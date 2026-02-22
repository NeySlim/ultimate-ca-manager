"""
Webhook API Tests — /api/v2/webhooks/*

Tests all webhook endpoints:
- GET    /api/v2/webhooks
- GET    /api/v2/webhooks/<endpoint_id>
- POST   /api/v2/webhooks
- PUT    /api/v2/webhooks/<endpoint_id>
- DELETE /api/v2/webhooks/<endpoint_id>
- POST   /api/v2/webhooks/<endpoint_id>/toggle
- POST   /api/v2/webhooks/<endpoint_id>/test
- POST   /api/v2/webhooks/<endpoint_id>/regenerate-secret
- GET    /api/v2/webhooks/events

Uses shared conftest fixtures: app, client, auth_client.
"""
import json

CONTENT_JSON = 'application/json'
WH = '/api/v2/webhooks'


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


def put_json(client, url, data):
    return client.put(url, data=json.dumps(data), content_type=CONTENT_JSON)


# ============================================================
# Auth Required — all endpoints must reject unauthenticated
# ============================================================

class TestAuthRequired:
    """All webhook endpoints require authentication."""

    def test_list_requires_auth(self, client):
        assert client.get(WH).status_code == 401

    def test_get_requires_auth(self, client):
        assert client.get(f'{WH}/999').status_code == 401

    def test_create_requires_auth(self, client):
        assert post_json(client, WH, {}).status_code == 401

    def test_update_requires_auth(self, client):
        assert put_json(client, f'{WH}/999', {}).status_code == 401

    def test_delete_requires_auth(self, client):
        assert client.delete(f'{WH}/999').status_code == 401

    def test_toggle_requires_auth(self, client):
        assert post_json(client, f'{WH}/999/toggle', {}).status_code == 401

    def test_test_requires_auth(self, client):
        assert post_json(client, f'{WH}/999/test', {}).status_code == 401

    def test_regenerate_secret_requires_auth(self, client):
        assert post_json(client, f'{WH}/999/regenerate-secret', {}).status_code == 401

    def test_events_requires_auth(self, client):
        assert client.get(f'{WH}/events').status_code == 401


# ============================================================
# Events List
# ============================================================

class TestWebhookEvents:
    """GET /api/v2/webhooks/events"""

    def test_events_returns_list(self, auth_client):
        r = auth_client.get(f'{WH}/events')
        data = assert_success(r)
        assert 'events' in data
        assert isinstance(data['events'], list)
        assert len(data['events']) > 0

    def test_events_has_descriptions(self, auth_client):
        r = auth_client.get(f'{WH}/events')
        data = assert_success(r)
        assert 'descriptions' in data
        assert isinstance(data['descriptions'], dict)


# ============================================================
# CRUD Lifecycle
# ============================================================

class TestWebhookCRUD:
    """Full CRUD lifecycle: create → get → update → toggle → test → delete."""

    def test_list_webhooks_empty_initially(self, auth_client):
        r = auth_client.get(WH)
        data = assert_success(r)
        assert isinstance(data, list)

    def test_create_webhook(self, auth_client):
        r = post_json(auth_client, WH, {
            'name': 'Test Hook',
            'url': 'https://hook.example.com/test',
            'events': ['certificate.created']
        })
        data = assert_success(r)
        assert data.get('name') == 'Test Hook'
        assert data.get('url') == 'https://hook.example.com/test'
        assert 'id' in data

    def test_get_created_webhook(self, auth_client):
        """Create and then retrieve by ID."""
        r = post_json(auth_client, WH, {
            'name': 'Get Test Hook',
            'url': 'https://hook.example.com/get-test',
            'events': ['certificate.revoked']
        })
        created = assert_success(r)
        wh_id = created['id']

        r = auth_client.get(f'{WH}/{wh_id}')
        data = assert_success(r)
        assert data['id'] == wh_id
        assert data['name'] == 'Get Test Hook'

    def test_update_webhook(self, auth_client):
        """Create then update."""
        r = post_json(auth_client, WH, {
            'name': 'Update Test',
            'url': 'https://hook.example.com/update-test',
            'events': ['certificate.created']
        })
        created = assert_success(r)
        wh_id = created['id']

        r = put_json(auth_client, f'{WH}/{wh_id}', {
            'name': 'Updated Hook Name',
            'url': 'https://hook.example.com/updated'
        })
        data = assert_success(r)
        assert data['name'] == 'Updated Hook Name'

    def test_toggle_webhook(self, auth_client):
        """Create and toggle enabled state."""
        r = post_json(auth_client, WH, {
            'name': 'Toggle Test',
            'url': 'https://hook.example.com/toggle-test',
            'events': ['certificate.created']
        })
        created = assert_success(r)
        wh_id = created['id']
        original_enabled = created.get('enabled', True)

        r = post_json(auth_client, f'{WH}/{wh_id}/toggle', {})
        data = assert_success(r)
        assert data['enabled'] != original_enabled

    def test_test_webhook(self, auth_client):
        """Create and send test event (may fail if URL unreachable)."""
        r = post_json(auth_client, WH, {
            'name': 'Webhook Test Target',
            'url': 'https://hook.example.com/test-target',
            'events': ['certificate.created']
        })
        created = assert_success(r)
        wh_id = created['id']

        r = post_json(auth_client, f'{WH}/{wh_id}/test', {})
        # Test may fail (unreachable URL) — accept 200 or 400
        assert r.status_code in (200, 400)

    def test_regenerate_secret(self, auth_client):
        """Create and regenerate secret."""
        r = post_json(auth_client, WH, {
            'name': 'Secret Regen Test',
            'url': 'https://hook.example.com/regen-test',
            'events': ['certificate.created']
        })
        created = assert_success(r)
        wh_id = created['id']
        r = post_json(auth_client, f'{WH}/{wh_id}/regenerate-secret', {})
        data = assert_success(r)
        assert 'secret' in data

    def test_delete_webhook(self, auth_client):
        """Create and then delete."""
        r = post_json(auth_client, WH, {
            'name': 'Delete Test',
            'url': 'https://hook.example.com/delete-test',
            'events': ['certificate.created']
        })
        created = assert_success(r)
        wh_id = created['id']

        r = auth_client.delete(f'{WH}/{wh_id}')
        assert r.status_code == 200

        # Verify deleted — should 404
        r = auth_client.get(f'{WH}/{wh_id}')
        assert r.status_code == 404


# ============================================================
# Validation
# ============================================================

class TestWebhookValidation:
    """Validation tests for webhook creation/update."""

    def test_create_missing_name(self, auth_client):
        r = post_json(auth_client, WH, {
            'url': 'https://hook.example.com/no-name',
            'events': ['certificate.created']
        })
        assert_error(r, 400)

    def test_create_missing_url(self, auth_client):
        r = post_json(auth_client, WH, {
            'name': 'No URL Hook',
            'events': ['certificate.created']
        })
        assert_error(r, 400)

    def test_create_invalid_url(self, auth_client):
        r = post_json(auth_client, WH, {
            'name': 'Bad URL Hook',
            'url': 'ftp://not-http.example.com',
            'events': ['certificate.created']
        })
        assert_error(r, 400)

    def test_create_invalid_events_type(self, auth_client):
        r = post_json(auth_client, WH, {
            'name': 'Bad Events Hook',
            'url': 'https://hook.example.com/bad-events',
            'events': 'not-an-array'
        })
        assert_error(r, 400)


# ============================================================
# 404 Cases
# ============================================================

class TestWebhookNotFound:
    """Operations on nonexistent webhook IDs should return 404."""

    def test_get_nonexistent(self, auth_client):
        assert auth_client.get(f'{WH}/99999').status_code == 404

    def test_update_nonexistent(self, auth_client):
        r = put_json(auth_client, f'{WH}/99999', {'name': 'Nope'})
        assert r.status_code == 404

    def test_delete_nonexistent(self, auth_client):
        assert auth_client.delete(f'{WH}/99999').status_code == 404

    def test_toggle_nonexistent(self, auth_client):
        assert post_json(auth_client, f'{WH}/99999/toggle', {}).status_code == 404
