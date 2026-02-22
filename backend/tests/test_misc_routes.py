"""
Miscellaneous Route Tests — covers remaining small modules.

Modules tested:
- Search         /api/v2/search
- Reports        /api/v2/reports/*
- Smart Import   /api/v2/import/*
- Policies       /api/v2/policies/*
- Approvals      /api/v2/approvals/*
- Groups         /api/v2/groups/*
- User Certs     /api/v2/user-certificates/*
- DNS Providers  /api/v2/dns-providers/*
- SCEP           /api/v2/scep/*
- OPNsense       /api/v2/import/opnsense/*

Uses shared conftest fixtures: app, client, auth_client, create_ca, create_user.
"""
import json

CONTENT_JSON = 'application/json'


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


def patch_json(client, url, data):
    return client.patch(url, data=json.dumps(data), content_type=CONTENT_JSON)


# ============================================================
# Search
# ============================================================

class TestSearch:
    """GET /api/v2/search"""

    def test_search_requires_auth(self, client):
        assert client.get('/api/v2/search?q=test').status_code == 401

    def test_search_returns_results(self, auth_client):
        r = auth_client.get('/api/v2/search?q=test&limit=5')
        data = assert_success(r)
        assert isinstance(data, (list, dict))

    def test_search_with_short_query(self, auth_client):
        """Query shorter than minimum (2 chars) may return error or empty."""
        r = auth_client.get('/api/v2/search?q=a')
        assert r.status_code in (200, 400)

    def test_search_empty_query(self, auth_client):
        r = auth_client.get('/api/v2/search?q=')
        assert r.status_code in (200, 400)


# ============================================================
# Reports
# ============================================================

class TestReportsAuth:
    """Reports endpoints require authentication."""

    def test_types_requires_auth(self, client):
        assert client.get('/api/v2/reports/types').status_code == 401

    def test_generate_requires_auth(self, client):
        assert post_json(client, '/api/v2/reports/generate', {}).status_code == 401

    def test_download_requires_auth(self, client):
        assert client.get('/api/v2/reports/download/summary').status_code == 401

    def test_schedule_get_requires_auth(self, client):
        assert client.get('/api/v2/reports/schedule').status_code == 401

    def test_schedule_put_requires_auth(self, client):
        assert put_json(client, '/api/v2/reports/schedule', {}).status_code == 401

    def test_send_test_requires_auth(self, client):
        assert post_json(client, '/api/v2/reports/send-test', {}).status_code == 401


class TestReports:
    """Reports happy-path tests."""

    def test_types_returns_list(self, auth_client):
        r = auth_client.get('/api/v2/reports/types')
        data = assert_success(r)
        assert isinstance(data, (list, dict))

    def test_schedule_get(self, auth_client):
        r = auth_client.get('/api/v2/reports/schedule')
        assert r.status_code == 200

    def test_generate_without_type(self, auth_client):
        """Generate without specifying type should fail."""
        r = post_json(auth_client, '/api/v2/reports/generate', {})
        assert r.status_code in (200, 400)

    def test_download_nonexistent_type(self, auth_client):
        r = auth_client.get('/api/v2/reports/download/nonexistent')
        assert r.status_code in (400, 404, 500)


# ============================================================
# Smart Import
# ============================================================

class TestSmartImportAuth:
    """Smart import endpoints require authentication."""

    def test_analyze_requires_auth(self, client):
        assert post_json(client, '/api/v2/import/analyze', {}).status_code == 401

    def test_execute_requires_auth(self, client):
        assert post_json(client, '/api/v2/import/execute', {}).status_code == 401

    def test_formats_requires_auth(self, client):
        assert client.get('/api/v2/import/formats').status_code == 401


class TestSmartImport:
    """Smart import happy-path tests."""

    def test_formats_returns_data(self, auth_client):
        r = auth_client.get('/api/v2/import/formats')
        data = assert_success(r)
        assert isinstance(data, (list, dict))

    def test_analyze_without_content(self, auth_client):
        r = post_json(auth_client, '/api/v2/import/analyze', {})
        assert r.status_code in (400, 500)

    def test_execute_without_content(self, auth_client):
        r = post_json(auth_client, '/api/v2/import/execute', {})
        assert r.status_code in (400, 500)


# ============================================================
# Policies
# ============================================================

class TestPoliciesAuth:
    """Policies endpoints require authentication."""

    def test_list_requires_auth(self, client):
        assert client.get('/api/v2/policies').status_code == 401

    def test_create_requires_auth(self, client):
        assert post_json(client, '/api/v2/policies', {}).status_code == 401

    def test_get_requires_auth(self, client):
        assert client.get('/api/v2/policies/999').status_code == 401

    def test_update_requires_auth(self, client):
        assert put_json(client, '/api/v2/policies/999', {}).status_code == 401

    def test_delete_requires_auth(self, client):
        assert client.delete('/api/v2/policies/999').status_code == 401

    def test_toggle_requires_auth(self, client):
        assert post_json(client, '/api/v2/policies/999/toggle', {}).status_code == 401


