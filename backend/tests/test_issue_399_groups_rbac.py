"""Default groups hold real permission lists, and system roles count their users."""
import importlib
import json
import os
import sqlite3

import pytest
from sqlalchemy import create_engine, text

from auth.permissions import GROUP_GRANTABLE_PERMISSIONS, get_group_permissions
from models import User, db
from models.group import Group, GroupMember
from models.rbac import CustomRole

PG_URL = os.getenv('UCM_TEST_PG_URL')
SEEDED = [
    (1, json.dumps('["*"]'), 'Full system administrators with all permissions'),
    (2, json.dumps('["read:certificates", "write:certificates"]'), 'ops'),
    (3, '["read:cas"]', 'already a list'),
    (4, 'not json', 'unreadable'),
]


def _migration():
    return importlib.import_module('migrations.104_group_permissions_lists')


def _check(rows):
    assert rows[1] == ([], _migration().ADMIN_GROUP_NOW)
    assert rows[2] == (['read:certificates', 'write:certificates'], 'ops')
    assert rows[3] == (['read:cas'], 'already a list')


def test_sqlite_decodes_string_permissions():
    m = _migration()
    conn = sqlite3.connect(':memory:')
    conn.execute("CREATE TABLE groups (id INTEGER PRIMARY KEY, name TEXT, description TEXT, permissions TEXT)")
    conn.executemany("INSERT INTO groups (id, permissions, description) VALUES (?, ?, ?)", SEEDED)
    m.upgrade(conn)
    m.upgrade(conn)
    rows = {i: (p, d) for i, p, d in conn.execute("SELECT id, permissions, description FROM groups")}
    assert rows[4] == ('not json', 'unreadable')
    _check({i: (json.loads(p), d) for i, (p, d) in rows.items() if i != 4})


@pytest.mark.postgres
@pytest.mark.skipif(not PG_URL, reason='UCM_TEST_PG_URL not set')
def test_postgres_decodes_string_permissions():
    m = _migration()
    schema = f"migtest_104_{os.getenv('PYTEST_XDIST_WORKER', 'main')}"
    engine = create_engine(PG_URL)
    conn = engine.connect()
    try:
        conn.execute(text(f"DROP SCHEMA IF EXISTS {schema} CASCADE"))
        conn.execute(text(f"CREATE SCHEMA {schema}"))
        conn.execute(text(f"SET search_path TO {schema}"))
        conn.execute(text("CREATE TABLE groups (id INTEGER PRIMARY KEY, name VARCHAR(100), "
                          "description TEXT, permissions JSON)"))
        for gid, perms, desc in SEEDED[:3]:
            conn.execute(text("INSERT INTO groups (id, permissions, description) "
                              "VALUES (:i, CAST(:p AS json), :d)"), {'i': gid, 'p': perms, 'd': desc})
        m.upgrade(conn)
        m.upgrade(conn)
        _check({i: (p, d) for i, p, d in conn.execute(
            text("SELECT id, permissions, description FROM groups"))})
    finally:
        conn.rollback()
        conn.execute(text(f"DROP SCHEMA IF EXISTS {schema} CASCADE"))
        conn.commit()
        conn.close()
        engine.dispose()


def test_seeded_groups_hold_grantable_lists(app):
    with app.app_context():
        groups = Group.query.filter(Group.name.in_(['Certificate Operators', 'Auditors'])).all()
        assert groups
        for group in groups:
            perms = group.permissions
            assert isinstance(perms, list) and perms
            assert set(perms) <= set(GROUP_GRANTABLE_PERMISSIONS)


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
        user = User(username='viewer399', email='viewer399@example.test', role='viewer')
        user.set_password('Str0ng-Passw0rd!')
        db.session.add(user)
        db.session.commit()
        try:
            viewer = CustomRole.query.filter_by(name='Viewer', is_system=True).first()
            assert viewer is not None
            expected = User.query.filter_by(role='viewer').count()
            assert expected >= 1
            assert viewer.to_dict()['user_count'] == expected
        finally:
            db.session.delete(user)
            db.session.commit()
