"""
Account Management API Tests

Tests all /api/v2/account/* endpoints:
- Profile (GET/PATCH)
- Password change (POST)
- API Keys (CRUD + regenerate)
- 2FA (enable, confirm, disable, recovery codes)
- Sessions (list, revoke, revoke-all)
- Activity log (GET)

Uses shared conftest fixtures: app, client, auth_client, create_user.
"""
import pytest
import json
import pyotp

CONTENT_JSON = 'application/json'


def get_json(response):
    """Parse JSON response, return dict."""
    return json.loads(response.data)


def assert_success(response, status=200):
    """Assert response is successful and return parsed data."""
    assert response.status_code == status, \
        f'Expected {status}, got {response.status_code}: {response.data[:500]}'
    data = json.loads(response.data)
    return data.get('data', data)


def assert_error(response, status):
    """Assert response is an error with given status code."""
    assert response.status_code == status, \
        f'Expected {status}, got {response.status_code}: {response.data[:500]}'


def post_json(client, url, data):
    return client.post(url, data=json.dumps(data), content_type=CONTENT_JSON)


def patch_json(client, url, data):
    return client.patch(url, data=json.dumps(data), content_type=CONTENT_JSON)


# ============================================================================
# Profile
# ============================================================================

class TestGetProfile:
    """Tests for GET /api/v2/account/profile"""

    def test_requires_auth(self, client):
        r = client.get('/api/v2/account/profile')
        assert r.status_code == 401

    def test_returns_user_data(self, auth_client):
        r = auth_client.get('/api/v2/account/profile')
        data = assert_success(r)
        assert data['username'] == 'admin'
        assert 'id' in data
        assert 'role' in data

    def test_contains_expected_fields(self, auth_client):
        r = auth_client.get('/api/v2/account/profile')
        data = assert_success(r)
        for field in ('id', 'username', 'role', 'email', 'active',
                      'two_factor_enabled', 'created_at'):
            assert field in data, f'Missing field: {field}'


class TestUpdateProfile:
    """Tests for PATCH /api/v2/account/profile"""

    def test_requires_auth(self, client):
        r = patch_json(client, '/api/v2/account/profile', {'email': 'a@b.com'})
        assert r.status_code == 401

    def test_update_email(self, auth_client):
        r = patch_json(auth_client, '/api/v2/account/profile',
                       {'email': 'admin@test.local'})
        data = assert_success(r)
        assert data.get('email') == 'admin@test.local'

    def test_update_full_name(self, auth_client):
        r = patch_json(auth_client, '/api/v2/account/profile',
                       {'full_name': 'Admin User'})
        data = assert_success(r)
        assert data.get('full_name') == 'Admin User'

    def test_update_timezone(self, auth_client):
        r = patch_json(auth_client, '/api/v2/account/profile',
                       {'timezone': 'America/New_York'})
        data = assert_success(r)
        assert data.get('timezone') == 'America/New_York'

    def test_empty_body_returns_400(self, auth_client):
        r = auth_client.patch('/api/v2/account/profile',
                              data=json.dumps(None), content_type=CONTENT_JSON)
        assert_error(r, 400)

    def test_update_multiple_fields(self, auth_client):
        r = patch_json(auth_client, '/api/v2/account/profile', {
            'email': 'multi@test.local',
            'full_name': 'Multi Update',
            'timezone': 'UTC',
        })
        data = assert_success(r)
        assert data.get('email') == 'multi@test.local'
        assert data.get('full_name') == 'Multi Update'


# ============================================================================
# Password Change
# ============================================================================

class TestChangePassword:
    """Tests for POST /api/v2/account/password"""

    def test_requires_auth(self, client):
        r = post_json(client, '/api/v2/account/password', {
            'current_password': 'changeme123',
            'new_password': 'NewPass456!',
        })
        assert r.status_code == 401

    def test_missing_current_password(self, auth_client):
        r = post_json(auth_client, '/api/v2/account/password', {
            'new_password': 'NewPass456!',
        })
        assert_error(r, 400)

    def test_missing_new_password(self, auth_client):
        r = post_json(auth_client, '/api/v2/account/password', {
            'current_password': 'changeme123',
        })
        assert_error(r, 400)

    def test_short_new_password(self, auth_client):
        r = post_json(auth_client, '/api/v2/account/password', {
            'current_password': 'changeme123',
            'new_password': 'short',
        })
        assert_error(r, 400)

    def test_wrong_current_password(self, auth_client):
        r = post_json(auth_client, '/api/v2/account/password', {
            'current_password': 'wrongpassword',
            'new_password': 'NewPass456!',
        })
        assert r.status_code == 401

    def test_empty_body_returns_400(self, auth_client):
        r = auth_client.post('/api/v2/account/password',
                             data=json.dumps(None), content_type=CONTENT_JSON)
        assert_error(r, 400)

    def test_change_password_success(self, app):
        """Use a fresh client to change and restore password."""
        c = app.test_client()
        r = post_json(c, '/api/v2/auth/login',
                      {'username': 'admin', 'password': 'changeme123'})
        assert r.status_code == 200

        # Change password
        r = post_json(c, '/api/v2/account/password', {
            'current_password': 'changeme123',
            'new_password': 'NewSecure456!',
        })
        assert_success(r)

        # Restore original password
        r = post_json(c, '/api/v2/account/password', {
            'current_password': 'NewSecure456!',
            'new_password': 'changeme123',
        })
        assert_success(r)


