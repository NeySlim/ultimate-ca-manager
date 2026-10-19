"""An assigned custom role grants its permissions, and nothing above them.

Authorisation read the built-in role and the groups only, so a custom role
assigned to a user granted nothing, while the effective-permissions screen
listed it beside a hard-coded Operator list of its own. Both now come from
auth.permissions.get_effective_permissions.
"""
import json

import pytest

from models import CA, User, db
from models.rbac import CustomRole

ROLES = '/api/v2/rbac/roles'


def _login(app, username):
    client = app.test_client()
    r = client.post('/api/v2/auth/login',
                    data=json.dumps({'username': username, 'password': 'TestPass123!'}),
                    content_type='application/json')
    assert r.status_code == 200, r.data
    return client


def _role(auth_client, name, permissions, inherits_from=None):
    body = {'name': name, 'permissions': permissions}
    if inherits_from is not None:
        body['inherits_from'] = inherits_from
    r = auth_client.post(ROLES, data=json.dumps(body), content_type='application/json')
    assert r.status_code == 200, r.data
    return json.loads(r.data)['data']['id']


def _assign(auth_client, user_id, role_id):
    r = auth_client.put(f'/api/v2/users/{user_id}', data=json.dumps({'custom_role_id': role_id}),
                        content_type='application/json')
    assert r.status_code == 200, r.data


def _viewer(app, create_user, username):
    create_user(username=username, role='viewer')
    with app.app_context():
        user_id = User.query.filter_by(username=username).first().id
    return user_id, _login(app, username)


def _issue(client, ca_id, cn):
    return client.post('/api/v2/certificates',
                       data=json.dumps({'cn': cn, 'ca_id': ca_id, 'validity_days': 30}),
                       content_type='application/json')


@pytest.fixture
def issuing_ca(create_ca):
    return create_ca(cn='Custom Role Issuing CA')['id']


class TestAssignedRoleApplies:
    def test_viewer_with_role_issues_then_loses_it(self, app, auth_client, create_user, issuing_ca):
        role_id = _role(auth_client, 'Issuer Probe Role', ['read:certs', 'write:certs'])
        user_id, viewer = _viewer(app, create_user, 'custom_role_issuer')

        assert _issue(viewer, issuing_ca, 'before.example.com').status_code == 403

        _assign(auth_client, user_id, role_id)
        r = _issue(viewer, issuing_ca, 'granted.example.com')
        assert r.status_code in (200, 201), r.data[:200]

        # Same session: permissions are recomputed on every request
        _assign(auth_client, user_id, None)
        assert _issue(viewer, issuing_ca, 'revoked.example.com').status_code == 403

    def test_inherited_permissions_apply(self, app, auth_client, create_user, issuing_ca):
        parent = _role(auth_client, 'Issuer Parent Role', ['read:certificates', 'write:certificates'])
        child = _role(auth_client, 'Issuer Child Role', ['read:cas'], inherits_from=parent)
        user_id, viewer = _viewer(app, create_user, 'custom_role_heir')
        _assign(auth_client, user_id, child)
        r = _issue(viewer, issuing_ca, 'inherited.example.com')
        assert r.status_code in (200, 201), r.data[:200]

    def test_role_with_private_keys_exports_a_ca_key(self, app, auth_client, create_user, create_ca):
        ca = create_ca(cn='Custom Role Key Export CA')
        body = json.dumps({'format': 'pkcs12', 'password': 'ExportPass123!'})
        writer = _role(auth_client, 'CA Writer Probe Role', ['read:cas', 'write:cas'])
        holder = _role(auth_client, 'CA Key Holder Probe Role',
                       ['read:cas', 'write:cas', 'read:private_keys'])
        user_id, viewer = _viewer(app, create_user, 'custom_role_key_holder')

        _assign(auth_client, user_id, writer)
        r = viewer.post(f"/api/v2/cas/{ca['id']}/export", data=body, content_type='application/json')
        assert r.status_code == 403

        _assign(auth_client, user_id, holder)
        r = viewer.post(f"/api/v2/cas/{ca['id']}/export", data=body, content_type='application/json')
        assert r.status_code == 200, r.data[:200]

    def test_effective_endpoint_is_what_authorisation_applies(self, app, auth_client, create_user):
        role_id = _role(auth_client, 'Effective Probe Role', ['read:audit', 'write:crl'])
        user_id, viewer = _viewer(app, create_user, 'custom_role_effective')
        _assign(auth_client, user_id, role_id)

        shown = json.loads(auth_client.get(f'/api/v2/rbac/effective-permissions/{user_id}').data)['data']
        applied = json.loads(viewer.get('/api/v2/auth/verify').data)['data']['permissions']
        assert sorted(shown) == sorted(applied)
        assert {'read:audit', 'write:crl'} <= set(applied)


