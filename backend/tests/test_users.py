"""
Users API Tests — /api/v2/users/*

Comprehensive tests for all user management endpoints including:
- Password policy (public)
- Password strength check (public)
- User CRUD (admin-only)
- Bulk operations
- Password reset
- Toggle active status
- CSV import
- mTLS certificate management
"""
import pytest
import json
import io
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

STRONG_PASSWORD = 'S3cure!Pass#99'


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
# Password Policy (public)
# ============================================================

class TestPasswordPolicy:
    """GET /api/v2/users/password-policy"""

    def test_returns_200_without_auth(self, client):
        r = client.get('/api/v2/users/password-policy')
        assert r.status_code == 200

    def test_returns_policy_structure(self, client):
        r = client.get('/api/v2/users/password-policy')
        data = get_json(r)['data']
        assert 'min_length' in data
        assert isinstance(data['min_length'], int)
        assert data['min_length'] >= 8


# ============================================================
# Password Strength (public)
# ============================================================

class TestPasswordStrength:
    """POST /api/v2/users/password-strength"""

    def test_returns_200_without_auth(self, client):
        r = client.post('/api/v2/users/password-strength',
                        data=json.dumps({'password': 'test'}),
                        content_type='application/json')
        assert r.status_code == 200

    def test_weak_password_low_score(self, client):
        r = client.post('/api/v2/users/password-strength',
                        data=json.dumps({'password': 'a'}),
                        content_type='application/json')
        data = get_json(r)['data']
        assert 'score' in data
        assert 'level' in data

    def test_strong_password_high_score(self, client):
        r = client.post('/api/v2/users/password-strength',
                        data=json.dumps({'password': STRONG_PASSWORD}),
                        content_type='application/json')
        data = get_json(r)['data']
        assert data['score'] >= 60

    def test_empty_password(self, client):
        r = client.post('/api/v2/users/password-strength',
                        data=json.dumps({'password': ''}),
                        content_type='application/json')
        assert r.status_code == 200
        data = get_json(r)['data']
        assert data['score'] == 0 or data['level'] == 'weak'


# ============================================================
# List Users
# ============================================================

class TestListUsers:
    """GET /api/v2/users"""

    def test_requires_auth(self, client):
        r = client.get('/api/v2/users')
        assert r.status_code == 401

    def test_returns_users_list(self, auth_client):
        r = auth_client.get('/api/v2/users')
        data = assert_success(r)
        assert isinstance(data, list)
        assert len(data) >= 1  # at least the admin user

    def test_admin_user_present(self, auth_client):
        r = auth_client.get('/api/v2/users')
        data = assert_success(r)
        usernames = [u['username'] for u in data]
        assert 'admin' in usernames

    def test_filter_by_role(self, auth_client):
        r = auth_client.get('/api/v2/users?role=admin')
        data = assert_success(r)
        assert all(u['role'] == 'admin' for u in data)

    def test_filter_by_active(self, auth_client):
        r = auth_client.get('/api/v2/users?active=true')
        data = assert_success(r)
        assert all(u.get('active', True) for u in data)

    def test_search_by_username(self, auth_client):
        r = auth_client.get('/api/v2/users?search=admin')
        data = assert_success(r)
        assert any('admin' in u['username'] for u in data)


# ============================================================
# Create User
# ============================================================