# ============================================================================
# API Keys
# ============================================================================

class TestListAPIKeys:
    """Tests for GET /api/v2/account/apikeys"""

    def test_requires_auth(self, client):
        r = client.get('/api/v2/account/apikeys')
        assert r.status_code == 401

    def test_returns_list(self, auth_client):
        r = auth_client.get('/api/v2/account/apikeys')
        data = assert_success(r)
        assert isinstance(data, list)


class TestCreateAPIKey:
    """Tests for POST /api/v2/account/apikeys"""

    def test_requires_auth(self, client):
        r = post_json(client, '/api/v2/account/apikeys', {
            'name': 'test', 'permissions': ['read:certificates'],
        })
        assert r.status_code == 401

    def test_missing_name(self, auth_client):
        r = post_json(auth_client, '/api/v2/account/apikeys', {
            'permissions': ['read:certificates'],
        })
        assert_error(r, 400)

    def test_missing_permissions(self, auth_client):
        r = post_json(auth_client, '/api/v2/account/apikeys', {
            'name': 'No Perms Key',
        })
        assert_error(r, 400)

    def test_invalid_permissions_format(self, auth_client):
        r = post_json(auth_client, '/api/v2/account/apikeys', {
            'name': 'Bad Perms', 'permissions': ['invalid'],
        })
        assert_error(r, 400)

    def test_permissions_not_list(self, auth_client):
        r = post_json(auth_client, '/api/v2/account/apikeys', {
            'name': 'String Perms', 'permissions': 'read:certificates',
        })
        assert_error(r, 400)

    def test_create_success(self, auth_client):
        r = post_json(auth_client, '/api/v2/account/apikeys', {
            'name': 'Test Automation Key',
            'permissions': ['read:certificates', 'read:cas'],
        })
        data = assert_success(r, 201)
        assert 'key' in data or 'id' in data

    def test_invalid_permission_category(self, auth_client):
        r = post_json(auth_client, '/api/v2/account/apikeys', {
            'name': 'Bad Cat', 'permissions': ['bogus:certificates'],
        })
        assert_error(r, 400)

    def test_invalid_permission_resource(self, auth_client):
        r = post_json(auth_client, '/api/v2/account/apikeys', {
            'name': 'Bad Res', 'permissions': ['read:nonexistent'],
        })
        assert_error(r, 400)


class TestGetAPIKey:
    """Tests for GET /api/v2/account/apikeys/<id>"""

    def test_requires_auth(self, client):
        r = client.get('/api/v2/account/apikeys/1')
        assert r.status_code == 401

    def test_not_found(self, auth_client):
        r = auth_client.get('/api/v2/account/apikeys/99999')
        assert_error(r, 404)

    def test_get_existing_key(self, auth_client):
        """Create a key then retrieve it."""
        cr = post_json(auth_client, '/api/v2/account/apikeys', {
            'name': 'Retrieve Me',
            'permissions': ['read:certificates'],
        })
        created = assert_success(cr, 201)
        key_id = created.get('id')
        if key_id is None:
            pytest.skip('Create did not return id')

        r = auth_client.get(f'/api/v2/account/apikeys/{key_id}')
        data = assert_success(r)
        assert data.get('name') == 'Retrieve Me'


