"""Default groups hold real permission lists, and system roles count their users."""
import importlib
import json
import os
import sqlite3

import pytest
from sqlalchemy import create_engine, text

from auth.permissions import GROUP_GRANTABLE_PERMISSIONS, get_group_permissions
from models import User, db
from models.group import DEFAULT_GROUPS, Group, GroupMember, seed_default_groups
from models.rbac import CustomRole

PG_URL = os.getenv('UCM_TEST_PG_URL')


def test_default_groups_hold_grantable_lists():
    assert DEFAULT_GROUPS
    for group in DEFAULT_GROUPS:
        perms = group['permissions']
        assert isinstance(perms, list) and perms
        assert set(perms) <= set(GROUP_GRANTABLE_PERMISSIONS)


def test_seed_on_empty_table_stores_lists(app):
    with app.app_context():
        saved = [(g.name, g.description, g.permissions) for g in Group.query.all()]
        GroupMember.query.delete()
        Group.query.delete()
        db.session.commit()
        try:
            assert seed_default_groups() == len(DEFAULT_GROUPS)
            assert seed_default_groups() == 0
            # Read back as stored, not through to_dict which would decode text.
            stored = {g.name: g.permissions for g in Group.query.all()}
            assert stored == {g['name']: g['permissions'] for g in DEFAULT_GROUPS}
        finally:
            Group.query.delete()
            db.session.add_all([Group(name=n, description=d, permissions=p) for n, d, p in saved])
            db.session.commit()


@pytest.fixture
def operator_in_string_group(app):
    """A group left with JSON text by an old backup, one member."""
    with app.app_context():
        user = User(username='grp399', email='grp399@example.test', role='viewer')
        user.set_password('Str0ng-Passw0rd!')
        group = Group(name='Old Backup Group', description='',
                      permissions=json.dumps(['write:certificates']))
        db.session.add_all([user, group])
        db.session.flush()
        db.session.add(GroupMember(group_id=group.id, user_id=user.id))
        db.session.commit()
        yield user.id, group.id
        GroupMember.query.filter_by(user_id=user.id).delete()
        db.session.delete(db.session.get(Group, group.id))
        db.session.delete(db.session.get(User, user.id))
        db.session.commit()


def test_string_permissions_read_as_list(app, operator_in_string_group):
    user_id, group_id = operator_in_string_group
    with app.app_context():
        assert db.session.get(Group, group_id).to_dict()['permissions'] == ['write:certificates']
        assert get_group_permissions(db.session.get(User, user_id)) == ['write:certificates']


def test_system_roles_count_builtin_users(app):
    with app.app_context():
        viewer = CustomRole.query.filter_by(name='Viewer').first()
        created = viewer is None
        if created:  # a database reset earlier in the run drops the seeded roles
            viewer = CustomRole(name='Viewer', description='', permissions=[], is_system=True)
            db.session.add(viewer)
        user = User(username='viewer399', email='viewer399@example.test', role='viewer')
        user.set_password('Str0ng-Passw0rd!')
        db.session.add(user)
        db.session.commit()
        try:
            assert viewer.is_system
            expected = User.query.filter_by(role='viewer').count()
            assert expected >= 1
            assert viewer.to_dict()['user_count'] == expected
        finally:
            db.session.delete(user)
            if created:
                db.session.delete(viewer)
            db.session.commit()