class TestCreateUser:
    """POST /api/v2/users"""

    def test_requires_auth(self, client):
        r = client.post('/api/v2/users',
                        data=json.dumps({
                            'username': 'noauth_user',
                            'password': STRONG_PASSWORD,
                            'email': 'noauth@test.local',
                            'role': 'viewer'
                        }),
                        content_type='application/json')
        assert r.status_code == 401

    def test_create_user_success(self, auth_client):
        r = auth_client.post('/api/v2/users',
                             data=json.dumps({
                                 'username': 'tu_create_ok',
                                 'password': STRONG_PASSWORD,
                                 'email': 'tu_create_ok@test.local',
                                 'role': 'viewer'
                             }),
                             content_type='application/json')
        assert r.status_code == 201
        data = get_json(r)['data']
        assert data['username'] == 'tu_create_ok'
        assert data['role'] == 'viewer'

    def test_create_operator(self, auth_client):
        r = auth_client.post('/api/v2/users',
                             data=json.dumps({
                                 'username': 'tu_operator',
                                 'password': STRONG_PASSWORD,
                                 'email': 'tu_operator@test.local',
                                 'role': 'operator'
                             }),
                             content_type='application/json')
        assert r.status_code == 201
        data = get_json(r)['data']
        assert data['role'] == 'operator'

    def test_create_admin(self, auth_client):
        r = auth_client.post('/api/v2/users',
                             data=json.dumps({
                                 'username': 'tu_admin2',
                                 'password': STRONG_PASSWORD,
                                 'email': 'tu_admin2@test.local',
                                 'role': 'admin'
                             }),
                             content_type='application/json')
        assert r.status_code == 201
        data = get_json(r)['data']
        assert data['role'] == 'admin'

    def test_missing_username(self, auth_client):
        r = auth_client.post('/api/v2/users',
                             data=json.dumps({
                                 'password': STRONG_PASSWORD,
                                 'email': 'nouser@test.local',
                                 'role': 'viewer'
                             }),
                             content_type='application/json')
        assert_error(r, 400)

    def test_missing_email(self, auth_client):
        r = auth_client.post('/api/v2/users',
                             data=json.dumps({
                                 'username': 'tu_noemail',
                                 'password': STRONG_PASSWORD,
                                 'role': 'viewer'
                             }),
                             content_type='application/json')
        assert_error(r, 400)

    def test_missing_password(self, auth_client):
        r = auth_client.post('/api/v2/users',
                             data=json.dumps({
                                 'username': 'tu_nopass',
                                 'email': 'tu_nopass@test.local',
                                 'role': 'viewer'
                             }),
                             content_type='application/json')
        assert_error(r, 400)

    def test_weak_password_rejected(self, auth_client):
        r = auth_client.post('/api/v2/users',
                             data=json.dumps({
                                 'username': 'tu_weakpw',
                                 'password': 'short',
                                 'email': 'tu_weakpw@test.local',
                                 'role': 'viewer'
                             }),
                             content_type='application/json')
        assert_error(r, 400)

    def test_duplicate_username(self, auth_client):
        # Create first
        auth_client.post('/api/v2/users',
                         data=json.dumps({
                             'username': 'tu_dup',
                             'password': STRONG_PASSWORD,
                             'email': 'tu_dup@test.local',
                             'role': 'viewer'
                         }),
                         content_type='application/json')
        # Duplicate
        r = auth_client.post('/api/v2/users',
                             data=json.dumps({
                                 'username': 'tu_dup',
                                 'password': STRONG_PASSWORD,
                                 'email': 'tu_dup2@test.local',
                                 'role': 'viewer'
                             }),
                             content_type='application/json')
        assert_error(r, 409)

    def test_duplicate_email(self, auth_client):
        auth_client.post('/api/v2/users',
                         data=json.dumps({
                             'username': 'tu_dupemail1',
                             'password': STRONG_PASSWORD,
                             'email': 'tu_dupemail@test.local',
                             'role': 'viewer'
                         }),
                         content_type='application/json')
        r = auth_client.post('/api/v2/users',
                             data=json.dumps({
                                 'username': 'tu_dupemail2',
                                 'password': STRONG_PASSWORD,
                                 'email': 'tu_dupemail@test.local',
                                 'role': 'viewer'
                             }),
                             content_type='application/json')
        assert_error(r, 409)

    def test_invalid_role(self, auth_client):
        r = auth_client.post('/api/v2/users',
                             data=json.dumps({
                                 'username': 'tu_badrole',
                                 'password': STRONG_PASSWORD,
                                 'email': 'tu_badrole@test.local',
                                 'role': 'superadmin'
                             }),
                             content_type='application/json')
        assert_error(r, 400)


# ============================================================
# Get User
# ============================================================

class TestGetUser:
    """GET /api/v2/users/<user_id>"""

    def test_requires_auth(self, client):
        r = client.get('/api/v2/users/1')
        assert r.status_code == 401

    def test_get_admin_user(self, auth_client):
        r = auth_client.get('/api/v2/users/1')
        data = assert_success(r)
        assert data['username'] == 'admin'

    def test_get_nonexistent_user(self, auth_client):
        r = auth_client.get('/api/v2/users/99999')
        assert_error(r, 404)

    def test_get_created_user(self, auth_client, create_user):
        user = create_user(username='tu_get_detail', role='viewer',
                           email='tu_get_detail@test.local')
        uid = user['id']
        r = auth_client.get(f'/api/v2/users/{uid}')
        data = assert_success(r)
        assert data['username'] == 'tu_get_detail'