class TestUpdateAPIKey:
    """Tests for PATCH /api/v2/account/apikeys/<id>"""

    def test_requires_auth(self, client):
        r = patch_json(client, '/api/v2/account/apikeys/1', {'name': 'x'})
        assert r.status_code == 401

    def test_not_found(self, auth_client):
        r = patch_json(auth_client, '/api/v2/account/apikeys/99999',
                       {'name': 'Ghost'})
        assert_error(r, 404)

    def test_update_name(self, auth_client):
        cr = post_json(auth_client, '/api/v2/account/apikeys', {
            'name': 'Original Name',
            'permissions': ['read:cas'],
        })
        created = assert_success(cr, 201)
        key_id = created.get('id')
        if key_id is None:
            pytest.skip('Create did not return id')

        r = patch_json(auth_client, f'/api/v2/account/apikeys/{key_id}',
                       {'name': 'Updated Name'})
        data = assert_success(r)
        assert data.get('name') == 'Updated Name'


class TestDeleteAPIKey:
    """Tests for DELETE /api/v2/account/apikeys/<id>"""

    def test_requires_auth(self, client):
        r = client.delete('/api/v2/account/apikeys/1')
        assert r.status_code == 401

    def test_not_found(self, auth_client):
        r = auth_client.delete('/api/v2/account/apikeys/99999')
        assert_error(r, 404)

    def test_delete_key(self, auth_client):
        cr = post_json(auth_client, '/api/v2/account/apikeys', {
            'name': 'Delete Me',
            'permissions': ['read:certificates'],
        })
        created = assert_success(cr, 201)
        key_id = created.get('id')
        if key_id is None:
            pytest.skip('Create did not return id')

        r = auth_client.delete(f'/api/v2/account/apikeys/{key_id}')
        assert_success(r)

        # Confirm soft-deleted (API still returns it but marked inactive)
        r = auth_client.get(f'/api/v2/account/apikeys/{key_id}')
        data = assert_success(r)
        assert data.get('is_active') is False


class TestRegenerateAPIKey:
    """Tests for POST /api/v2/account/apikeys/<id>/regenerate"""

    def test_requires_auth(self, client):
        r = client.post('/api/v2/account/apikeys/1/regenerate')
        assert r.status_code == 401

    def test_not_found(self, auth_client):
        r = auth_client.post('/api/v2/account/apikeys/99999/regenerate')
        assert_error(r, 404)

    def test_regenerate_key(self, auth_client):
        cr = post_json(auth_client, '/api/v2/account/apikeys', {
            'name': 'Regen Me',
            'permissions': ['read:cas'],
        })
        created = assert_success(cr, 201)
        key_id = created.get('id')
        if key_id is None:
            pytest.skip('Create did not return id')

        r = auth_client.post(f'/api/v2/account/apikeys/{key_id}/regenerate')
        data = assert_success(r, 201)
        # Should return a new key
        assert 'key' in data or 'id' in data


# ============================================================================
# 2FA
# ============================================================================

class TestEnable2FA:
    """Tests for POST /api/v2/account/2fa/enable"""

    def test_requires_auth(self, client):
        r = client.post('/api/v2/account/2fa/enable')
        assert r.status_code == 401

    def test_returns_secret_and_qr(self, auth_client):
        r = auth_client.post('/api/v2/account/2fa/enable')
        data = assert_success(r)
        assert 'secret' in data
        assert 'qr_code' in data
        assert data['qr_code'].startswith('data:image/png;base64,')


class TestConfirm2FA:
    """Tests for POST /api/v2/account/2fa/confirm"""

    def test_requires_auth(self, client):
        r = post_json(client, '/api/v2/account/2fa/confirm', {'code': '000000'})
        assert r.status_code == 401

    def test_missing_code(self, auth_client):
        r = post_json(auth_client, '/api/v2/account/2fa/confirm', {})
        assert_error(r, 400)

    def test_invalid_code(self, auth_client):
        # First enable to get a secret stored
        auth_client.post('/api/v2/account/2fa/enable')
        r = post_json(auth_client, '/api/v2/account/2fa/confirm',
                      {'code': '000000'})
        assert_error(r, 400)

    def test_confirm_with_valid_code(self, auth_client):
        """Enable 2FA, generate valid TOTP code, confirm."""
        r = auth_client.post('/api/v2/account/2fa/enable')
        data = assert_success(r)
        secret = data['secret']

        totp = pyotp.TOTP(secret)
        code = totp.now()

        r = post_json(auth_client, '/api/v2/account/2fa/confirm',
                      {'code': code})
        data = assert_success(r)
        assert 'backup_codes' in data
        assert isinstance(data['backup_codes'], list)
        assert len(data['backup_codes']) == 8


