"""Access Control shows the built-in roles with what auth.permissions enforces for them."""
from auth.permissions import CUSTOM_ROLE_GRANTABLE_PERMISSIONS, ROLE_PERMISSIONS
from models.rbac import SYSTEM_ROLE_USERS


def test_system_roles_show_the_enforced_permissions(auth_client):
    r = auth_client.get('/api/v2/rbac/roles')
    assert r.status_code == 200
    system = {role['name']: role for role in r.get_json()['data'] if role['is_system']}
    assert set(SYSTEM_ROLE_USERS) <= set(system)
    for name, builtin in SYSTEM_ROLE_USERS.items():
        expected = (sorted(CUSTOM_ROLE_GRANTABLE_PERMISSIONS) if builtin == 'admin'
                    else sorted(ROLE_PERMISSIONS[builtin]))
        assert sorted(system[name]['all_permissions']) == expected, name
        assert sorted(system[name]['permissions']) == expected, name


def test_a_custom_role_is_shown_as_stored(auth_client):
    r = auth_client.post('/api/v2/rbac/roles', json={'name': 'Display Check Role',
                                                     'permissions': ['read:cas']})
    assert r.status_code in (200, 201), r.data
    role = r.get_json()['data']
    try:
        assert role['permissions'] == ['read:cas']
        assert role['all_permissions'] == ['read:cas']
    finally:
        auth_client.delete(f"/api/v2/rbac/roles/{role['id']}")