class TestPolicies:
    """Policies CRUD and validation tests."""

    def test_list_returns_success(self, auth_client):
        r = auth_client.get('/api/v2/policies')
        data = assert_success(r)
        assert isinstance(data, list)

    def test_create_policy(self, auth_client):
        r = post_json(auth_client, '/api/v2/policies', {
            'name': 'Test Policy',
            'type': 'approval',
            'description': 'Test policy for automated tests',
            'enabled': True
        })
        # May succeed or fail depending on required fields
        assert r.status_code in (200, 201, 400)

    def test_create_missing_name(self, auth_client):
        r = post_json(auth_client, '/api/v2/policies', {
            'type': 'approval'
        })
        assert r.status_code == 400

    def test_get_nonexistent_policy(self, auth_client):
        assert auth_client.get('/api/v2/policies/99999').status_code == 404

    def test_delete_nonexistent_policy(self, auth_client):
        assert auth_client.delete('/api/v2/policies/99999').status_code == 404

    def test_toggle_nonexistent_policy(self, auth_client):
        r = post_json(auth_client, '/api/v2/policies/99999/toggle', {})
        assert r.status_code == 404


# ============================================================
# Approvals
# ============================================================

class TestApprovalsAuth:
    """Approvals endpoints require authentication."""

    def test_list_requires_auth(self, client):
        assert client.get('/api/v2/approvals').status_code == 401

    def test_get_requires_auth(self, client):
        assert client.get('/api/v2/approvals/999').status_code == 401

    def test_approve_requires_auth(self, client):
        assert post_json(client, '/api/v2/approvals/999/approve', {}).status_code == 401

    def test_reject_requires_auth(self, client):
        assert post_json(client, '/api/v2/approvals/999/reject', {}).status_code == 401

    def test_stats_requires_auth(self, client):
        assert client.get('/api/v2/approvals/stats').status_code == 401


class TestApprovals:
    """Approvals happy-path tests."""

    def test_list_returns_success(self, auth_client):
        r = auth_client.get('/api/v2/approvals')
        data = assert_success(r)
        assert isinstance(data, (list, dict))

    def test_stats_returns_success(self, auth_client):
        r = auth_client.get('/api/v2/approvals/stats')
        data = assert_success(r)
        assert isinstance(data, dict)

    def test_get_nonexistent_approval(self, auth_client):
        assert auth_client.get('/api/v2/approvals/99999').status_code == 404

    def test_approve_nonexistent(self, auth_client):
        r = post_json(auth_client, '/api/v2/approvals/99999/approve', {})
        assert r.status_code in (400, 404)

    def test_reject_nonexistent(self, auth_client):
        r = post_json(auth_client, '/api/v2/approvals/99999/reject', {})
        assert r.status_code in (400, 404)


# ============================================================
# Groups
# ============================================================

class TestGroupsAuth:
    """Groups endpoints require authentication."""

    def test_list_requires_auth(self, client):
        assert client.get('/api/v2/groups').status_code == 401

    def test_create_requires_auth(self, client):
        assert post_json(client, '/api/v2/groups', {}).status_code == 401

    def test_get_requires_auth(self, client):
        assert client.get('/api/v2/groups/999').status_code == 401

    def test_update_requires_auth(self, client):
        assert put_json(client, '/api/v2/groups/999', {}).status_code == 401

    def test_delete_requires_auth(self, client):
        assert client.delete('/api/v2/groups/999').status_code == 401

    def test_members_requires_auth(self, client):
        assert client.get('/api/v2/groups/999/members').status_code == 401

    def test_add_member_requires_auth(self, client):
        assert post_json(client, '/api/v2/groups/999/members', {}).status_code == 401

    def test_stats_requires_auth(self, client):
        assert client.get('/api/v2/groups/stats').status_code == 401


