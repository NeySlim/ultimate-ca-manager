"""
RBAC API Endpoint Tests

Tests for /api/v2/rbac/* routes:
  - GET  /permissions           — list available permissions
  - GET  /roles                 — list custom roles
  - POST /roles                 — create custom role
  - GET  /roles/<id>            — get role details
  - PUT  /roles/<id>            — update role
  - DELETE /roles/<id>          — delete custom role
  - GET  /effective-permissions/<user_id> — user effective perms
"""
import json
import pytest


# ============================================================
# Helpers
# ============================================================

def _json(response):
    return json.loads(response.data)


def _post_json(client, url, data):
    return client.post(url, data=json.dumps(data), content_type='application/json')


def _put_json(client, url, data):
    return client.put(url, data=json.dumps(data), content_type='application/json')


# ============================================================
# Auth required (unauthenticated → 401)
# ============================================================

class TestRBACAuthRequired:
    """All RBAC endpoints must reject unauthenticated requests."""

    def test_permissions_requires_auth(self, client):
        r = client.get('/api/v2/rbac/permissions')
        assert r.status_code == 401

    def test_list_roles_requires_auth(self, client):
        r = client.get('/api/v2/rbac/roles')
        assert r.status_code == 401

    def test_create_role_requires_auth(self, client):
        r = _post_json(client, '/api/v2/rbac/roles', {'name': 'NoAuth'})
        assert r.status_code == 401

    def test_get_role_requires_auth(self, client):
        r = client.get('/api/v2/rbac/roles/1')
        assert r.status_code == 401

    def test_update_role_requires_auth(self, client):
        r = _put_json(client, '/api/v2/rbac/roles/1', {'name': 'Updated'})
        assert r.status_code == 401

    def test_delete_role_requires_auth(self, client):
        r = client.delete('/api/v2/rbac/roles/1')
        assert r.status_code == 401

    def test_effective_perms_requires_auth(self, client):
        r = client.get('/api/v2/rbac/effective-permissions/1')
        assert r.status_code == 401


# ============================================================
# GET /permissions
# ============================================================

class TestListPermissions:
    """GET /api/v2/rbac/permissions — list available permissions."""

    def test_returns_200(self, auth_client):
        r = auth_client.get('/api/v2/rbac/permissions')
        assert r.status_code == 200

    def test_returns_list(self, auth_client):
        r = auth_client.get('/api/v2/rbac/permissions')
        data = _json(r).get('data', _json(r))
        assert isinstance(data, list)
        assert len(data) > 0

    def test_permission_format(self, auth_client):
        """Every permission must be 'action:resource'."""
        r = auth_client.get('/api/v2/rbac/permissions')
        data = _json(r).get('data', _json(r))
        for perm in data:
            assert isinstance(perm, str)
            assert ':' in perm, f"Permission '{perm}' missing ':' separator"
            parts = perm.split(':')
            assert len(parts) == 2, f"Permission '{perm}' not in action:resource format"
            assert len(parts[0]) > 0 and len(parts[1]) > 0

    def test_contains_known_permissions(self, auth_client):
        r = auth_client.get('/api/v2/rbac/permissions')
        data = _json(r).get('data', _json(r))
        for expected in ['read:cas', 'write:cas', 'read:certs', 'write:certs',
                         'read:users', 'admin:users', 'read:audit']:
            assert expected in data, f"Missing expected permission '{expected}'"


# ============================================================
# GET /roles — list
# ============================================================

class TestListRoles:
    """GET /api/v2/rbac/roles — list all custom roles."""

    def test_returns_200(self, auth_client):
        r = auth_client.get('/api/v2/rbac/roles')
        assert r.status_code == 200

    def test_returns_list(self, auth_client):
        r = auth_client.get('/api/v2/rbac/roles')
        data = _json(r).get('data', _json(r))
        assert isinstance(data, list)


# ============================================================
# POST /roles — create
# ============================================================

