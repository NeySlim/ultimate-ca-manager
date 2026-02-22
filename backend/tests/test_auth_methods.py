"""
Tests for auth_methods API (/api/v2/auth/methods, /api/v2/auth/login/*)
and legacy auth endpoints (/api/v2/auth/login, /api/v2/auth/logout, etc.)

Uses shared fixtures from conftest.py:
  - app, client (unauthenticated), auth_client (admin session)
"""
import pytest
import json


def get_json(response):
    return json.loads(response.data)


def _post(client, url, data=None):
    """Helper: POST JSON to url."""
    return client.post(
        url,
        data=json.dumps(data) if data else '{}',
        content_type='application/json',
    )


# ============================================================
# GET/POST /api/v2/auth/methods — detect available auth methods
# ============================================================
class TestDetectAuthMethods:
    """Tests for /api/v2/auth/methods"""

    def test_get_methods_returns_200(self, client):
        r = client.get('/api/v2/auth/methods')
        assert r.status_code == 200

    def test_get_methods_response_structure(self, client):
        r = client.get('/api/v2/auth/methods')
        body = get_json(r)
        data = body.get('data', body)
        assert 'password' in data
        assert 'mtls' in data
        assert 'webauthn' in data

    def test_get_methods_password_always_available(self, client):
        r = client.get('/api/v2/auth/methods')
        data = get_json(r).get('data', {})
        assert data['password'] is True

    def test_get_methods_mtls_status_present(self, client):
        """Without client cert, mtls_status should be 'not_present'."""
        r = client.get('/api/v2/auth/methods')
        data = get_json(r).get('data', {})
        assert data['mtls_status'] == 'not_present'

    def test_post_methods_with_valid_username(self, client):
        """POST with known username returns webauthn_credentials count."""
        r = _post(client, '/api/v2/auth/methods', {'username': 'admin'})
        assert r.status_code == 200
        data = get_json(r).get('data', {})
        assert 'webauthn_credentials' in data
        assert isinstance(data['webauthn_credentials'], int)

    def test_post_methods_with_unknown_username(self, client):
        """POST with unknown username still returns 200 (no user enumeration leak)."""
        r = _post(client, '/api/v2/auth/methods', {'username': 'nonexistent_user_xyz'})
        assert r.status_code == 200
        data = get_json(r).get('data', {})
        assert data['webauthn_credentials'] == 0

    def test_post_methods_empty_body(self, client):
        """POST with empty body returns global methods (no crash)."""
        r = _post(client, '/api/v2/auth/methods', {})
        assert r.status_code == 200


# ============================================================
# POST /api/v2/auth/login/password — password login
# ============================================================
class TestPasswordLogin:
    """Tests for /api/v2/auth/login/password"""

    def test_login_success(self, app):
        c = app.test_client()
        r = _post(c, '/api/v2/auth/login/password', {
            'username': 'admin',
            'password': 'changeme123',
        })
        assert r.status_code == 200
        data = get_json(r).get('data', {})
        assert 'user' in data
        assert data['user']['username'] == 'admin'

    def test_login_returns_permissions(self, app):
        c = app.test_client()
        r = _post(c, '/api/v2/auth/login/password', {
            'username': 'admin',
            'password': 'changeme123',
        })
        data = get_json(r).get('data', {})
        assert 'permissions' in data
        assert isinstance(data['permissions'], list)
        assert len(data['permissions']) > 0

    def test_login_returns_role(self, app):
        c = app.test_client()
        r = _post(c, '/api/v2/auth/login/password', {
            'username': 'admin',
            'password': 'changeme123',
        })
        data = get_json(r).get('data', {})
        assert data['role'] == 'admin'

    def test_login_returns_csrf_token(self, app):
        c = app.test_client()
        r = _post(c, '/api/v2/auth/login/password', {
            'username': 'admin',
            'password': 'changeme123',
        })
        data = get_json(r).get('data', {})
        assert 'csrf_token' in data

    def test_login_returns_auth_method(self, app):
        c = app.test_client()
        r = _post(c, '/api/v2/auth/login/password', {
            'username': 'admin',
            'password': 'changeme123',
        })
        data = get_json(r).get('data', {})
        assert data.get('auth_method') == 'password'

    def test_login_missing_username(self, client):
        r = _post(client, '/api/v2/auth/login/password', {'password': 'changeme123'})
        assert r.status_code == 400

    def test_login_missing_password(self, client):
        r = _post(client, '/api/v2/auth/login/password', {'username': 'admin'})
        assert r.status_code == 400

    def test_login_empty_body(self, client):
        r = _post(client, '/api/v2/auth/login/password', {})
        assert r.status_code == 400

    def test_login_wrong_password(self, client):
        r = _post(client, '/api/v2/auth/login/password', {
            'username': 'admin',
            'password': 'wrongpassword',
        })
        assert r.status_code == 401

    def test_login_nonexistent_user(self, client):
        r = _post(client, '/api/v2/auth/login/password', {
            'username': 'no_such_user',
            'password': 'anything',
        })
        assert r.status_code == 401

    def test_login_error_message_is_generic(self, client):
        """Should not reveal whether username or password is wrong."""
        r = _post(client, '/api/v2/auth/login/password', {
            'username': 'no_such_user',
            'password': 'anything',
        })
        body = get_json(r)
        msg = body.get('message', '').lower()
        assert 'not found' not in msg
        assert 'invalid credentials' in msg or 'invalid' in msg


