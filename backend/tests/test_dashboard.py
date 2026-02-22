"""
Dashboard & Stats API Tests — /api/v2/dashboard/* and /api/v2/stats/*

Tests all dashboard endpoints:
- GET /api/v2/stats/overview — public stats (no auth)
- GET /api/v2/dashboard/stats — dashboard statistics
- GET /api/v2/dashboard/recent-cas — recently created CAs
- GET /api/v2/dashboard/expiring-certs — expiring certificates
- GET /api/v2/dashboard/activity — recent activity/audit entries
- GET /api/v2/dashboard/certificate-trend — cert creation trend
- GET /api/v2/dashboard/system-status — system health (no auth)

Uses shared conftest fixtures: app, client, auth_client, create_ca, create_cert.
"""
import json

CONTENT_JSON = 'application/json'
STATS_OVERVIEW = '/api/v2/stats/overview'
DASH = '/api/v2/dashboard'


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


# ============================================================
# Auth Required — authenticated endpoints must reject unauthed
# ============================================================

class TestAuthRequired:
    """Dashboard endpoints that require auth must return 401."""

    def test_dashboard_stats_requires_auth(self, client):
        assert client.get(f'{DASH}/stats').status_code == 401

    def test_recent_cas_requires_auth(self, client):
        assert client.get(f'{DASH}/recent-cas').status_code == 401

    def test_expiring_certs_requires_auth(self, client):
        assert client.get(f'{DASH}/expiring-certs').status_code == 401

    def test_activity_requires_auth(self, client):
        assert client.get(f'{DASH}/activity').status_code == 401

    def test_certificate_trend_requires_auth(self, client):
        assert client.get(f'{DASH}/certificate-trend').status_code == 401


# ============================================================
# Public Endpoints (no auth)
# ============================================================

class TestPublicEndpoints:
    """Endpoints that do NOT require authentication."""

    def test_stats_overview_no_auth(self, client):
        r = client.get(STATS_OVERVIEW)
        data = assert_success(r)
        assert 'total_cas' in data
        assert 'total_certs' in data
        assert 'active_users' in data

    def test_stats_overview_returns_integers(self, client):
        r = client.get(STATS_OVERVIEW)
        data = assert_success(r)
        assert isinstance(data['total_cas'], int)
        assert isinstance(data['total_certs'], int)

    def test_system_status_no_auth(self, client):
        r = client.get(f'{DASH}/system-status')
        data = assert_success(r)
        assert 'database' in data
        assert 'core' in data
        assert data['database']['status'] in ('online', 'offline')
        assert data['core']['status'] == 'online'

    def test_system_status_has_services(self, client):
        r = client.get(f'{DASH}/system-status')
        data = assert_success(r)
        for svc in ('database', 'acme', 'scep', 'core'):
            assert svc in data
            assert 'status' in data[svc]
            assert 'message' in data[svc]


# ============================================================
# Dashboard Stats
# ============================================================

class TestDashboardStats:
    """GET /api/v2/dashboard/stats"""

    def test_stats_returns_expected_keys(self, auth_client):
        r = auth_client.get(f'{DASH}/stats')
        data = assert_success(r)
        for key in ('total_cas', 'total_certificates', 'expiring_soon', 'revoked', 'pending_csrs'):
            assert key in data, f'Missing key: {key}'

    def test_stats_values_are_integers(self, auth_client):
        r = auth_client.get(f'{DASH}/stats')
        data = assert_success(r)
        assert isinstance(data['total_cas'], int)
        assert isinstance(data['total_certificates'], int)
        assert isinstance(data['expiring_soon'], int)
        assert isinstance(data['revoked'], int)

    def test_stats_reflect_created_ca(self, auth_client, create_ca):
        """After creating a CA, dashboard stats should count it."""
        r1 = auth_client.get(f'{DASH}/stats')
        before = assert_success(r1)['total_cas']

        create_ca(cn='Dashboard Stats Test CA')

        r2 = auth_client.get(f'{DASH}/stats')
        after = assert_success(r2)['total_cas']
        assert after > before

    def test_stats_reflect_created_cert(self, auth_client, create_cert):
        """After creating a cert, dashboard stats should count it."""
        r1 = auth_client.get(f'{DASH}/stats')
        before = assert_success(r1)['total_certificates']

        create_cert(cn='dashboard-stats-test.example.com')

        r2 = auth_client.get(f'{DASH}/stats')
        after = assert_success(r2)['total_certificates']
        assert after > before