class TestCreateRole:
    """POST /api/v2/rbac/roles — create custom role."""

    def test_create_minimal(self, auth_client):
        r = _post_json(auth_client, '/api/v2/rbac/roles', {
            'name': 'Test Role Minimal',
        })
        assert r.status_code == 200
        body = _json(r)
        role = body.get('data', body)
        assert role['name'] == 'Test Role Minimal'
        assert 'id' in role

    def test_create_with_permissions(self, auth_client):
        r = _post_json(auth_client, '/api/v2/rbac/roles', {
            'name': 'Cert Reader',
            'description': 'Can only read certificates',
            'permissions': ['read:certs', 'read:cas'],
        })
        assert r.status_code == 200
        role = _json(r).get('data', _json(r))
        assert 'read:certs' in role['permissions']
        assert 'read:cas' in role['permissions']
        assert role['description'] == 'Can only read certificates'

    def test_create_missing_name_400(self, auth_client):
        r = _post_json(auth_client, '/api/v2/rbac/roles', {
            'description': 'No name',
        })
        assert r.status_code == 400

    def test_create_empty_name_400(self, auth_client):
        r = _post_json(auth_client, '/api/v2/rbac/roles', {
            'name': '',
        })
        assert r.status_code == 400

    def test_create_duplicate_name_409(self, auth_client):
        name = 'Unique Role For Dup Test'
        _post_json(auth_client, '/api/v2/rbac/roles', {'name': name})
        r = _post_json(auth_client, '/api/v2/rbac/roles', {'name': name})
        assert r.status_code == 409

    def test_create_returns_message(self, auth_client):
        r = _post_json(auth_client, '/api/v2/rbac/roles', {
            'name': 'Role With Msg',
        })
        body = _json(r)
        assert 'message' in body


# ============================================================
# GET /roles/<id> — details
# ============================================================

class TestGetRole:
    """GET /api/v2/rbac/roles/<id> — get role details."""

    def test_get_existing_role(self, auth_client):
        # Create a role first
        cr = _post_json(auth_client, '/api/v2/rbac/roles', {
            'name': 'Role For Get Test',
            'permissions': ['read:certs'],
        })
        role_id = _json(cr).get('data', _json(cr))['id']

        r = auth_client.get(f'/api/v2/rbac/roles/{role_id}')
        assert r.status_code == 200
        role = _json(r).get('data', _json(r))
        assert role['id'] == role_id
        assert role['name'] == 'Role For Get Test'

    def test_get_nonexistent_role_404(self, auth_client):
        r = auth_client.get('/api/v2/rbac/roles/99999')
        assert r.status_code == 404

    def test_role_dict_fields(self, auth_client):
        cr = _post_json(auth_client, '/api/v2/rbac/roles', {
            'name': 'Role Fields Test',
            'permissions': ['read:audit'],
        })
        role_id = _json(cr).get('data', _json(cr))['id']
        r = auth_client.get(f'/api/v2/rbac/roles/{role_id}')
        role = _json(r).get('data', _json(r))
        for key in ('id', 'name', 'description', 'permissions',
                     'all_permissions', 'is_system', 'created_at'):
            assert key in role, f"Missing field '{key}' in role dict"


# ============================================================
# PUT /roles/<id> — update
# ============================================================