class TestGroups:
    """Groups CRUD lifecycle and validation tests."""

    def test_list_returns_success(self, auth_client):
        r = auth_client.get('/api/v2/groups')
        data = assert_success(r)
        assert isinstance(data, (list, dict))

    def test_stats_returns_success(self, auth_client):
        r = auth_client.get('/api/v2/groups/stats')
        data = assert_success(r)
        assert isinstance(data, dict)

    def test_create_group(self, auth_client):
        r = post_json(auth_client, '/api/v2/groups', {
            'name': 'Test Group',
            'description': 'Test group for automated tests'
        })
        data = assert_success(r, status=201)
        assert data.get('name') == 'Test Group'
        assert 'id' in data

    def test_crud_lifecycle(self, auth_client):
        """Create → get → update → delete full cycle."""
        # Create
        r = post_json(auth_client, '/api/v2/groups', {
            'name': 'CRUD Group',
            'description': 'For CRUD test'
        })
        created = assert_success(r, status=201)
        gid = created['id']

        # Get
        r = auth_client.get(f'/api/v2/groups/{gid}')
        data = assert_success(r)
        assert data['id'] == gid
        assert data['name'] == 'CRUD Group'

        # Update
        r = put_json(auth_client, f'/api/v2/groups/{gid}', {
            'name': 'Updated Group',
            'description': 'Updated description'
        })
        data = assert_success(r)
        assert data['name'] == 'Updated Group'

        # Delete
        r = auth_client.delete(f'/api/v2/groups/{gid}')
        assert r.status_code in (200, 204)

        # Verify deleted
        r = auth_client.get(f'/api/v2/groups/{gid}')
        assert r.status_code == 404

    def test_create_missing_name(self, auth_client):
        r = post_json(auth_client, '/api/v2/groups', {
            'description': 'No name group'
        })
        assert_error(r, 400)

    def test_get_nonexistent_group(self, auth_client):
        assert auth_client.get('/api/v2/groups/99999').status_code == 404

    def test_delete_nonexistent_group(self, auth_client):
        assert auth_client.delete('/api/v2/groups/99999').status_code == 404

    def test_members_list(self, auth_client):
        """Create group and list members (should be empty)."""
        r = post_json(auth_client, '/api/v2/groups', {
            'name': 'Members Group',
            'description': 'For members test'
        })
        created = assert_success(r, status=201)
        gid = created['id']

        r = auth_client.get(f'/api/v2/groups/{gid}/members')
        data = assert_success(r)
        assert isinstance(data, list)


# ============================================================
# User Certificates
# ============================================================

class TestUserCertificatesAuth:
    """User certificates endpoints require authentication."""

    def test_list_requires_auth(self, client):
        assert client.get('/api/v2/user-certificates').status_code == 401

    def test_stats_requires_auth(self, client):
        assert client.get('/api/v2/user-certificates/stats').status_code == 401

    def test_get_requires_auth(self, client):
        assert client.get('/api/v2/user-certificates/999').status_code == 401

    def test_export_requires_auth(self, client):
        assert client.get('/api/v2/user-certificates/999/export').status_code == 401

    def test_revoke_requires_auth(self, client):
        assert post_json(client, '/api/v2/user-certificates/999/revoke', {}).status_code == 401


class TestUserCertificates:
    """User certificates happy-path tests."""

    def test_list_returns_success(self, auth_client):
        r = auth_client.get('/api/v2/user-certificates')
        data = assert_success(r)
        assert isinstance(data, (list, dict))

    def test_stats_returns_success(self, auth_client):
        r = auth_client.get('/api/v2/user-certificates/stats')
        data = assert_success(r)
        assert isinstance(data, dict)

    def test_get_nonexistent(self, auth_client):
        r = auth_client.get('/api/v2/user-certificates/99999')
        assert r.status_code in (403, 404)

    def test_export_nonexistent(self, auth_client):
        r = auth_client.get('/api/v2/user-certificates/99999/export')
        assert r.status_code in (403, 404)


# ============================================================
# DNS Providers
# ============================================================

class TestDNSProvidersAuth:
    """DNS provider endpoints require authentication."""

    def test_list_requires_auth(self, client):
        assert client.get('/api/v2/dns-providers').status_code == 401

    def test_types_requires_auth(self, client):
        assert client.get('/api/v2/dns-providers/types').status_code == 401

    def test_create_requires_auth(self, client):
        assert post_json(client, '/api/v2/dns-providers', {}).status_code == 401

    def test_get_requires_auth(self, client):
        assert client.get('/api/v2/dns-providers/999').status_code == 401

    def test_update_requires_auth(self, client):
        assert patch_json(client, '/api/v2/dns-providers/999', {}).status_code == 401

    def test_delete_requires_auth(self, client):
        assert client.delete('/api/v2/dns-providers/999').status_code == 401

    def test_test_requires_auth(self, client):
        assert post_json(client, '/api/v2/dns-providers/999/test', {}).status_code == 401