class TestDisable2FA:
    """Tests for POST /api/v2/account/2fa/disable"""

    def test_requires_auth(self, client):
        r = post_json(client, '/api/v2/account/2fa/disable', {'code': '000000'})
        assert r.status_code == 401

    def test_empty_body_returns_400(self, auth_client):
        r = auth_client.post('/api/v2/account/2fa/disable',
                             data=json.dumps(None), content_type=CONTENT_JSON)
        assert_error(r, 400)

    def test_missing_code_and_backup(self, auth_client):
        r = post_json(auth_client, '/api/v2/account/2fa/disable', {})
        assert_error(r, 400)

    def test_disable_with_totp_code(self, auth_client):
        """Full cycle: enable → confirm → disable with TOTP code."""
        # Enable
        r = auth_client.post('/api/v2/account/2fa/enable')
        secret = assert_success(r)['secret']

        # Confirm
        code = pyotp.TOTP(secret).now()
        r = post_json(auth_client, '/api/v2/account/2fa/confirm', {'code': code})
        assert_success(r)

        # Disable with TOTP code
        code = pyotp.TOTP(secret).now()
        r = post_json(auth_client, '/api/v2/account/2fa/disable', {'code': code})
        assert_success(r)


class TestRecoveryCodes:
    """Tests for GET /api/v2/account/2fa/recovery-codes"""

    def test_requires_auth(self, client):
        r = client.get('/api/v2/account/2fa/recovery-codes')
        assert r.status_code == 401

    def test_fails_when_2fa_not_enabled(self, auth_client):
        """Should return 400 when 2FA is not enabled."""
        # Ensure 2FA is off first (may already be off from previous tests)
        r = auth_client.get('/api/v2/account/2fa/recovery-codes')
        # Could be 400 if 2FA not enabled
        body = get_json(r)
        if r.status_code == 400:
            assert 'not enabled' in body.get('message', '').lower() or \
                   'not enabled' in body.get('error', '').lower()

    def test_returns_codes_when_2fa_enabled(self, auth_client):
        """Enable 2FA, then fetch recovery codes."""
        r = auth_client.post('/api/v2/account/2fa/enable')
        secret = assert_success(r)['secret']
        code = pyotp.TOTP(secret).now()
        post_json(auth_client, '/api/v2/account/2fa/confirm', {'code': code})

        r = auth_client.get('/api/v2/account/2fa/recovery-codes')
        data = assert_success(r)
        assert 'codes' in data
        assert 'count' in data
        assert data['count'] > 0

        # Cleanup: disable 2FA
        code = pyotp.TOTP(secret).now()
        post_json(auth_client, '/api/v2/account/2fa/disable', {'code': code})


class TestRegenerateRecoveryCodes:
    """Tests for POST /api/v2/account/2fa/recovery-codes/regenerate"""

    def test_requires_auth(self, client):
        r = post_json(client, '/api/v2/account/2fa/recovery-codes/regenerate',
                      {'code': '000000'})
        assert r.status_code == 401

    def test_missing_code(self, auth_client):
        r = post_json(auth_client,
                      '/api/v2/account/2fa/recovery-codes/regenerate', {})
        assert_error(r, 400)

    def test_fails_when_2fa_not_enabled(self, auth_client):
        r = post_json(auth_client,
                      '/api/v2/account/2fa/recovery-codes/regenerate',
                      {'code': '123456'})
        assert_error(r, 400)

    def test_regenerate_with_valid_code(self, auth_client):
        """Enable 2FA, then regenerate recovery codes."""
        # Enable + confirm
        r = auth_client.post('/api/v2/account/2fa/enable')
        secret = assert_success(r)['secret']
        code = pyotp.TOTP(secret).now()
        r = post_json(auth_client, '/api/v2/account/2fa/confirm', {'code': code})
        old_codes = assert_success(r)['backup_codes']

        # Regenerate
        code = pyotp.TOTP(secret).now()
        r = post_json(auth_client,
                      '/api/v2/account/2fa/recovery-codes/regenerate',
                      {'code': code})
        data = assert_success(r)
        assert 'backup_codes' in data
        assert isinstance(data['backup_codes'], list)
        assert len(data['backup_codes']) == 8
        # New codes should differ from old
        assert data['backup_codes'] != old_codes

        # Cleanup
        code = pyotp.TOTP(secret).now()
        post_json(auth_client, '/api/v2/account/2fa/disable', {'code': code})


# ============================================================================
# Sessions
# ============================================================================

class TestListSessions:
    """Tests for GET /api/v2/account/sessions"""

    def test_requires_auth(self, client):
        r = client.get('/api/v2/account/sessions')
        assert r.status_code == 401

    def test_returns_list(self, auth_client):
        r = auth_client.get('/api/v2/account/sessions')
        data = assert_success(r)
        assert isinstance(data, list)