# ============================================================
# Update User
# ============================================================

class TestUpdateUser:
    """PUT /api/v2/users/<user_id>"""

    def test_requires_auth(self, client):
        r = client.put('/api/v2/users/1',
                       data=json.dumps({'full_name': 'Hacked'}),
                       content_type='application/json')
        assert r.status_code == 401

    def test_update_full_name(self, auth_client, create_user):
        user = create_user(username='tu_upd_name', email='tu_upd_name@test.local')
        uid = user['id']
        r = auth_client.put(f'/api/v2/users/{uid}',
                            data=json.dumps({'full_name': 'Updated Name'}),
                            content_type='application/json')
        data = assert_success(r)
        assert data['full_name'] == 'Updated Name'

    def test_update_email(self, auth_client, create_user):
        user = create_user(username='tu_upd_email', email='tu_upd_email@test.local')
        uid = user['id']
        r = auth_client.put(f'/api/v2/users/{uid}',
                            data=json.dumps({'email': 'new_email@test.local'}),
                            content_type='application/json')
        data = assert_success(r)
        assert data['email'] == 'new_email@test.local'

    def test_update_role(self, auth_client, create_user):
        user = create_user(username='tu_upd_role', email='tu_upd_role@test.local',
                           role='viewer')
        uid = user['id']
        r = auth_client.put(f'/api/v2/users/{uid}',
                            data=json.dumps({'role': 'operator'}),
                            content_type='application/json')
        data = assert_success(r)
        assert data['role'] == 'operator'

    def test_update_nonexistent_user(self, auth_client):
        r = auth_client.put('/api/v2/users/99999',
                            data=json.dumps({'full_name': 'Ghost'}),
                            content_type='application/json')
        assert_error(r, 404)

    def test_update_duplicate_email(self, auth_client, create_user):
        user_a = create_user(username='tu_dupem_a', email='tu_dupem_a@test.local')
        user_b = create_user(username='tu_dupem_b', email='tu_dupem_b@test.local')
        r = auth_client.put(f'/api/v2/users/{user_b["id"]}',
                            data=json.dumps({'email': 'tu_dupem_a@test.local'}),
                            content_type='application/json')
        assert_error(r, 409)

    def test_update_password(self, auth_client, create_user):
        user = create_user(username='tu_upd_pw', email='tu_upd_pw@test.local')
        uid = user['id']
        r = auth_client.put(f'/api/v2/users/{uid}',
                            data=json.dumps({'password': 'N3wStr0ng!Pass'}),
                            content_type='application/json')
        assert r.status_code == 200

    def test_update_with_weak_password(self, auth_client, create_user):
        user = create_user(username='tu_upd_weakpw', email='tu_upd_weakpw@test.local')
        uid = user['id']
        r = auth_client.put(f'/api/v2/users/{uid}',
                            data=json.dumps({'password': 'weak'}),
                            content_type='application/json')
        assert_error(r, 400)

    def test_update_invalid_role(self, auth_client, create_user):
        user = create_user(username='tu_upd_badrole', email='tu_upd_badrole@test.local')
        uid = user['id']
        r = auth_client.put(f'/api/v2/users/{uid}',
                            data=json.dumps({'role': 'megaadmin'}),
                            content_type='application/json')
        assert_error(r, 400)


# ============================================================
# Delete User
# ============================================================

class TestDeleteUser:
    """DELETE /api/v2/users/<user_id>"""

    def test_requires_auth(self, client):
        r = client.delete('/api/v2/users/999')
        assert r.status_code == 401

    def test_delete_user_soft(self, auth_client, create_user):
        user = create_user(username='tu_del', email='tu_del@test.local')
        uid = user['id']
        r = auth_client.delete(f'/api/v2/users/{uid}')
        assert r.status_code == 200
        # Verify soft-deleted (still retrievable but inactive)
        r2 = auth_client.get(f'/api/v2/users/{uid}')
        if r2.status_code == 200:
            data = get_json(r2)['data']
            assert data['active'] is False

    def test_cannot_delete_self(self, auth_client):
        # Admin is user id 1
        r = auth_client.delete('/api/v2/users/1')
        assert_error(r, 403)

    def test_delete_nonexistent_user(self, auth_client):
        r = auth_client.delete('/api/v2/users/99999')
        assert_error(r, 404)


