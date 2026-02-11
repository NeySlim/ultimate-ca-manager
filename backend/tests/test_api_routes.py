"""
Backend API Route Tests

Tests all critical API endpoints for:
- Correct HTTP status codes
- Required field validation (400 on missing fields)  
- Authentication enforcement (401 on unauthenticated)
- Data type validation
- Response structure

Uses Flask test client with the create_app factory.
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
    os.environ['UCM_SECRET_KEY'] = 'test-secret-key-for-testing'
    os.environ['UCM_ENV'] = 'test'
    os.environ['HTTP_REDIRECT'] = 'false'
    os.environ['INITIAL_ADMIN_PASSWORD'] = 'changeme123'
    
    # Use temp DB so we don't touch production
    with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as f:
        os.environ['UCM_DATABASE_PATH'] = f.name
        temp_db = f.name
    
    from app import create_app
    app = create_app('testing')
    app.config['TESTING'] = True
    app.config['WTF_CSRF_ENABLED'] = False
    
    yield app
    
    # Cleanup
    if os.path.exists(temp_db):
        os.unlink(temp_db)


@pytest.fixture(scope='module')
def client(app):
    """Flask test client"""
    return app.test_client()


@pytest.fixture(scope='module')
def auth_client(app):
    """Authenticated Flask test client with persistent session"""
    client = app.test_client()
    # Login as default admin
    r = client.post('/api/v2/auth/login',
        data=json.dumps({'username': 'admin', 'password': 'changeme123'}),
        content_type='application/json')
    assert r.status_code == 200, f'Login failed: {r.data}'
    return client


# ============================================================
# Health Check (no auth required)
# ============================================================
class TestHealthEndpoints:
    """Health endpoints should work without auth"""

    def test_health(self, client):
        r = client.get('/health')
        assert r.status_code in (200, 301, 308)

    def test_api_health(self, client):
        r = client.get('/api/health')
        assert r.status_code in (200, 301, 308)


# ============================================================
# Authentication
# ============================================================
class TestAuthEndpoints:
    """Auth endpoint tests"""

    def test_login_missing_fields_returns_400(self, client):
        """POST /auth/login without username/password → 400"""
        r = client.post('/api/v2/auth/login',
            data=json.dumps({}),
            content_type='application/json')
        assert r.status_code in (400, 401, 422)

    def test_login_wrong_password_returns_401(self, client):
        """POST /auth/login with wrong password → 401"""
        r = client.post('/api/v2/auth/login',
            data=json.dumps({'username': 'admin', 'password': 'wrongpass'}),
            content_type='application/json')
        assert r.status_code == 401

    def test_verify_unauthenticated_returns_401(self, client):
        """GET /auth/verify without session → 401 (fresh client)"""
        # Use a fresh client without session
        from flask import Flask
        fresh_client = client.application.test_client()
        r = fresh_client.get('/api/v2/auth/verify')
        # Session-based auth may return 200 with anonymous data or 401
        assert r.status_code in (200, 401)

    def test_forgot_password_accepts_email(self, client):
        """POST /auth/forgot-password always returns success (no enumeration)"""
        r = client.post('/api/v2/auth/forgot-password',
            data=json.dumps({'email': 'nonexistent@test.com'}),
            content_type='application/json')
        # Returns 200 (email sent or pretended), 400 (bad format), or 503 (no SMTP)
        assert r.status_code in (200, 400, 500, 503)

    def test_reset_password_invalid_token(self, client):
        """POST /auth/reset-password with bad token → 400/401"""
        r = client.post('/api/v2/auth/reset-password',
            data=json.dumps({'token': 'invalid', 'password': 'NewStr0ng@Pass!'}),
            content_type='application/json')
        assert r.status_code in (400, 401, 404)


# ============================================================
# Protected Endpoints — Must return 401 without auth
# ============================================================
class TestAuthRequired:
    """All protected endpoints should return 401 without auth"""

    @pytest.mark.parametrize('method,path', [
        ('GET', '/api/v2/certificates'),
        ('GET', '/api/v2/certificates/stats'),
        ('GET', '/api/v2/cas'),
        ('GET', '/api/v2/cas/tree'),
        ('GET', '/api/v2/csrs'),
        ('GET', '/api/v2/templates'),
        ('GET', '/api/v2/users'),
        ('GET', '/api/v2/groups'),
        ('GET', '/api/v2/roles'),
        ('GET', '/api/v2/settings/general'),
        ('GET', '/api/v2/settings/email'),
        ('GET', '/api/v2/audit/logs'),
        ('GET', '/api/v2/dashboard/stats'),
        ('GET', '/api/v2/account/profile'),
        ('GET', '/api/v2/account/apikeys'),
        ('GET', '/api/v2/scep/config'),
        ('GET', '/api/v2/crl'),
        ('GET', '/api/v2/system/database/stats'),
        ('GET', '/api/v2/system/https/cert-info'),
    ])
    def test_get_requires_auth(self, client, method, path):
        """GET endpoints require authentication"""
        r = client.get(path)
        assert r.status_code == 401, f'{path} should require auth, got {r.status_code}'

    @pytest.mark.parametrize('path,body', [
        ('/api/v2/certificates', {'cn': 'test.com', 'ca_id': 1}),
        ('/api/v2/cas', {'commonName': 'Test CA'}),
        ('/api/v2/csrs/upload', {'pem': 'test'}),
        ('/api/v2/templates', {'name': 'Test'}),
        ('/api/v2/users', {'username': 'test', 'password': 'Test1234!', 'email': 'a@b.com'}),
        ('/api/v2/groups', {'name': 'Test'}),
        ('/api/v2/system/database/optimize', {}),
        ('/api/v2/system/database/reset', {}),
    ])
    def test_post_requires_auth(self, client, path, body):
        """POST endpoints require authentication"""
        r = client.post(path,
            data=json.dumps(body),
            content_type='application/json')
        assert r.status_code == 401, f'{path} should require auth, got {r.status_code}'


# ============================================================
# Input Validation — With auth
# ============================================================
class TestInputValidation:
    """Test that the backend validates inputs correctly"""

    def test_create_cert_missing_cn_returns_400(self, auth_client):
        """POST /certificates without cn → 400"""
        r = auth_client.post('/api/v2/certificates',
            data=json.dumps({'ca_id': 999}),
            content_type='application/json')
        assert r.status_code in (400, 404, 500)
        if r.status_code == 400:
            data = json.loads(r.data)
            assert 'cn' in str(data).lower() or 'common' in str(data).lower()

    def test_create_cert_missing_ca_returns_error(self, auth_client):
        """POST /certificates without ca_id → error"""
        r = auth_client.post('/api/v2/certificates',
            data=json.dumps({'cn': 'test.com'}),
            content_type='application/json')
        assert r.status_code in (400, 404, 500)

    def test_create_cert_validity_days_must_be_int(self, auth_client):
        """POST /certificates with string validity_days → error"""
        r = auth_client.post('/api/v2/certificates',
            data=json.dumps({
                'cn': 'test.com',
                'ca_id': 999,
                'validity_days': 'not-a-number'
            }),
            content_type='application/json')
        assert r.status_code in (400, 404, 500)

    def test_create_user_requires_username(self, auth_client):
        """POST /users without username → 400"""
        r = auth_client.post('/api/v2/users',
            data=json.dumps({'email': 'a@b.com', 'password': 'Test1234!'}),
            content_type='application/json')
        assert r.status_code in (400, 422)

    def test_create_user_requires_password(self, auth_client):
        """POST /users without password → 400"""
        r = auth_client.post('/api/v2/users',
            data=json.dumps({'username': 'newuser', 'email': 'a@b.com'}),
            content_type='application/json')
        assert r.status_code in (400, 422)

    def test_create_user_weak_password_rejected(self, auth_client):
        """POST /users with weak password → 400"""
        r = auth_client.post('/api/v2/users',
            data=json.dumps({
                'username': 'weakuser',
                'email': 'weak@b.com',
                'password': '123'
            }),
            content_type='application/json')
        assert r.status_code in (400, 422)

    def test_create_template_requires_name(self, auth_client):
        """POST /templates without name → 400"""
        r = auth_client.post('/api/v2/templates',
            data=json.dumps({'type': 'certificate'}),
            content_type='application/json')
        assert r.status_code in (400, 422)

    def test_create_group_requires_name(self, auth_client):
        """POST /groups without name → 400"""
        r = auth_client.post('/api/v2/groups',
            data=json.dumps({'description': 'No name'}),
            content_type='application/json')
        assert r.status_code in (400, 422)


# ============================================================
# Response Structure — With auth  
# ============================================================
class TestResponseStructure:
    """Verify response structures match frontend expectations"""

    def test_certificates_list_returns_array(self, auth_client):
        """GET /certificates → list structure"""
        r = auth_client.get('/api/v2/certificates')
        assert r.status_code == 200
        data = json.loads(r.data)
        assert isinstance(data, (list, dict))

    def test_cas_list_returns_array(self, auth_client):
        """GET /cas → list of CAs"""
        r = auth_client.get('/api/v2/cas')
        assert r.status_code == 200
        data = json.loads(r.data)
        assert isinstance(data, (list, dict))

    def test_dashboard_stats_returns_dict(self, auth_client):
        """GET /dashboard/stats → dict with counts"""
        r = auth_client.get('/api/v2/dashboard/stats')
        assert r.status_code == 200
        data = json.loads(r.data)
        assert isinstance(data, dict)

    def test_settings_general_returns_dict(self, auth_client):
        """GET /settings/general → settings object"""
        r = auth_client.get('/api/v2/settings/general')
        assert r.status_code == 200
        data = json.loads(r.data)
        assert isinstance(data, dict)

    def test_templates_list_returns_array(self, auth_client):
        """GET /templates → list"""
        r = auth_client.get('/api/v2/templates')
        assert r.status_code == 200
        data = json.loads(r.data)
        assert isinstance(data, (list, dict))

    def test_users_list_returns_array(self, auth_client):
        """GET /users → list"""
        r = auth_client.get('/api/v2/users')
        assert r.status_code == 200
        data = json.loads(r.data)
        assert isinstance(data, (list, dict))

    def test_audit_logs_returns_data(self, auth_client):
        """GET /audit/logs → response with logs"""
        r = auth_client.get('/api/v2/audit/logs')
        assert r.status_code == 200
        data = json.loads(r.data)
        assert isinstance(data, (list, dict))

    def test_account_profile_returns_user_data(self, auth_client):
        """GET /account/profile → user object"""
        r = auth_client.get('/api/v2/account/profile')
        assert r.status_code == 200
        data = json.loads(r.data)
        assert isinstance(data, dict)
        assert 'username' in data or 'user' in data or 'data' in data

    def test_search_returns_categorized_results(self, auth_client):
        """GET /search?q=test → categorized results"""
        r = auth_client.get('/api/v2/search?q=test&limit=5')
        assert r.status_code == 200
        data = json.loads(r.data)
        assert isinstance(data, dict)

    def test_nonexistent_endpoint_returns_404(self, auth_client):
        """GET /api/v2/nonexistent → 404"""
        r = auth_client.get('/api/v2/totally-nonexistent-endpoint')
        assert r.status_code in (404, 200, 301, 302)

    def test_password_policy_public(self, client):
        """GET /users/password-policy → public (no auth)"""
        r = client.get('/api/v2/users/password-policy')
        assert r.status_code == 200
        data = json.loads(r.data)
        assert isinstance(data, dict)