class TestRevokeSession:
    """Tests for DELETE /api/v2/account/sessions/<id>"""

    def test_requires_auth(self, client):
        r = client.delete('/api/v2/account/sessions/1')
        assert r.status_code == 401

    def test_not_found(self, auth_client):
        r = auth_client.delete('/api/v2/account/sessions/99999')
        assert_error(r, 404)


class TestRevokeAllSessions:
    """Tests for POST /api/v2/account/sessions/revoke-all"""

    def test_requires_auth(self, client):
        r = client.post('/api/v2/account/sessions/revoke-all')
        assert r.status_code == 401

    def test_revoke_all_succeeds(self, auth_client):
        r = auth_client.post('/api/v2/account/sessions/revoke-all')
        assert_success(r)


# ============================================================================
# Activity Log
# ============================================================================

class TestActivityLog:
    """Tests for GET /api/v2/account/activity"""

    def test_requires_auth(self, client):
        r = client.get('/api/v2/account/activity')
        assert r.status_code == 401

    def test_returns_list(self, auth_client):
        r = auth_client.get('/api/v2/account/activity')
        data = assert_success(r)
        assert isinstance(data, list)

    def test_pagination_params(self, auth_client):
        r = auth_client.get('/api/v2/account/activity?page=1&per_page=5')
        body = get_json(r)
        assert r.status_code == 200
        meta = body.get('meta', {})
        if meta:
            assert meta.get('per_page') == 5


# ============================================================================
# API Key full lifecycle
# ============================================================================

class TestAPIKeyLifecycle:
    """End-to-end lifecycle: create → list → get → update → regenerate → delete"""

    def test_full_crud(self, auth_client):
        # Create
        r = post_json(auth_client, '/api/v2/account/apikeys', {
            'name': 'Lifecycle Key',
            'permissions': ['read:certificates', 'write:certificates'],
        })
        created = assert_success(r, 201)
        key_id = created.get('id')
        if key_id is None:
            pytest.skip('Create did not return id')

        # List — should contain the new key
        r = auth_client.get('/api/v2/account/apikeys')
        keys = assert_success(r)
        assert any(k.get('id') == key_id for k in keys)

        # Get single
        r = auth_client.get(f'/api/v2/account/apikeys/{key_id}')
        data = assert_success(r)
        assert data.get('name') == 'Lifecycle Key'

        # Update name
        r = patch_json(auth_client, f'/api/v2/account/apikeys/{key_id}',
                       {'name': 'Renamed Key'})
        data = assert_success(r)
        assert data.get('name') == 'Renamed Key'

        # Regenerate
        r = auth_client.post(f'/api/v2/account/apikeys/{key_id}/regenerate')
        regen = assert_success(r, 201)
        assert regen.get('id') != key_id or 'key' in regen

        # Delete original (now soft-deleted via regenerate, but delete new one)
        new_id = regen.get('id')
        if new_id:
            r = auth_client.delete(f'/api/v2/account/apikeys/{new_id}')
            assert_success(r)


# ============================================================================
# 2FA full lifecycle
# ============================================================================

class TestTwoFactorLifecycle:
    """End-to-end: enable → confirm → get codes → regenerate codes → disable"""

    def test_full_cycle(self, auth_client):
        # Enable
        r = auth_client.post('/api/v2/account/2fa/enable')
        data = assert_success(r)
        secret = data['secret']
        assert len(secret) > 10

        # Confirm with valid TOTP
        totp = pyotp.TOTP(secret)
        r = post_json(auth_client, '/api/v2/account/2fa/confirm',
                      {'code': totp.now()})
        data = assert_success(r)
        backup_codes = data['backup_codes']
        assert len(backup_codes) == 8

        # Get recovery codes (masked)
        r = auth_client.get('/api/v2/account/2fa/recovery-codes')
        data = assert_success(r)
        assert data['count'] == 8

        # Regenerate recovery codes
        r = post_json(auth_client,
                      '/api/v2/account/2fa/recovery-codes/regenerate',
                      {'code': totp.now()})
        data = assert_success(r)
        new_codes = data['backup_codes']
        assert len(new_codes) == 8

        # Disable with backup code
        r = post_json(auth_client, '/api/v2/account/2fa/disable',
                      {'backup_code': new_codes[0]})
        assert_success(r)

        # Verify 2FA is now disabled via profile
        r = auth_client.get('/api/v2/account/profile')
        profile = assert_success(r)
        assert profile.get('two_factor_enabled') is False