# ============================================================
# Bulk Delete
# ============================================================

class TestBulkDelete:
    """POST /api/v2/users/bulk/delete"""

    def test_requires_auth(self, client):
        r = client.post('/api/v2/users/bulk/delete',
                        data=json.dumps({'ids': [999]}),
                        content_type='application/json')
        assert r.status_code == 401

    def test_bulk_delete_success(self, auth_client, create_user):
        u1 = create_user(username='tu_bulk1', email='tu_bulk1@test.local')
        u2 = create_user(username='tu_bulk2', email='tu_bulk2@test.local')
        r = auth_client.post('/api/v2/users/bulk/delete',
                             data=json.dumps({'ids': [u1['id'], u2['id']]}),
                             content_type='application/json')
        data = assert_success(r)
        assert u1['id'] in data['success']
        assert u2['id'] in data['success']

    def test_bulk_delete_missing_ids(self, auth_client):
        r = auth_client.post('/api/v2/users/bulk/delete',
                             data=json.dumps({}),
                             content_type='application/json')
        assert_error(r, 400)

    def test_bulk_delete_nonexistent_ids(self, auth_client):
        r = auth_client.post('/api/v2/users/bulk/delete',
                             data=json.dumps({'ids': [88888, 88889]}),
                             content_type='application/json')
        data = assert_success(r)
        assert len(data['failed']) == 2

    def test_bulk_delete_cannot_include_self(self, auth_client, create_user):
        u = create_user(username='tu_bulkself', email='tu_bulkself@test.local')
        r = auth_client.post('/api/v2/users/bulk/delete',
                             data=json.dumps({'ids': [1, u['id']]}),
                             content_type='application/json')
        data = assert_success(r)
        # Admin (id=1) should fail, other user should succeed
        failed_ids = [f['id'] for f in data['failed']]
        assert 1 in failed_ids
        assert u['id'] in data['success']


# ============================================================
# Reset Password
# ============================================================

class TestResetPassword:
    """POST /api/v2/users/<user_id>/reset-password"""

    def test_requires_auth(self, client):
        r = client.post('/api/v2/users/1/reset-password',
                        data=json.dumps({'new_password': STRONG_PASSWORD}),
                        content_type='application/json')
        assert r.status_code == 401

    def test_reset_password_success(self, auth_client, create_user):
        user = create_user(username='tu_resetpw', email='tu_resetpw@test.local')
        uid = user['id']
        r = auth_client.post(f'/api/v2/users/{uid}/reset-password',
                             data=json.dumps({'new_password': 'N3wP@ssword!'}),
                             content_type='application/json')
        assert r.status_code == 200

    def test_reset_password_missing(self, auth_client, create_user):
        user = create_user(username='tu_resetpw2', email='tu_resetpw2@test.local')
        uid = user['id']
        r = auth_client.post(f'/api/v2/users/{uid}/reset-password',
                             data=json.dumps({}),
                             content_type='application/json')
        assert_error(r, 400)

    def test_reset_password_weak(self, auth_client, create_user):
        user = create_user(username='tu_resetweak', email='tu_resetweak@test.local')
        uid = user['id']
        r = auth_client.post(f'/api/v2/users/{uid}/reset-password',
                             data=json.dumps({'new_password': 'abc'}),
                             content_type='application/json')
        assert_error(r, 400)

    def test_reset_password_nonexistent_user(self, auth_client):
        r = auth_client.post('/api/v2/users/99999/reset-password',
                             data=json.dumps({'new_password': STRONG_PASSWORD}),
                             content_type='application/json')
        assert_error(r, 404)


# ============================================================
# Toggle Active Status
# ============================================================

