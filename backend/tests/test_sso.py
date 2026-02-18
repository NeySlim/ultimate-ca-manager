"""
SSO Authentication Tests

Tests SSO provider management, auth response contracts, rate limiting,
and role validation. Ensures all auth endpoints return consistent response
structures so the frontend can set permissions correctly.

Uses Flask test client with create_app factory.
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
    """Authenticated admin client"""
    client = app.test_client()
    r = client.post('/api/v2/auth/login',
        data=json.dumps({'username': 'admin', 'password': 'changeme123'}),
        content_type='application/json')
    assert r.status_code == 200, f'Login failed: {r.data}'
    return client


# ============================================================
# Auth Response Contract — all login endpoints must return
# the same fields so the frontend can set permissions
# ============================================================
class TestAuthResponseContract:
    """Verify all auth flows return consistent response structure"""

    REQUIRED_AUTH_FIELDS = {'user', 'csrf_token'}

    def test_password_login_response_structure(self, client):
        """POST /auth/login → response must have user + csrf_token"""
        r = client.post('/api/v2/auth/login',
            data=json.dumps({'username': 'admin', 'password': 'changeme123'}),
            content_type='application/json')
        assert r.status_code == 200
        data = json.loads(r.data)
        resp_data = data.get('data', data)
        assert 'user' in resp_data, 'Password login must return user object'
        assert 'csrf_token' in resp_data, 'Password login must return csrf_token'

    def test_verify_response_has_permissions(self, auth_client):
        """GET /auth/verify → must return permissions and role"""
        r = auth_client.get('/api/v2/auth/verify')
        assert r.status_code == 200
        data = json.loads(r.data)
        resp_data = data.get('data', data)
        assert 'permissions' in resp_data, 'Verify must return permissions'
        assert 'role' in resp_data, 'Verify must return role'
        assert 'csrf_token' in resp_data, 'Verify must return csrf_token'
        assert isinstance(resp_data['permissions'], list), 'Permissions must be a list'

    def test_admin_verify_has_wildcard_permission(self, auth_client):
        """Admin user should have ['*'] permissions"""
        r = auth_client.get('/api/v2/auth/verify')
        data = json.loads(r.data)
        resp_data = data.get('data', data)
        assert '*' in resp_data['permissions'], 'Admin should have wildcard permission'
        assert resp_data['role'] == 'admin'


# ============================================================
# SSO Provider CRUD
# ============================================================
class TestSSOProviderCRUD:
    """Test SSO provider management endpoints"""

    def test_list_providers_requires_auth(self, client):
        """GET /sso/providers → 401 without auth"""
        fresh = client.application.test_client()
        r = fresh.get('/api/v2/sso/providers')
        assert r.status_code == 401

    def test_list_providers(self, auth_client):
        """GET /sso/providers → list"""
        r = auth_client.get('/api/v2/sso/providers')
        assert r.status_code == 200
        data = json.loads(r.data)
        assert isinstance(data.get('data', data), list)

    def test_create_ldap_provider(self, auth_client):
        """POST /sso/providers → create LDAP provider"""
        r = auth_client.post('/api/v2/sso/providers',
            data=json.dumps({
                'name': 'test-ldap',
                'provider_type': 'ldap',
                'display_name': 'Test LDAP',
                'enabled': False,
                'default_role': 'operator',
                'ldap_server': 'ldap.test.com',
                'ldap_port': 389,
                'ldap_bind_dn': 'cn=admin,dc=test',
                'ldap_bind_password': 'secret',
                'ldap_base_dn': 'ou=users,dc=test',
                'ldap_user_filter': '(uid={username})',
                'ldap_username_attr': 'uid',
                'ldap_email_attr': 'mail',
                'ldap_fullname_attr': 'cn',
            }),
            content_type='application/json')
        assert r.status_code in (200, 201), f'Create LDAP failed: {r.data}'
        data = json.loads(r.data)
        provider = data.get('data', data)
        assert provider['name'] == 'test-ldap'
        assert provider['default_role'] == 'operator'

    def test_create_provider_invalid_role_defaults_to_viewer(self, auth_client):
        """POST /sso/providers with invalid default_role → fallback to viewer"""
        r = auth_client.post('/api/v2/sso/providers',
            data=json.dumps({
                'name': 'test-bad-role',
                'provider_type': 'oauth2',
                'default_role': 'superadmin',
                'oauth2_client_id': 'test-client',
                'oauth2_client_secret': 'test-secret',
                'oauth2_auth_url': 'https://auth.test.com/authorize',
                'oauth2_token_url': 'https://auth.test.com/token',
                'oauth2_userinfo_url': 'https://auth.test.com/userinfo',
            }),
            content_type='application/json')
        assert r.status_code in (200, 201)
        data = json.loads(r.data)
        provider = data.get('data', data)
        assert provider['default_role'] == 'viewer', \
            f'Invalid role should fallback to viewer, got {provider["default_role"]}'

    def test_update_provider_invalid_role(self, auth_client):
        """PUT /sso/providers/<id> with invalid role → fallback to viewer"""
        # First, get providers to find the test one
        r = auth_client.get('/api/v2/sso/providers')
        providers = json.loads(r.data).get('data', [])
        test_provider = next((p for p in providers if p['name'] == 'test-ldap'), None)
        if not test_provider:
            pytest.skip('No test provider found')

        r = auth_client.put(f'/api/v2/sso/providers/{test_provider["id"]}',
            data=json.dumps({'default_role': 'root'}),
            content_type='application/json')
        assert r.status_code == 200
        data = json.loads(r.data)
        provider = data.get('data', data)
        assert provider['default_role'] == 'viewer'

    def test_available_providers_public(self, client):
        """GET /sso/available → public endpoint, no auth"""
        r = client.get('/api/v2/sso/available')
        assert r.status_code == 200
        data = json.loads(r.data)
        assert isinstance(data.get('data', data), list)


# ============================================================
# LDAP Login — Rate Limiting & Input Validation
# ============================================================
class TestLDAPLogin:
    """Test LDAP login endpoint security"""

    def test_ldap_login_missing_credentials(self, client):
        """POST /sso/ldap/login without credentials → 400"""
        r = client.post('/api/v2/sso/ldap/login',
            data=json.dumps({}),
            content_type='application/json')
        assert r.status_code == 400

    def test_ldap_login_missing_password(self, client):
        """POST /sso/ldap/login without password → 400"""
        r = client.post('/api/v2/sso/ldap/login',
            data=json.dumps({'username': 'alice'}),
            content_type='application/json')
        assert r.status_code == 400

    def test_ldap_login_no_provider(self, client):
        """POST /sso/ldap/login with no enabled provider → 400"""
        r = client.post('/api/v2/sso/ldap/login',
            data=json.dumps({'username': 'alice', 'password': 'test123'}),
            content_type='application/json')
        # No enabled LDAP provider in test DB
        assert r.status_code == 400

    def test_ldap_login_error_is_generic(self, client):
        """LDAP auth errors should not leak user enumeration info"""
        r = client.post('/api/v2/sso/ldap/login',
            data=json.dumps({'username': 'alice', 'password': 'wrong'}),
            content_type='application/json')
        if r.status_code == 401:
            data = json.loads(r.data)
            msg = data.get('message', '').lower()
            assert 'not found' not in msg, 'Error should not reveal user existence'
            assert 'invalid password' not in msg, 'Error should not distinguish user vs password'


# ============================================================
# Role Resolution — _resolve_role helper
# ============================================================
class TestRoleResolution:
    """Test the _resolve_role helper function directly"""

    def test_resolve_role_with_valid_mapping(self, app):
        """Role mapping matches → mapped role"""
        with app.app_context():
            from api.v2.sso import _resolve_role
            from unittest.mock import MagicMock

            provider = MagicMock()
            provider.role_mapping = json.dumps({'admins': 'admin', 'ops': 'operator'})
            provider.default_role = 'viewer'

            role = _resolve_role(provider, {'groups': ['admins']})
            assert role == 'admin'

    def test_resolve_role_no_match_uses_default(self, app):
        """No role mapping match → default_role"""
        with app.app_context():
            from api.v2.sso import _resolve_role
            from unittest.mock import MagicMock

            provider = MagicMock()
            provider.role_mapping = json.dumps({'admins': 'admin'})
            provider.default_role = 'operator'

            role = _resolve_role(provider, {'groups': ['users']})
            assert role == 'operator'

    def test_resolve_role_no_mapping_uses_default(self, app):
        """No role_mapping configured → default_role"""
        with app.app_context():
            from api.v2.sso import _resolve_role
            from unittest.mock import MagicMock

            provider = MagicMock()
            provider.role_mapping = None
            provider.default_role = 'admin'

            role = _resolve_role(provider, {'groups': []})
            assert role == 'admin'

    def test_resolve_role_invalid_default_falls_to_viewer(self, app):
        """Invalid default_role → viewer"""
        with app.app_context():
            from api.v2.sso import _resolve_role
            from unittest.mock import MagicMock

            provider = MagicMock()
            provider.role_mapping = None
            provider.default_role = 'superadmin'

            role = _resolve_role(provider, {})
            assert role == 'viewer'

    def test_resolve_role_invalid_mapped_role_falls_to_viewer(self, app):
        """Mapped role value is invalid → viewer"""
        with app.app_context():
            from api.v2.sso import _resolve_role
            from unittest.mock import MagicMock

            provider = MagicMock()
            provider.role_mapping = json.dumps({'admins': 'root'})
            provider.default_role = 'operator'

            role = _resolve_role(provider, {'groups': ['admins']})
            assert role == 'viewer'

    def test_resolve_role_groups_as_string(self, app):
        """External roles as string (not list) → still works"""
        with app.app_context():
            from api.v2.sso import _resolve_role
            from unittest.mock import MagicMock

            provider = MagicMock()
            provider.role_mapping = json.dumps({'admins': 'admin'})
            provider.default_role = 'viewer'

            role = _resolve_role(provider, {'groups': 'admins'})
            assert role == 'admin'


# ============================================================
# LDAP Rate Limiting — Lockout helpers
# ============================================================
class TestLDAPRateLimiting:
    """Test LDAP brute-force protection"""

    def test_lockout_check_nonexistent_user(self, app):
        """Non-existent user should not be locked"""
        with app.app_context():
            from api.v2.sso import _check_ldap_lockout
            assert _check_ldap_lockout('nonexistent_user_xyz') is False

    def test_record_failed_attempts_and_lockout(self, app):
        """After 5 failed attempts, user should be locked"""
        with app.app_context():
            from api.v2.sso import (
                _record_ldap_failed_attempt,
                _check_ldap_lockout,
                _clear_ldap_failed_attempts,
                LDAP_MAX_FAILED_ATTEMPTS,
            )
            from models import db, User

            # Use the admin user for testing
            user = User.query.filter_by(username='admin').first()
            assert user is not None

            # Clear any existing lockout
            user.failed_logins = 0
            user.locked_until = None
            db.session.commit()

            # Record failures up to threshold
            for i in range(LDAP_MAX_FAILED_ATTEMPTS):
                assert _check_ldap_lockout('admin') is False
                _record_ldap_failed_attempt('admin')

            # Should now be locked
            assert _check_ldap_lockout('admin') is True

            # Clear and verify unlocked
            _clear_ldap_failed_attempts('admin')
            assert _check_ldap_lockout('admin') is False

            # Verify user state is clean
            db.session.refresh(user)
            assert user.failed_logins == 0
            assert user.locked_until is None


# ============================================================
# SSO Helper — _parse_json_field
# ============================================================
class TestParseJsonField:
    """Test JSON field parsing (handles string, double-encoded, dict)"""

    def test_parse_none(self, app):
        with app.app_context():
            from api.v2.sso import _parse_json_field
            assert _parse_json_field(None) == {}

    def test_parse_empty_string(self, app):
        with app.app_context():
            from api.v2.sso import _parse_json_field
            assert _parse_json_field('') == {}

    def test_parse_dict(self, app):
        with app.app_context():
            from api.v2.sso import _parse_json_field
            assert _parse_json_field({'a': 1}) == {'a': 1}

    def test_parse_json_string(self, app):
        with app.app_context():
            from api.v2.sso import _parse_json_field
            assert _parse_json_field('{"a": 1}') == {'a': 1}

    def test_parse_double_encoded(self, app):
        with app.app_context():
            from api.v2.sso import _parse_json_field
            assert _parse_json_field('"{\\"a\\": 1}"') == {'a': 1}

    def test_parse_invalid_json(self, app):
        with app.app_context():
            from api.v2.sso import _parse_json_field
            assert _parse_json_field('not json') == {}

    def test_parse_json_array_returns_empty(self, app):
        with app.app_context():
            from api.v2.sso import _parse_json_field
            assert _parse_json_field('[1, 2, 3]') == {}
