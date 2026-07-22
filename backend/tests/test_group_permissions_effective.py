"""Group permissions are actually enforced.

`Group.permissions` was stored but never consulted by authorisation, so any
grant made through a group was inert. These tests pin the behaviour now that
group permissions are unioned with the role's, and — more importantly — pin the
limits: a group must never be a path to administrator.
"""
import json

import pytest

from auth.permissions import (
    GROUP_GRANTABLE_PERMISSIONS,
    get_effective_permissions,
    get_group_permissions,
)
from models import User, db
from models.group import Group, GroupMember


@pytest.fixture
def viewer_in_group(app):
    """A viewer plus a group granting an extra permission, linked together."""
    with app.app_context():
        user = User(username='grp-viewer', email='grp-viewer@example.test', role='viewer')
        user.set_password('Str0ng-Passw0rd!')
        db.session.add(user)
        group = Group(name='Cert Writers', description='',
                      permissions=['write:certificates'])
        db.session.add(group)
        db.session.flush()
        db.session.add(GroupMember(group_id=group.id, user_id=user.id))
        db.session.commit()
        yield {'user_id': user.id, 'group_id': group.id}

        GroupMember.query.filter_by(user_id=user.id).delete()
        db.session.delete(db.session.get(Group, group.id))
        db.session.delete(db.session.get(User, user.id))
        db.session.commit()


class TestGrantableSet:

    def test_never_contains_admin_or_wildcard(self):
        """Group membership must not be able to confer administrator."""
        assert '*' not in GROUP_GRANTABLE_PERMISSIONS
        assert not [p for p in GROUP_GRANTABLE_PERMISSIONS if p.startswith('admin:')]

    def test_uses_the_enforced_vocabulary(self):
        """Grants must name resources @require_auth actually checks."""
        assert 'read:certificates' in GROUP_GRANTABLE_PERMISSIONS
        # `certs` was the old, never-enforced spelling
        assert 'read:certs' not in GROUP_GRANTABLE_PERMISSIONS


class TestEffectivePermissions:

    def test_group_permission_is_added_to_role(self, app, viewer_in_group):
        with app.app_context():
            user = db.session.get(User, viewer_in_group['user_id'])
            perms = get_effective_permissions(user)
            # from the viewer role
            assert 'read:certificates' in perms
            # from the group — previously ignored entirely
            assert 'write:certificates' in perms

    def test_no_duplicates(self, app, viewer_in_group):
        with app.app_context():
            user = db.session.get(User, viewer_in_group['user_id'])
            group = db.session.get(Group, viewer_in_group['group_id'])
            group.permissions = ['read:certificates', 'write:certificates']
            db.session.commit()
            perms = get_effective_permissions(user)
            assert perms.count('read:certificates') == 1

    def test_non_grantable_permission_is_ignored(self, app, viewer_in_group):
        """A permission that reached the DB by another route stays inert."""
        with app.app_context():
            group = db.session.get(Group, viewer_in_group['group_id'])
            group.permissions = ['admin:system', '*', 'read:certs']
            db.session.commit()
            user = db.session.get(User, viewer_in_group['user_id'])
            perms = get_effective_permissions(user)
            assert '*' not in perms
            assert 'admin:system' not in perms
            assert 'read:certs' not in perms

    def test_admin_is_unchanged(self, app):
        with app.app_context():
            admin = User.query.filter_by(role='admin').first()
            assert get_effective_permissions(admin) == ['*']

    def test_user_without_groups_matches_role(self, app):
        with app.app_context():
            user = User(username='grp-none', email='grp-none@example.test', role='viewer')
            user.set_password('Str0ng-Passw0rd!')
            db.session.add(user)
            db.session.commit()
            try:
                from auth.permissions import get_role_permissions
                assert get_effective_permissions(user) == get_role_permissions('viewer')
                assert get_group_permissions(user) == []
            finally:
                db.session.delete(user)
                db.session.commit()


class TestEnforcement:
    """The permission must work end-to-end, not just in the helper."""

    def _login(self, client, username, password):
        return client.post('/api/v2/auth/login/password',
                           data=json.dumps({'username': username, 'password': password}),
                           content_type='application/json')

    def test_login_response_advertises_group_permissions(self, app, client, viewer_in_group):
        """The UI gates on the login payload — it must match what the API enforces."""
        r = self._login(client, 'grp-viewer', 'Str0ng-Passw0rd!')
        assert r.status_code == 200, r.data
        perms = r.get_json()['data']['permissions']
        assert 'write:certificates' in perms

    def test_group_permission_grants_api_access(self, app, client, viewer_in_group):
        """A viewer normally cannot write certificates; the group allows it."""
        self._login(client, 'grp-viewer', 'Str0ng-Passw0rd!')
        # Hitting a write:certificates endpoint must no longer be a 403.
        r = client.post('/api/v2/certificates',
                        data=json.dumps({}), content_type='application/json')
        assert r.status_code != 403, r.data

    def test_removing_membership_revokes_access(self, app, client, viewer_in_group):
        with app.app_context():
            GroupMember.query.filter_by(user_id=viewer_in_group['user_id']).delete()
            db.session.commit()
        self._login(client, 'grp-viewer', 'Str0ng-Passw0rd!')
        r = client.post('/api/v2/certificates',
                        data=json.dumps({}), content_type='application/json')
        assert r.status_code == 403