class TestToggleUser:
    """PATCH /api/v2/users/<user_id>/toggle and POST .../toggle-active"""

    def test_requires_auth(self, client):
        r = client.patch('/api/v2/users/1/toggle')
        assert r.status_code == 401

    def test_toggle_deactivate(self, auth_client, create_user):
        user = create_user(username='tu_toggle1', email='tu_toggle1@test.local')
        uid = user['id']
        r = auth_client.patch(f'/api/v2/users/{uid}/toggle')
        data = assert_success(r)
        assert data['active'] is False

    def test_toggle_reactivate(self, auth_client, create_user):
        user = create_user(username='tu_toggle2', email='tu_toggle2@test.local')
        uid = user['id']
        # Deactivate first
        auth_client.patch(f'/api/v2/users/{uid}/toggle')
        # Reactivate
        r = auth_client.patch(f'/api/v2/users/{uid}/toggle')
        data = assert_success(r)
        assert data['active'] is True

    def test_cannot_toggle_self(self, auth_client):
        r = auth_client.patch('/api/v2/users/1/toggle')
        assert_error(r, 403)

    def test_toggle_nonexistent_user(self, auth_client):
        r = auth_client.patch('/api/v2/users/99999/toggle')
        assert_error(r, 404)

    def test_toggle_active_alt_endpoint(self, auth_client, create_user):
        user = create_user(username='tu_togglealt', email='tu_togglealt@test.local')
        uid = user['id']
        r = auth_client.post(f'/api/v2/users/{uid}/toggle-active')
        data = assert_success(r)
        assert 'active' in data


# ============================================================
# Import Users (CSV)
# ============================================================

class TestImportUsers:
    """POST /api/v2/users/import"""

    def test_requires_auth(self, client):
        r = client.post('/api/v2/users/import')
        assert r.status_code == 401

    def test_import_csv_success(self, auth_client):
        csv_content = (
            'username,email,full_name,role,password\n'
            f'tu_imp1,tu_imp1@test.local,Import One,viewer,{STRONG_PASSWORD}\n'
            f'tu_imp2,tu_imp2@test.local,Import Two,operator,{STRONG_PASSWORD}\n'
        )
        data = {'file': (io.BytesIO(csv_content.encode('utf-8')), 'users.csv')}
        r = auth_client.post('/api/v2/users/import',
                             data=data,
                             content_type='multipart/form-data')
        result = assert_success(r)
        assert result['imported'] == 2
        assert result['skipped'] == 0

    def test_import_no_file(self, auth_client):
        r = auth_client.post('/api/v2/users/import',
                             content_type='multipart/form-data')
        assert_error(r, 400)

    def test_import_non_csv(self, auth_client):
        data = {'file': (io.BytesIO(b'not csv'), 'users.json')}
        r = auth_client.post('/api/v2/users/import',
                             data=data,
                             content_type='multipart/form-data')
        assert_error(r, 400)

    def test_import_skips_weak_passwords(self, auth_client):
        csv_content = (
            'username,email,full_name,role,password\n'
            'tu_imp_weak,tu_imp_weak@test.local,Weak User,viewer,bad\n'
        )
        data = {'file': (io.BytesIO(csv_content.encode('utf-8')), 'users.csv')}
        r = auth_client.post('/api/v2/users/import',
                             data=data,
                             content_type='multipart/form-data')
        result = assert_success(r)
        assert result['imported'] == 0
        assert result['skipped'] == 1
        assert len(result['errors']) == 1

    def test_import_skips_duplicates(self, auth_client):
        csv_content = (
            'username,email,full_name,role,password\n'
            f'admin,admin@test.local,Dup Admin,admin,{STRONG_PASSWORD}\n'
        )
        data = {'file': (io.BytesIO(csv_content.encode('utf-8')), 'users.csv')}
        r = auth_client.post('/api/v2/users/import',
                             data=data,
                             content_type='multipart/form-data')
        result = assert_success(r)
        assert result['skipped'] >= 1

    def test_import_skips_missing_fields(self, auth_client):
        csv_content = (
            'username,email,full_name,role,password\n'
            ',,,viewer,\n'
        )
        data = {'file': (io.BytesIO(csv_content.encode('utf-8')), 'users.csv')}
        r = auth_client.post('/api/v2/users/import',
                             data=data,
                             content_type='multipart/form-data')
        result = assert_success(r)
        assert result['imported'] == 0
        assert result['skipped'] == 1


# ============================================================
# mTLS Certificate Management
# ============================================================