# ============================================================
# POST /api/v2/auth/login/2fa — TOTP 2FA verification
# ============================================================
class TestLogin2FA:
    """Tests for /api/v2/auth/login/2fa"""

    def test_2fa_without_pending_session(self, app):
        """2FA endpoint without prior password login returns 401."""
        c = app.test_client()
        r = _post(c, '/api/v2/auth/login/2fa', {'code': '123456'})
        assert r.status_code == 401

    def test_2fa_missing_code(self, app):
        """2FA endpoint with empty code returns 400 or 401."""
        c = app.test_client()
        r = _post(c, '/api/v2/auth/login/2fa', {})
        assert r.status_code in (400, 401)

    def test_2fa_no_pending_message(self, app):
        c = app.test_client()
        r = _post(c, '/api/v2/auth/login/2fa', {'code': '000000'})
        body = get_json(r)
        assert 'pending' in body.get('message', '').lower() or r.status_code == 401


# ============================================================
# POST /api/v2/auth/login/webauthn/start — start WebAuthn
# ============================================================
class TestWebAuthnStart:
    """Tests for /api/v2/auth/login/webauthn/start"""

    def test_start_missing_username(self, client):
        r = _post(client, '/api/v2/auth/login/webauthn/start', {})
        assert r.status_code == 400

    def test_start_nonexistent_user(self, client):
        r = _post(client, '/api/v2/auth/login/webauthn/start', {
            'username': 'ghost_user',
        })
        assert r.status_code in (401, 404)

    def test_start_user_without_credentials(self, client):
        """Admin has no WebAuthn credentials registered → 404."""
        r = _post(client, '/api/v2/auth/login/webauthn/start', {
            'username': 'admin',
        })
        assert r.status_code in (404, 500)


# ============================================================
# POST /api/v2/auth/login/webauthn/verify — verify WebAuthn
# ============================================================
class TestWebAuthnVerify:
    """Tests for /api/v2/auth/login/webauthn/verify"""

    def test_verify_missing_fields(self, client):
        r = _post(client, '/api/v2/auth/login/webauthn/verify', {})
        assert r.status_code == 400

    def test_verify_missing_response(self, client):
        r = _post(client, '/api/v2/auth/login/webauthn/verify', {
            'username': 'admin',
        })
        assert r.status_code == 400

    def test_verify_nonexistent_user(self, client):
        r = _post(client, '/api/v2/auth/login/webauthn/verify', {
            'username': 'ghost_user',
            'response': {'id': 'fake'},
        })
        assert r.status_code == 401


# ============================================================
# Legacy: POST /api/v2/auth/login — password login (auth.py)
# ============================================================
class TestLegacyLogin:
    """Tests for /api/v2/auth/login (legacy endpoint in auth.py)"""

    def test_legacy_login_success(self, app):
        c = app.test_client()
        r = _post(c, '/api/v2/auth/login', {
            'username': 'admin',
            'password': 'changeme123',
        })
        assert r.status_code == 200
        data = get_json(r).get('data', {})
        assert 'user' in data
        assert 'csrf_token' in data

    def test_legacy_login_missing_fields(self, client):
        r = _post(client, '/api/v2/auth/login', {})
        assert r.status_code in (400, 401, 422)

    def test_legacy_login_wrong_password(self, client):
        r = _post(client, '/api/v2/auth/login', {
            'username': 'admin',
            'password': 'wrong',
        })
        assert r.status_code == 401