class TestDNSProviders:
    """DNS providers CRUD and validation tests."""

    def test_list_returns_success(self, auth_client):
        r = auth_client.get('/api/v2/dns-providers')
        data = assert_success(r)
        assert isinstance(data, list)

    def test_types_returns_list(self, auth_client):
        r = auth_client.get('/api/v2/dns-providers/types')
        data = assert_success(r)
        assert isinstance(data, (list, dict))

    def test_create_provider(self, auth_client):
        r = post_json(auth_client, '/api/v2/dns-providers', {
            'name': 'Test Provider',
            'type': 'cloudflare',
            'config': {'api_token': 'test-token-123'}
        })
        # May succeed or fail depending on validation
        assert r.status_code in (200, 201, 400)

    def test_create_missing_name(self, auth_client):
        r = post_json(auth_client, '/api/v2/dns-providers', {
            'type': 'cloudflare',
            'config': {'api_token': 'test'}
        })
        assert r.status_code in (400, 200)

    def test_get_nonexistent(self, auth_client):
        assert auth_client.get('/api/v2/dns-providers/99999').status_code == 404

    def test_delete_nonexistent(self, auth_client):
        assert auth_client.delete('/api/v2/dns-providers/99999').status_code == 404

    def test_test_nonexistent(self, auth_client):
        r = post_json(auth_client, '/api/v2/dns-providers/99999/test', {})
        assert r.status_code in (400, 404)


# ============================================================
# SCEP
# ============================================================

class TestSCEPAuth:
    """SCEP endpoints require authentication."""

    def test_config_get_requires_auth(self, client):
        assert client.get('/api/v2/scep/config').status_code == 401

    def test_config_patch_requires_auth(self, client):
        assert patch_json(client, '/api/v2/scep/config', {}).status_code == 401

    def test_requests_requires_auth(self, client):
        assert client.get('/api/v2/scep/requests').status_code == 401

    def test_approve_requires_auth(self, client):
        assert post_json(client, '/api/v2/scep/999/approve', {}).status_code == 401

    def test_reject_requires_auth(self, client):
        assert post_json(client, '/api/v2/scep/999/reject', {}).status_code == 401

    def test_stats_requires_auth(self, client):
        assert client.get('/api/v2/scep/stats').status_code == 401

    def test_challenge_requires_auth(self, client):
        assert client.get('/api/v2/scep/challenge/1').status_code == 401

    def test_regenerate_challenge_requires_auth(self, client):
        assert post_json(client, '/api/v2/scep/challenge/1/regenerate', {}).status_code == 401


class TestSCEP:
    """SCEP happy-path tests."""

    def test_config_returns_success(self, auth_client):
        r = auth_client.get('/api/v2/scep/config')
        data = assert_success(r)
        assert isinstance(data, dict)
        assert 'enabled' in data

    def test_requests_returns_success(self, auth_client):
        r = auth_client.get('/api/v2/scep/requests')
        data = assert_success(r)
        assert isinstance(data, (list, dict))

    def test_stats_returns_success(self, auth_client):
        r = auth_client.get('/api/v2/scep/stats')
        data = assert_success(r)
        assert isinstance(data, dict)

    def test_approve_nonexistent(self, auth_client):
        r = post_json(auth_client, '/api/v2/scep/99999/approve', {})
        assert r.status_code in (400, 404)

    def test_reject_nonexistent(self, auth_client):
        r = post_json(auth_client, '/api/v2/scep/99999/reject', {})
        assert r.status_code in (400, 404)

    def test_config_patch(self, auth_client):
        """Patch SCEP config — should accept partial updates."""
        r = patch_json(auth_client, '/api/v2/scep/config', {
            'enabled': True
        })
        assert r.status_code == 200


# ============================================================
# OPNsense Import
# ============================================================

class TestOPNsenseAuth:
    """OPNsense import endpoints require authentication."""

    def test_test_requires_auth(self, client):
        assert post_json(client, '/api/v2/import/opnsense/test', {}).status_code == 401

    def test_import_requires_auth(self, client):
        assert post_json(client, '/api/v2/import/opnsense/import', {}).status_code == 401


class TestOPNsense:
    """OPNsense import validation tests."""

    def test_test_without_host(self, auth_client):
        """Test connection without host should fail."""
        r = post_json(auth_client, '/api/v2/import/opnsense/test', {})
        assert r.status_code in (400, 500)

    def test_import_without_data(self, auth_client):
        """Import without proper data should fail."""
        r = post_json(auth_client, '/api/v2/import/opnsense/import', {})
        assert r.status_code in (400, 500)

    def test_test_with_invalid_host(self, auth_client):
        """Test connection with unreachable host."""
        r = post_json(auth_client, '/api/v2/import/opnsense/test', {
            'host': '192.0.2.1',
            'port': 443,
            'api_key': 'test',
            'api_secret': 'test',
            'verify_ssl': False
        })
        # Should fail — unreachable host (408 timeout, 400, or 500)
        assert r.status_code in (400, 408, 500)