class TestUserMtlsCertificates:
    """
    GET/POST /api/v2/users/<user_id>/mtls/certificates
    DELETE /api/v2/users/<user_id>/mtls/certificates/<cert_id>
    """

    def test_list_mtls_requires_auth(self, client):
        r = client.get('/api/v2/users/1/mtls/certificates')
        assert r.status_code == 401

    def test_list_mtls_nonexistent_user(self, auth_client):
        r = auth_client.get('/api/v2/users/99999/mtls/certificates')
        assert_error(r, 404)

    def test_list_mtls_empty(self, auth_client, create_user):
        user = create_user(username='tu_mtls_list', email='tu_mtls_list@test.local')
        uid = user['id']
        r = auth_client.get(f'/api/v2/users/{uid}/mtls/certificates')
        data = assert_success(r)
        assert isinstance(data, list)
        assert len(data) == 0

    def test_create_mtls_requires_auth(self, client):
        r = client.post('/api/v2/users/1/mtls/certificates',
                        data=json.dumps({'mode': 'generate'}),
                        content_type='application/json')
        assert r.status_code == 401

    def test_create_mtls_nonexistent_user(self, auth_client):
        r = auth_client.post('/api/v2/users/99999/mtls/certificates',
                             data=json.dumps({'mode': 'generate'}),
                             content_type='application/json')
        assert_error(r, 404)

    def test_create_mtls_import_missing_pem(self, auth_client, create_user):
        user = create_user(username='tu_mtls_nopem', email='tu_mtls_nopem@test.local')
        uid = user['id']
        r = auth_client.post(f'/api/v2/users/{uid}/mtls/certificates',
                             data=json.dumps({'mode': 'import', 'pem': ''}),
                             content_type='application/json')
        assert_error(r, 400)

    def test_create_mtls_import_invalid_pem(self, auth_client, create_user):
        user = create_user(username='tu_mtls_badpem', email='tu_mtls_badpem@test.local')
        uid = user['id']
        r = auth_client.post(f'/api/v2/users/{uid}/mtls/certificates',
                             data=json.dumps({'mode': 'import', 'pem': 'not-a-cert'}),
                             content_type='application/json')
        assert_error(r, 400)

    def test_delete_mtls_requires_auth(self, client):
        r = client.delete('/api/v2/users/1/mtls/certificates/1')
        assert r.status_code == 401

    def test_delete_mtls_nonexistent_user(self, auth_client):
        r = auth_client.delete('/api/v2/users/99999/mtls/certificates/1')
        assert_error(r, 404)

    def test_delete_mtls_nonexistent_cert(self, auth_client, create_user):
        user = create_user(username='tu_mtls_delghost',
                           email='tu_mtls_delghost@test.local')
        uid = user['id']
        r = auth_client.delete(f'/api/v2/users/{uid}/mtls/certificates/99999')
        assert_error(r, 404)


# ============================================================
# CRUD Lifecycle
# ============================================================

class TestUserLifecycle:
    """Full create → get → update → toggle → delete lifecycle."""

    def test_full_lifecycle(self, auth_client):
        # Create
        r = auth_client.post('/api/v2/users',
                             data=json.dumps({
                                 'username': 'tu_lifecycle',
                                 'password': STRONG_PASSWORD,
                                 'email': 'tu_lifecycle@test.local',
                                 'full_name': 'Lifecycle User',
                                 'role': 'viewer'
                             }),
                             content_type='application/json')
        assert r.status_code == 201
        user = get_json(r)['data']
        uid = user['id']

        # Get
        r = auth_client.get(f'/api/v2/users/{uid}')
        data = assert_success(r)
        assert data['username'] == 'tu_lifecycle'
        assert data['full_name'] == 'Lifecycle User'

        # Update
        r = auth_client.put(f'/api/v2/users/{uid}',
                            data=json.dumps({
                                'full_name': 'Updated Lifecycle',
                                'role': 'operator'
                            }),
                            content_type='application/json')
        data = assert_success(r)
        assert data['full_name'] == 'Updated Lifecycle'
        assert data['role'] == 'operator'

        # Toggle inactive
        r = auth_client.patch(f'/api/v2/users/{uid}/toggle')
        data = assert_success(r)
        assert data['active'] is False

        # Toggle active again
        r = auth_client.patch(f'/api/v2/users/{uid}/toggle')
        data = assert_success(r)
        assert data['active'] is True

        # Delete (soft)
        r = auth_client.delete(f'/api/v2/users/{uid}')
        assert r.status_code == 200
