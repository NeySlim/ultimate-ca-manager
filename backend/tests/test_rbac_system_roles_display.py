"""Access Control shows the built-in roles with what auth.permissions enforces for them."""
import pytest

from auth.permissions import CUSTOM_ROLE_GRANTABLE_PERMISSIONS, ROLE_PERMISSIONS
from models import db
from models.rbac import SYSTEM_ROLE_USERS, CustomRole


@pytest.fixture
def system_roles(app):
    """The seeded roles, put back if a database reset earlier in the run dropped them."""
    with app.app_context():
        missing = [name for name in SYSTEM_ROLE_USERS
                   if CustomRole.query.filter_by(name=name).first() is None]
        for name in missing:
            db.session.add(CustomRole(name=name, description='', permissions=[], is_system=True))
        db.session.commit()
    yield
    with app.app_context():
        CustomRole.query.filter(CustomRole.name.in_(missing)).delete(synchronize_session=False)
        db.session.commit()


def test_system_roles_show_the_enforced_permissions(auth_client, system_roles):
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


def test_a_custom_role_cannot_inherit_from_a_system_role(app, auth_client, system_roles):
    with app.app_context():
        operator = CustomRole.query.filter_by(name='Operator', is_system=True).first()
        assert operator is not None
        operator_id = operator.id
    r = auth_client.post('/api/v2/rbac/roles', json={'name': 'Child Of Operator', 'permissions': [],
                                                     'inherits_from': operator_id})
    created = (r.get_json() or {}).get('data') or {}
    if created.get('id'):
        auth_client.delete(f"/api/v2/rbac/roles/{created['id']}")
    assert r.status_code == 400, r.data


def test_a_role_already_under_a_system_role_can_still_be_edited(app, auth_client, system_roles):
    with app.app_context():
        operator = CustomRole.query.filter_by(name='Operator', is_system=True).first()
        child = CustomRole(name='Legacy Operator Child', description='', permissions=[],
                           inherits_from=operator.id)
        db.session.add(child)
        db.session.commit()
        child_id, operator_id = child.id, operator.id
    try:
        r = auth_client.put(f'/api/v2/rbac/roles/{child_id}',
                            json={'description': 'kept', 'inherits_from': operator_id})
        assert r.status_code == 200, r.data
    finally:
        auth_client.delete(f'/api/v2/rbac/roles/{child_id}')