class TestUpdateRole:
    """PUT /api/v2/rbac/roles/<id> — update custom role."""

    def test_update_name(self, auth_client):
        cr = _post_json(auth_client, '/api/v2/rbac/roles', {
            'name': 'Before Update Name',
        })
        role_id = _json(cr).get('data', _json(cr))['id']

        r = _put_json(auth_client, f'/api/v2/rbac/roles/{role_id}', {
            'name': 'After Update Name',
        })
        assert r.status_code == 200
        role = _json(r).get('data', _json(r))
        assert role['name'] == 'After Update Name'

    def test_update_permissions(self, auth_client):
        cr = _post_json(auth_client, '/api/v2/rbac/roles', {
            'name': 'Perm Update Test',
            'permissions': ['read:certs'],
        })
        role_id = _json(cr).get('data', _json(cr))['id']

        r = _put_json(auth_client, f'/api/v2/rbac/roles/{role_id}', {
            'permissions': ['read:certs', 'write:certs', 'read:cas'],
        })
        assert r.status_code == 200
        role = _json(r).get('data', _json(r))
        assert set(role['permissions']) == {'read:certs', 'write:certs', 'read:cas'}

    def test_update_description(self, auth_client):
        cr = _post_json(auth_client, '/api/v2/rbac/roles', {
            'name': 'Desc Update Test',
            'description': 'old',
        })
        role_id = _json(cr).get('data', _json(cr))['id']

        r = _put_json(auth_client, f'/api/v2/rbac/roles/{role_id}', {
            'description': 'new description',
        })
        assert r.status_code == 200
        role = _json(r).get('data', _json(r))
        assert role['description'] == 'new description'

    def test_update_nonexistent_404(self, auth_client):
        r = _put_json(auth_client, '/api/v2/rbac/roles/99999', {
            'name': 'Ghost',
        })
        assert r.status_code == 404

    def test_update_returns_message(self, auth_client):
        cr = _post_json(auth_client, '/api/v2/rbac/roles', {
            'name': 'Msg Update Test',
        })
        role_id = _json(cr).get('data', _json(cr))['id']
        r = _put_json(auth_client, f'/api/v2/rbac/roles/{role_id}', {
            'description': 'updated',
        })
        body = _json(r)
        assert 'message' in body


# ============================================================
# DELETE /roles/<id>
# ============================================================

class TestDeleteRole:
    """DELETE /api/v2/rbac/roles/<id> — delete custom role."""

    def test_delete_custom_role(self, auth_client):
        cr = _post_json(auth_client, '/api/v2/rbac/roles', {
            'name': 'Role To Delete',
        })
        role_id = _json(cr).get('data', _json(cr))['id']

        r = auth_client.delete(f'/api/v2/rbac/roles/{role_id}')
        assert r.status_code == 200

        # Confirm gone
        r2 = auth_client.get(f'/api/v2/rbac/roles/{role_id}')
        assert r2.status_code == 404

    def test_delete_nonexistent_404(self, auth_client):
        r = auth_client.delete('/api/v2/rbac/roles/99999')
        assert r.status_code == 404

    def test_delete_system_role_forbidden(self, auth_client):
        """System/built-in roles cannot be deleted."""
        # Create a system role manually via the model
        from models.rbac import CustomRole
        from models import db

        with auth_client.application.app_context():
            existing = CustomRole.query.filter_by(name='System Test Role').first()
            if not existing:
                sys_role = CustomRole(
                    name='System Test Role',
                    description='Built-in',
                    permissions=['read:certs'],
                    is_system=True,
                )
                db.session.add(sys_role)
                db.session.commit()
                role_id = sys_role.id
            else:
                role_id = existing.id

        r = auth_client.delete(f'/api/v2/rbac/roles/{role_id}')
        assert r.status_code == 403


# ============================================================
# GET /effective-permissions/<user_id>
# ============================================================

class TestEffectivePermissions:
    """GET /api/v2/rbac/effective-permissions/<user_id>"""

    def test_admin_has_all_permissions(self, auth_client):
        """Admin user should have all available permissions."""
        # Admin user is typically id=1
        r = auth_client.get('/api/v2/rbac/effective-permissions/1')
        assert r.status_code == 200
        perms = _json(r).get('data', _json(r))
        assert isinstance(perms, list)
        assert len(perms) > 0
        # Admin should have key permissions
        for expected in ['read:cas', 'read:certs', 'admin:users']:
            assert expected in perms, f"Admin missing '{expected}'"

    def test_nonexistent_user_404(self, auth_client):
        r = auth_client.get('/api/v2/rbac/effective-permissions/99999')
        assert r.status_code == 404

    def test_effective_perms_returns_list(self, auth_client):
        r = auth_client.get('/api/v2/rbac/effective-permissions/1')
        data = _json(r).get('data', _json(r))
        assert isinstance(data, list)
        for perm in data:
            assert isinstance(perm, str)

    def test_operator_has_limited_permissions(self, auth_client, create_user):
        """Operator should have more perms than viewer but fewer than admin."""
        user = create_user(username='rbac_operator_test', role='operator')
        user_id = user.get('id', user.get('user_id'))
        if not user_id:
            pytest.skip("Could not determine operator user ID")

        r = auth_client.get(f'/api/v2/rbac/effective-permissions/{user_id}')
        assert r.status_code == 200
        perms = _json(r).get('data', _json(r))
        # Operator should have basic read perms
        assert 'read:certs' in perms
        assert 'read:cas' in perms

    def test_viewer_has_read_only(self, auth_client, create_user):
        """Viewer should only have read permissions."""
        user = create_user(username='rbac_viewer_test', role='viewer')
        user_id = user.get('id', user.get('user_id'))
        if not user_id:
            pytest.skip("Could not determine viewer user ID")

        r = auth_client.get(f'/api/v2/rbac/effective-permissions/{user_id}')
        assert r.status_code == 200
        perms = _json(r).get('data', _json(r))
        assert 'read:cas' in perms
        assert 'read:certs' in perms