class TestNoPathToAdministrator:
    @pytest.mark.parametrize('perm', ['*', 'read:*', 'admin:system', 'admin:users',
                                      'write:users', 'read:sso', 'write:deploy', 'sign:csrs',
                                      'write:ad_connector', 'write:hsm'])
    def test_scope_is_refused(self, auth_client, perm):
        r = auth_client.post(ROLES, data=json.dumps({'name': f'Refused {perm.replace(":", " ").replace("*", "x")}',
                                                     'permissions': [perm]}),
                             content_type='application/json')
        assert r.status_code == 400, f'{perm} accepted in a custom role'

    def test_a_stored_wildcard_grants_nothing(self, app, auth_client, create_user):
        """A role written before validation (the seeded Administrator one) holds `*`."""
        with app.app_context():
            role = CustomRole(name='Stored Wildcard Probe', permissions=['*', 'admin:users'])
            db.session.add(role)
            db.session.commit()
            role_id = role.id
        user_id, viewer = _viewer(app, create_user, 'custom_role_wildcard')
        _assign(auth_client, user_id, role_id)
        assert viewer.get('/api/v2/users').status_code == 403
        assert viewer.get('/api/v2/system/backups').status_code == 403

    def test_an_operator_cannot_create_or_self_assign(self, app, auth_client, create_user):
        role_id = _role(auth_client, 'Self Assign Probe Role', ['read:private_keys'])
        create_user(username='custom_role_operator', role='operator')
        with app.app_context():
            op_id = User.query.filter_by(username='custom_role_operator').first().id
        op = _login(app, 'custom_role_operator')
        r = op.post(ROLES, data=json.dumps({'name': 'Op Made', 'permissions': ['read:cas']}),
                    content_type='application/json')
        assert r.status_code == 403
        r = op.put(f'/api/v2/users/{op_id}', data=json.dumps({'custom_role_id': role_id}),
                   content_type='application/json')
        assert r.status_code == 403


class TestInheritanceIsBounded:
    def test_a_cycle_is_refused(self, auth_client):
        a = _role(auth_client, 'Cycle A', ['read:cas'])
        b = _role(auth_client, 'Cycle B', ['read:crl'], inherits_from=a)
        r = auth_client.put(f'{ROLES}/{a}', data=json.dumps({'inherits_from': b}),
                            content_type='application/json')
        assert r.status_code == 400
        r = auth_client.put(f'{ROLES}/{a}', data=json.dumps({'inherits_from': a}),
                            content_type='application/json')
        assert r.status_code == 400

    def test_a_stored_cycle_does_not_hang(self, app, auth_client, create_user):
        a = _role(auth_client, 'Stored Cycle A', ['read:audit'])
        b = _role(auth_client, 'Stored Cycle B', ['write:crl'], inherits_from=a)
        with app.app_context():
            db.session.get(CustomRole, a).inherits_from = b
            db.session.commit()
        user_id, viewer = _viewer(app, create_user, 'custom_role_cycle')
        _assign(auth_client, user_id, b)
        perms = json.loads(viewer.get('/api/v2/auth/verify').data)['data']['permissions']
        assert {'read:audit', 'write:crl'} <= set(perms)

    def test_a_parent_in_use_cannot_be_deleted(self, auth_client):
        parent = _role(auth_client, 'Deletion Parent', ['read:cas'])
        _role(auth_client, 'Deletion Child', ['read:crl'], inherits_from=parent)
        assert auth_client.delete(f'{ROLES}/{parent}').status_code == 409


class _Link:
    def __init__(self, role_id, parent=None):
        self.id, self.parent, self.permissions = role_id, parent, []


class TestChainIsBounded:
    def test_a_cycle_yields_each_role_once(self):
        from auth.permissions import custom_role_chain
        a = _Link(1)
        b = _Link(2, a)
        a.parent = b
        assert [r.id for r in custom_role_chain(b)] == [2, 1]

    def test_a_long_chain_stops_at_the_depth_bound(self):
        from auth.permissions import MAX_ROLE_DEPTH, custom_role_chain
        role = None
        for i in range(MAX_ROLE_DEPTH + 10):
            role = _Link(i, role)
        assert len(custom_role_chain(role)) == MAX_ROLE_DEPTH


class TestStoredPermissionsAreKept:
    def test_a_save_keeps_an_ignored_permission(self, app, auth_client):
        with app.app_context():
            role = CustomRole(name='Kept Ignored Probe', permissions=['*', 'read:dashboard'])
            db.session.add(role)
            db.session.commit()
            role_id = role.id
        r = auth_client.put(f'{ROLES}/{role_id}',
                            data=json.dumps({'permissions': ['*', 'read:dashboard', 'read:certs']}),
                            content_type='application/json')
        assert r.status_code == 200, r.data
        data = json.loads(r.data)['data']
        assert data['permissions'] == ['*', 'read:dashboard', 'read:certificates']
        assert data['all_permissions'] == ['read:certificates']

    def test_a_save_cannot_add_a_reserved_permission(self, auth_client):
        role_id = _role(auth_client, 'No New Wildcard Probe', ['read:cas'])
        r = auth_client.put(f'{ROLES}/{role_id}', data=json.dumps({'permissions': ['read:cas', '*']}),
                            content_type='application/json')
        assert r.status_code == 400