# ============================================================
# POST /api/v2/auth/logout — logout
# ============================================================
class TestLogout:
    """Tests for /api/v2/auth/logout"""

    def test_logout_authenticated(self, app):
        """Authenticated user can logout."""
        c = app.test_client()
        _post(c, '/api/v2/auth/login', {
            'username': 'admin',
            'password': 'changeme123',
        })
        r = c.post('/api/v2/auth/logout')
        assert r.status_code == 200

    def test_logout_unauthenticated(self, app):
        """Unauthenticated logout attempt returns 401 (legacy requires auth)."""
        c = app.test_client()
        r = c.post('/api/v2/auth/logout')
        # Legacy auth.py logout requires @require_auth; auth_methods logout does not
        assert r.status_code in (200, 401)


# ============================================================
# GET /api/v2/auth/verify — session verification
# ============================================================
class TestVerify:
    """Tests for /api/v2/auth/verify"""

    def test_verify_unauthenticated(self, app):
        """Unauthenticated verify returns 200 with authenticated=False."""
        c = app.test_client()
        r = c.get('/api/v2/auth/verify')
        assert r.status_code in (200, 401)
        if r.status_code == 200:
            data = get_json(r).get('data', {})
            assert data.get('authenticated') is False

    def test_verify_authenticated(self, app):
        """Authenticated verify returns user info."""
        c = app.test_client()
        _post(c, '/api/v2/auth/login', {
            'username': 'admin',
            'password': 'changeme123',
        })
        r = c.get('/api/v2/auth/verify')
        assert r.status_code == 200
        data = get_json(r).get('data', {})
        assert data.get('authenticated') is True
        assert 'user' in data
        assert 'permissions' in data

    def test_verify_after_logout(self, app):
        """After logout, verify should show unauthenticated."""
        c = app.test_client()
        _post(c, '/api/v2/auth/login', {
            'username': 'admin',
            'password': 'changeme123',
        })
        c.post('/api/v2/auth/logout')
        r = c.get('/api/v2/auth/verify')
        if r.status_code == 200:
            data = get_json(r).get('data', {})
            assert data.get('authenticated') is False


# ============================================================
# POST /api/v2/auth/forgot-password — request password reset
# ============================================================
class TestForgotPassword:
    """Tests for /api/v2/auth/forgot-password"""

    def test_forgot_password_missing_email(self, client):
        r = _post(client, '/api/v2/auth/forgot-password', {})
        assert r.status_code in (400, 503)

    def test_forgot_password_nonexistent_email(self, client):
        """Should return success regardless to prevent enumeration."""
        r = _post(client, '/api/v2/auth/forgot-password', {
            'email': 'nobody@example.com',
        })
        # 200 (success pretended) or 503 (email not configured)
        assert r.status_code in (200, 503)

    def test_forgot_password_no_enumeration(self, client):
        """Response for valid vs invalid email should be identical status."""
        r1 = _post(client, '/api/v2/auth/forgot-password', {
            'email': 'nobody@example.com',
        })
        r2 = _post(client, '/api/v2/auth/forgot-password', {
            'email': 'admin@example.com',
        })
        assert r1.status_code == r2.status_code


# ============================================================
# POST /api/v2/auth/reset-password — reset with token
# ============================================================
class TestResetPassword:
    """Tests for /api/v2/auth/reset-password"""

    def test_reset_missing_token(self, client):
        r = _post(client, '/api/v2/auth/reset-password', {
            'password': 'NewPassword123!',
        })
        assert r.status_code == 400

    def test_reset_invalid_token(self, client):
        r = _post(client, '/api/v2/auth/reset-password', {
            'token': 'invalid-token-abc',
            'password': 'NewPassword123!',
        })
        assert r.status_code == 400

    def test_reset_short_password(self, client):
        r = _post(client, '/api/v2/auth/reset-password', {
            'token': 'some-token',
            'password': 'short',
        })
        assert r.status_code == 400


# ============================================================
# GET /api/v2/auth/email-configured — check email config
# ============================================================
class TestEmailConfigured:
    """Tests for /api/v2/auth/email-configured"""

    def test_email_configured_returns_200(self, client):
        r = client.get('/api/v2/auth/email-configured')
        assert r.status_code == 200

    def test_email_configured_response_structure(self, client):
        r = client.get('/api/v2/auth/email-configured')
        data = get_json(r).get('data', {})
        assert 'configured' in data
        assert isinstance(data['configured'], bool)