# ============================================================
# Recent CAs
# ============================================================

class TestRecentCAs:
    """GET /api/v2/dashboard/recent-cas"""

    def test_recent_cas_returns_list(self, auth_client):
        r = auth_client.get(f'{DASH}/recent-cas')
        data = assert_success(r)
        assert isinstance(data, list)

    def test_recent_cas_limit(self, auth_client):
        r = auth_client.get(f'{DASH}/recent-cas?limit=2')
        data = assert_success(r)
        assert len(data) <= 2

    def test_recent_cas_entry_structure(self, auth_client, create_ca):
        create_ca(cn='Recent CA Structure Test')
        r = auth_client.get(f'{DASH}/recent-cas?limit=1')
        data = assert_success(r)
        assert len(data) >= 1
        entry = data[0]
        assert 'id' in entry
        assert 'common_name' in entry or 'descr' in entry


# ============================================================
# Expiring Certificates
# ============================================================

class TestExpiringCerts:
    """GET /api/v2/dashboard/expiring-certs"""

    def test_expiring_certs_returns_list(self, auth_client):
        r = auth_client.get(f'{DASH}/expiring-certs')
        data = assert_success(r)
        assert isinstance(data, list)

    def test_expiring_certs_limit(self, auth_client):
        r = auth_client.get(f'{DASH}/expiring-certs?limit=3')
        data = assert_success(r)
        assert len(data) <= 3

    def test_expiring_certs_after_create(self, auth_client, create_cert):
        """A newly created cert should appear in expiring list (sorted by soonest)."""
        create_cert(cn='expiring-test.example.com', validity_days=30)
        r = auth_client.get(f'{DASH}/expiring-certs?limit=50')
        data = assert_success(r)
        assert isinstance(data, list)
        # Should have at least the cert we just created
        assert len(data) >= 1
        # Each entry should have valid_to
        for cert in data:
            assert 'valid_to' in cert


# ============================================================
# Activity Log
# ============================================================

class TestActivityLog:
    """GET /api/v2/dashboard/activity"""

    def test_activity_returns_structure(self, auth_client):
        r = auth_client.get(f'{DASH}/activity')
        data = assert_success(r)
        assert 'activity' in data
        assert isinstance(data['activity'], list)

    def test_activity_limit(self, auth_client):
        r = auth_client.get(f'{DASH}/activity?limit=5')
        data = assert_success(r)
        assert len(data['activity']) <= 5

    def test_activity_entry_structure(self, auth_client):
        """Activity entries should have type, action, message, timestamp, user."""
        r = auth_client.get(f'{DASH}/activity?limit=5')
        data = assert_success(r)
        if data['activity']:
            entry = data['activity'][0]
            for key in ('type', 'action', 'message', 'timestamp', 'user'):
                assert key in entry, f'Missing key: {key}'


# ============================================================
# Certificate Trend
# ============================================================

class TestCertificateTrend:
    """GET /api/v2/dashboard/certificate-trend"""

    def test_trend_returns_structure(self, auth_client):
        r = auth_client.get(f'{DASH}/certificate-trend')
        data = assert_success(r)
        assert 'trend' in data
        assert isinstance(data['trend'], list)

    def test_trend_default_7_days(self, auth_client):
        r = auth_client.get(f'{DASH}/certificate-trend')
        data = assert_success(r)
        assert len(data['trend']) == 7

    def test_trend_custom_days(self, auth_client):
        r = auth_client.get(f'{DASH}/certificate-trend?days=14')
        data = assert_success(r)
        assert len(data['trend']) == 14

    def test_trend_entry_has_fields(self, auth_client):
        r = auth_client.get(f'{DASH}/certificate-trend?days=3')
        data = assert_success(r)
        assert len(data['trend']) == 3
        entry = data['trend'][0]
        for key in ('name', 'date', 'issued', 'revoked', 'expired'):
            assert key in entry, f'Missing key: {key}'

    def test_trend_clamped_max_90(self, auth_client):
        r = auth_client.get(f'{DASH}/certificate-trend?days=200')
        data = assert_success(r)
        assert len(data['trend']) <= 90
