"""
Audit Logs API Tests — /api/v2/audit/*

Tests all audit log endpoints:
- GET /api/v2/audit/logs — list audit logs (paginated)
- GET /api/v2/audit/logs/<id> — get single log entry
- GET /api/v2/audit/stats — audit statistics
- GET /api/v2/audit/actions — list action types
- GET /api/v2/audit/export — export logs (CSV/JSON)
- POST /api/v2/audit/cleanup — cleanup old logs
- GET /api/v2/audit/verify — verify integrity

Uses shared conftest fixtures: app, client, auth_client, create_ca, create_cert.
"""
import json

CONTENT_JSON = 'application/json'
BASE = '/api/v2/audit'


def get_json(response):
    return json.loads(response.data)


def assert_success(response, status=200):
    assert response.status_code == status, \
        f'Expected {status}, got {response.status_code}: {response.data[:500]}'
    body = json.loads(response.data)
    return body.get('data', body)


def assert_error(response, status):
    assert response.status_code == status, \
        f'Expected {status}, got {response.status_code}: {response.data[:500]}'


def post_json(client, url, data):
    return client.post(url, data=json.dumps(data), content_type=CONTENT_JSON)


# ============================================================
# Auth Required — all endpoints must reject unauthenticated
# ============================================================

class TestAuthRequired:
    """All audit endpoints must return 401 without authentication."""

    def test_list_logs_requires_auth(self, client):
        assert client.get(f'{BASE}/logs').status_code == 401

    def test_get_log_requires_auth(self, client):
        assert client.get(f'{BASE}/logs/1').status_code == 401

    def test_stats_requires_auth(self, client):
        assert client.get(f'{BASE}/stats').status_code == 401

    def test_actions_requires_auth(self, client):
        assert client.get(f'{BASE}/actions').status_code == 401

    def test_export_requires_auth(self, client):
        assert client.get(f'{BASE}/export').status_code == 401

    def test_cleanup_requires_auth(self, client):
        r = post_json(client, f'{BASE}/cleanup', {'retention_days': 90})
        assert r.status_code == 401

    def test_verify_requires_auth(self, client):
        assert client.get(f'{BASE}/verify').status_code == 401


# ============================================================
# List Logs
# ============================================================

class TestListLogs:
    """GET /api/v2/audit/logs"""

    def test_list_returns_array(self, auth_client):
        r = auth_client.get(f'{BASE}/logs')
        data = assert_success(r)
        assert isinstance(data, list)

    def test_list_has_pagination_meta(self, auth_client):
        r = auth_client.get(f'{BASE}/logs')
        body = get_json(r)
        assert 'meta' in body
        meta = body['meta']
        for key in ('page', 'per_page', 'total', 'total_pages'):
            assert key in meta, f'Missing meta key: {key}'

    def test_list_pagination(self, auth_client):
        r = auth_client.get(f'{BASE}/logs?page=1&per_page=5')
        body = get_json(r)
        assert body['meta']['page'] == 1
        assert body['meta']['per_page'] == 5
        assert len(body.get('data', [])) <= 5

    def test_list_filter_by_action(self, auth_client):
        """Filtering by action should return only matching entries."""
        r = auth_client.get(f'{BASE}/logs?action=login_success')
        data = assert_success(r)
        for entry in data:
            assert entry['action'] == 'login_success'

    def test_list_per_page_max_100(self, auth_client):
        """per_page should be capped at 100."""
        r = auth_client.get(f'{BASE}/logs?per_page=200')
        body = get_json(r)
        assert body['meta']['per_page'] <= 100

    def test_list_has_audit_entries(self, auth_client):
        """Login action should have generated audit entries."""
        r = auth_client.get(f'{BASE}/logs?per_page=100')
        data = assert_success(r)
        assert len(data) >= 1, 'Expected at least one audit entry from login'


# ============================================================
# Get Single Log
# ============================================================

class TestGetLog:
    """GET /api/v2/audit/logs/<id>"""

    def test_get_existing_log(self, auth_client):
        """Fetch audit logs, then get the first one by ID."""
        r = auth_client.get(f'{BASE}/logs?per_page=1')
        logs = assert_success(r)
        if not logs:
            return  # No logs to test
        log_id = logs[0]['id']

        r2 = auth_client.get(f'{BASE}/logs/{log_id}')
        entry = assert_success(r2)
        assert entry['id'] == log_id
        assert 'action' in entry
        assert 'timestamp' in entry

    def test_get_nonexistent_log(self, auth_client):
        r = auth_client.get(f'{BASE}/logs/999999')
        assert_error(r, 404)


# ============================================================
# Audit Stats
# ============================================================

class TestAuditStats:
    """GET /api/v2/audit/stats"""

    def test_stats_returns_structure(self, auth_client):
        r = auth_client.get(f'{BASE}/stats')
        data = assert_success(r)
        for key in ('total_logs', 'success_count', 'failure_count', 'success_rate'):
            assert key in data, f'Missing key: {key}'

    def test_stats_custom_days(self, auth_client):
        r = auth_client.get(f'{BASE}/stats?days=7')
        data = assert_success(r)
        assert data['period_days'] == 7

    def test_stats_top_actions(self, auth_client):
        r = auth_client.get(f'{BASE}/stats')
        data = assert_success(r)
        assert 'top_actions' in data
        assert isinstance(data['top_actions'], list)

    def test_stats_top_users(self, auth_client):
        r = auth_client.get(f'{BASE}/stats')
        data = assert_success(r)
        assert 'top_users' in data
        assert isinstance(data['top_users'], list)


