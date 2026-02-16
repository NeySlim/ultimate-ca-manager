"""
Governance API Tests — Policies, Approvals, Reports

Tests the three governance modules:
- Certificate Policies CRUD
- Approval Requests lifecycle
- Report generation (all 5 types)
"""
import pytest
import os
import sys
import json
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


@pytest.fixture(scope='module')
def app():
    """Create app with test configuration"""
    os.environ['SECRET_KEY'] = 'test-secret-key-for-testing'
    os.environ['JWT_SECRET_KEY'] = 'test-jwt-secret-key-for-testing'
    os.environ['UCM_ENV'] = 'test'
    os.environ['HTTP_REDIRECT'] = 'false'
    os.environ['INITIAL_ADMIN_PASSWORD'] = 'changeme123'
    os.environ['CSRF_DISABLED'] = 'true'

    with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as f:
        os.environ['UCM_DATABASE_PATH'] = f.name
        temp_db = f.name

    from app import create_app
    app = create_app('testing')
    app.config['TESTING'] = True
    app.config['WTF_CSRF_ENABLED'] = False

    yield app

    if os.path.exists(temp_db):
        os.unlink(temp_db)


@pytest.fixture(scope='module')
def client(app):
    return app.test_client()


@pytest.fixture(scope='module')
def auth_client(app):
    client = app.test_client()
    r = client.post('/api/v2/auth/login',
        data=json.dumps({'username': 'admin', 'password': 'changeme123'}),
        content_type='application/json')
    assert r.status_code == 200, f'Login failed: {r.data}'
    return client


# ============================================================
# Certificate Policies
# ============================================================
class TestPoliciesAPI:
    """Test /api/v2/policies endpoints"""

    def test_list_policies_unauth(self, client):
        r = client.get('/api/v2/policies')
        assert r.status_code in (401, 403)

    def test_list_policies(self, auth_client):
        r = auth_client.get('/api/v2/policies')
        assert r.status_code == 200
        data = json.loads(r.data)
        assert 'data' in data

    def test_create_policy(self, auth_client):
        policy = {
            'name': 'Test Policy',
            'description': 'A test policy for automated testing',
            'type': 'key_requirements',
            'rules': {
                'min_key_size': 2048,
                'allowed_algorithms': ['RSA', 'ECDSA']
            },
            'enforcement': 'strict',
            'enabled': True
        }
        r = auth_client.post('/api/v2/policies',
            data=json.dumps(policy),
            content_type='application/json')
        assert r.status_code in (200, 201), f'Create failed: {r.data}'
        data = json.loads(r.data)
        assert 'data' in data

    def test_get_policy(self, auth_client):
        # First list to get an ID
        r = auth_client.get('/api/v2/policies')
        data = json.loads(r.data)
        policies = data.get('data', [])
        if len(policies) > 0:
            pid = policies[0].get('id', 1)
            r = auth_client.get(f'/api/v2/policies/{pid}')
            assert r.status_code == 200

    def test_update_policy(self, auth_client):
        r = auth_client.get('/api/v2/policies')
        data = json.loads(r.data)
        policies = data.get('data', [])
        if len(policies) > 0:
            pid = policies[0].get('id', 1)
            r = auth_client.put(f'/api/v2/policies/{pid}',
                data=json.dumps({'name': 'Updated Policy', 'enabled': False}),
                content_type='application/json')
            assert r.status_code == 200

    def test_toggle_policy(self, auth_client):
        r = auth_client.get('/api/v2/policies')
        data = json.loads(r.data)
        policies = data.get('data', [])
        if len(policies) > 0:
            pid = policies[0].get('id', 1)
            r = auth_client.post(f'/api/v2/policies/{pid}/toggle',
                content_type='application/json')
            assert r.status_code in (200, 204)

    def test_delete_policy(self, auth_client):
        # Create one to delete
        policy = {
            'name': 'To Delete',
            'type': 'key_requirements',
            'rules': {},
            'enforcement': 'warn'
        }
        r = auth_client.post('/api/v2/policies',
            data=json.dumps(policy),
            content_type='application/json')
        if r.status_code in (200, 201):
            data = json.loads(r.data)
            pid = data.get('data', {}).get('id')
            if pid:
                r = auth_client.delete(f'/api/v2/policies/{pid}')
                assert r.status_code in (200, 204)