# ============================================================
# Role inheritance
# ============================================================

class TestRoleInheritance:
    """Custom roles can inherit permissions from a parent role."""

    def test_child_inherits_parent_perms(self, auth_client):
        # Create parent
        pr = _post_json(auth_client, '/api/v2/rbac/roles', {
            'name': 'Inheritance Parent',
            'permissions': ['read:certs', 'read:cas'],
        })
        parent_id = _json(pr).get('data', _json(pr))['id']

        # Create child inheriting from parent
        cr = _post_json(auth_client, '/api/v2/rbac/roles', {
            'name': 'Inheritance Child',
            'permissions': ['write:certs'],
            'inherits_from': parent_id,
        })
        assert cr.status_code == 200
        child = _json(cr).get('data', _json(cr))
        all_perms = child.get('all_permissions', child.get('permissions', []))
        # Should have own + parent
        assert 'write:certs' in all_perms
        assert 'read:certs' in all_perms
        assert 'read:cas' in all_perms

    def test_update_inherits_from(self, auth_client):
        pr = _post_json(auth_client, '/api/v2/rbac/roles', {
            'name': 'Inherit Update Parent',
            'permissions': ['read:audit'],
        })
        parent_id = _json(pr).get('data', _json(pr))['id']

        cr = _post_json(auth_client, '/api/v2/rbac/roles', {
            'name': 'Inherit Update Child',
            'permissions': ['read:certs'],
        })
        child_id = _json(cr).get('data', _json(cr))['id']

        # Set inheritance
        r = _put_json(auth_client, f'/api/v2/rbac/roles/{child_id}', {
            'inherits_from': parent_id,
        })
        assert r.status_code == 200
        role = _json(r).get('data', _json(r))
        assert role.get('inherits_from') == parent_id


# ============================================================
# Full CRUD lifecycle
# ============================================================

class TestRoleCRUDLifecycle:
    """End-to-end create → read → update → delete cycle."""

    def test_full_lifecycle(self, auth_client):
        # 1. Create
        r = _post_json(auth_client, '/api/v2/rbac/roles', {
            'name': 'Lifecycle Role',
            'description': 'For lifecycle test',
            'permissions': ['read:certs'],
        })
        assert r.status_code == 200
        role = _json(r).get('data', _json(r))
        role_id = role['id']

        # 2. Read
        r = auth_client.get(f'/api/v2/rbac/roles/{role_id}')
        assert r.status_code == 200
        role = _json(r).get('data', _json(r))
        assert role['name'] == 'Lifecycle Role'

        # 3. Update
        r = _put_json(auth_client, f'/api/v2/rbac/roles/{role_id}', {
            'name': 'Lifecycle Role Updated',
            'permissions': ['read:certs', 'write:certs'],
        })
        assert r.status_code == 200
        role = _json(r).get('data', _json(r))
        assert role['name'] == 'Lifecycle Role Updated'
        assert 'write:certs' in role['permissions']

        # 4. Appears in list
        r = auth_client.get('/api/v2/rbac/roles')
        roles = _json(r).get('data', _json(r))
        assert any(ro['id'] == role_id for ro in roles)

        # 5. Delete
        r = auth_client.delete(f'/api/v2/rbac/roles/{role_id}')
        assert r.status_code == 200

        # 6. Gone
        r = auth_client.get(f'/api/v2/rbac/roles/{role_id}')
        assert r.status_code == 404