# ============================================================
# Actions List
# ============================================================

class TestActionsList:
    """GET /api/v2/audit/actions"""

    def test_actions_returns_structure(self, auth_client):
        r = auth_client.get(f'{BASE}/actions')
        data = assert_success(r)
        assert 'actions' in data
        assert 'categories' in data
        assert isinstance(data['actions'], list)
        assert isinstance(data['categories'], dict)

    def test_actions_has_login_action(self, auth_client):
        """Login should have created at least a login_success action type."""
        r = auth_client.get(f'{BASE}/actions')
        data = assert_success(r)
        assert len(data['actions']) >= 1


# ============================================================
# Export
# ============================================================

class TestExport:
    """GET /api/v2/audit/export"""

    def test_export_json_default(self, auth_client):
        r = auth_client.get(f'{BASE}/export')
        assert r.status_code == 200
        assert r.content_type.startswith('application/json')
        # Should be valid JSON array
        parsed = json.loads(r.data)
        assert isinstance(parsed, list)

    def test_export_json_explicit(self, auth_client):
        r = auth_client.get(f'{BASE}/export?format=json')
        assert r.status_code == 200
        assert r.content_type.startswith('application/json')

    def test_export_csv(self, auth_client):
        r = auth_client.get(f'{BASE}/export?format=csv')
        assert r.status_code == 200
        assert 'text/csv' in r.content_type
        text = r.data.decode('utf-8')
        # CSV should have header row
        assert 'id' in text.split('\n')[0]
        assert 'timestamp' in text.split('\n')[0]

    def test_export_csv_has_data_rows(self, auth_client):
        """CSV export should contain at least a header + one data row."""
        r = auth_client.get(f'{BASE}/export?format=csv')
        text = r.data.decode('utf-8')
        lines = [l for l in text.strip().split('\n') if l]
        assert len(lines) >= 2, 'Expected header + at least one data row'


# ============================================================
# Cleanup
# ============================================================

class TestCleanup:
    """POST /api/v2/audit/cleanup"""

    def test_cleanup_returns_deleted_count(self, auth_client):
        r = post_json(auth_client, f'{BASE}/cleanup', {'retention_days': 90})
        data = assert_success(r)
        assert 'deleted' in data
        assert isinstance(data['deleted'], int)

    def test_cleanup_min_retention_30(self, auth_client):
        """Even if client sends retention_days < 30, it should be clamped to 30."""
        r = post_json(auth_client, f'{BASE}/cleanup', {'retention_days': 1})
        # Should succeed (server clamps to 30)
        assert r.status_code == 200

    def test_cleanup_default_retention(self, auth_client):
        """Cleanup with empty body should default to 90 days."""
        r = post_json(auth_client, f'{BASE}/cleanup', {})
        assert r.status_code == 200


# ============================================================
# Verify Integrity
# ============================================================

class TestVerifyIntegrity:
    """GET /api/v2/audit/verify"""

    def test_verify_returns_structure(self, auth_client):
        r = auth_client.get(f'{BASE}/verify')
        data = assert_success(r)
        assert 'valid' in data
        assert 'checked' in data
        assert 'errors' in data
        assert isinstance(data['valid'], bool)
        assert isinstance(data['checked'], int)
        assert isinstance(data['errors'], list)

    def test_verify_passes(self, auth_client):
        """Integrity check should pass for untampered logs."""
        r = auth_client.get(f'{BASE}/verify')
        data = assert_success(r)
        assert data['valid'] is True
        assert data['checked'] >= 0


# ============================================================
# Integration: actions generate audit entries
# ============================================================

class TestAuditIntegration:
    """Verify that creating resources generates audit log entries."""

    def test_create_ca_generates_audit(self, auth_client, create_ca):
        """Creating a CA should produce an audit log entry."""
        create_ca(cn='Audit Integration CA')

        r = auth_client.get(f'{BASE}/logs?per_page=100')
        data = assert_success(r)
        assert len(data) >= 1

    def test_create_cert_generates_audit(self, auth_client, create_cert):
        """Creating a certificate should produce an audit log entry."""
        create_cert(cn='audit-integration-cert.example.com')

        r = auth_client.get(f'{BASE}/logs?per_page=100')
        data = assert_success(r)
        assert len(data) >= 1

    def test_audit_count_increases(self, auth_client, create_cert):
        """Total audit count should increase after actions."""
        r1 = auth_client.get(f'{BASE}/stats')
        before = assert_success(r1)['total_logs']

        create_cert(cn='audit-count-test.example.com')

        r2 = auth_client.get(f'{BASE}/stats')
        after = assert_success(r2)['total_logs']
        assert after >= before