# ============================================================
# Approval Requests
# ============================================================
class TestApprovalsAPI:
    """Test /api/v2/approvals endpoints"""

    def test_list_approvals_unauth(self, client):
        r = client.get('/api/v2/approvals')
        assert r.status_code in (401, 403)

    def test_list_approvals(self, auth_client):
        r = auth_client.get('/api/v2/approvals')
        assert r.status_code == 200
        data = json.loads(r.data)
        assert 'data' in data

    def test_approval_stats(self, auth_client):
        r = auth_client.get('/api/v2/approvals/stats')
        assert r.status_code == 200

    def test_approve_nonexistent(self, auth_client):
        r = auth_client.post('/api/v2/approvals/99999/approve',
            data=json.dumps({'comment': 'test'}),
            content_type='application/json')
        assert r.status_code in (404, 400, 500)

    def test_reject_nonexistent(self, auth_client):
        r = auth_client.post('/api/v2/approvals/99999/reject',
            data=json.dumps({'comment': 'test reason'}),
            content_type='application/json')
        assert r.status_code in (404, 400, 500)


# ============================================================
# Reports
# ============================================================
class TestReportsAPI:
    """Test /api/v2/reports endpoints"""

    def test_list_report_types(self, auth_client):
        r = auth_client.get('/api/v2/reports/types')
        assert r.status_code == 200
        data = json.loads(r.data)
        assert 'data' in data

    def test_generate_certificate_inventory(self, auth_client):
        r = auth_client.post('/api/v2/reports/generate',
            data=json.dumps({'report_type': 'certificate_inventory', 'params': {}}),
            content_type='application/json')
        assert r.status_code == 200
        data = json.loads(r.data)
        report = data.get('data', {})
        assert 'content' in report or 'summary' in report

    def test_generate_expiring_certificates(self, auth_client):
        r = auth_client.post('/api/v2/reports/generate',
            data=json.dumps({'report_type': 'expiring_certificates', 'params': {'days': 30}}),
            content_type='application/json')
        assert r.status_code == 200

    def test_generate_ca_hierarchy(self, auth_client):
        r = auth_client.post('/api/v2/reports/generate',
            data=json.dumps({'report_type': 'ca_hierarchy', 'params': {}}),
            content_type='application/json')
        assert r.status_code == 200

    def test_generate_audit_summary(self, auth_client):
        r = auth_client.post('/api/v2/reports/generate',
            data=json.dumps({'report_type': 'audit_summary', 'params': {'days': 7}}),
            content_type='application/json')
        assert r.status_code == 200

    def test_generate_compliance_status(self, auth_client):
        r = auth_client.post('/api/v2/reports/generate',
            data=json.dumps({'report_type': 'compliance_status', 'params': {}}),
            content_type='application/json')
        assert r.status_code == 200

    def test_generate_invalid_type(self, auth_client):
        r = auth_client.post('/api/v2/reports/generate',
            data=json.dumps({'report_type': 'nonexistent', 'params': {}}),
            content_type='application/json')
        assert r.status_code == 400

    def test_generate_missing_type(self, auth_client):
        r = auth_client.post('/api/v2/reports/generate',
            data=json.dumps({'params': {}}),
            content_type='application/json')
        assert r.status_code == 400

    def test_download_csv(self, auth_client):
        r = auth_client.get('/api/v2/reports/download/certificate_inventory?format=csv')
        assert r.status_code == 200
        assert 'text/csv' in r.content_type or 'application/octet-stream' in r.content_type

    def test_download_json(self, auth_client):
        r = auth_client.get('/api/v2/reports/download/certificate_inventory?format=json')
        assert r.status_code == 200

    def test_download_invalid_type(self, auth_client):
        r = auth_client.get('/api/v2/reports/download/nonexistent')
        assert r.status_code == 400

    def test_report_schedule(self, auth_client):
        r = auth_client.get('/api/v2/reports/schedule')
        assert r.status_code == 200
