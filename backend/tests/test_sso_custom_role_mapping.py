"""Custom roles in the SSO role mapping (migration 109, resolution, sync, guards)."""
import importlib
import json
import os
import sqlite3
import uuid

import pytest
from sqlalchemy import create_engine, text

from models import AuditLog, User, db
from models.rbac import CustomRole
from models.sso import SSOProvider
from tests.conftest import get_json

PG_URL = os.getenv('UCM_TEST_PG_URL')
JSON = 'application/json'
PROVIDERS = '/api/v2/sso/providers'
TYPES = ('ldap', 'oauth2', 'saml')


def _uid():
    return uuid.uuid4().hex[:8]


@pytest.fixture
def role(app):
    """Factory for custom roles, removed afterwards."""
    made = []

    def _make(name=None):
        with app.app_context():
            r = CustomRole(name=name or f'cr-{_uid()}', permissions=['read:certificates'])
            db.session.add(r)
            db.session.commit()
            made.append(r.id)
            return r.name

    yield _make
    with app.app_context():
        User.query.filter(User.custom_role_id.in_(made)).update(
            {'custom_role_id': None, 'custom_role_source': None}, synchronize_session=False)
        SSOProvider.query.filter(SSOProvider.name.like('crm-%')).delete(synchronize_session=False)
        CustomRole.query.filter(CustomRole.id.in_(made)).delete(synchronize_session=False)
        db.session.commit()


@pytest.fixture
def provider(app):
    made = []

    def _make(ptype='ldap', mapping=None, sync=False, **kw):
        with app.app_context():
            p = SSOProvider(name=f'crm-{_uid()}', provider_type=ptype, enabled=True,
                            auto_create_users=True, default_role='viewer',
                            role_mapping=json.dumps(mapping) if mapping is not None else None,
                            sync_role_on_login=sync, **kw)
            db.session.add(p)
            db.session.commit()
            made.append(p.id)
            return p.id

    yield _make
    with app.app_context():
        User.query.filter(User.sso_provider_id.in_(made)).delete(synchronize_session=False)
        SSOProvider.query.filter(SSOProvider.id.in_(made)).delete(synchronize_session=False)
        db.session.commit()


@pytest.fixture(autouse=True)
def _no_api_provider_left(app):
    """The API allows one provider per type: clear the ones these tests create."""
    def clear():
        with app.app_context():
            SSOProvider.query.filter(SSOProvider.name.like('crm-%')).delete(synchronize_session=False)
            db.session.commit()
    clear()
    yield
    clear()


def _login(app, provider_id, username, groups):
    from api.v2.sso.ldap_routes import _get_or_create_sso_user
    p = db.session.get(SSOProvider, provider_id)
    user, err = _get_or_create_sso_user(p, username, f'{username}@example.test', username,
                                        {'groups': groups, 'sub': username})
    assert err is None, err
    return user


def _post(client, **body):
    base = {'name': f'crm-{_uid()}', 'provider_type': 'oauth2', 'enabled': False}
    base.update(body)
    return client.post(PROVIDERS, data=json.dumps(base), content_type=JSON)


# ---- migration -----------------------------------------------------------------

def test_sqlite_migration_adds_the_column_and_leaves_users_manual():
    m = importlib.import_module('migrations.109_user_custom_role_source')
    conn = sqlite3.connect(':memory:')
    conn.execute('CREATE TABLE users (id INTEGER PRIMARY KEY, username TEXT)')
    conn.execute("INSERT INTO users VALUES (1, 'old')")
    m.upgrade(conn)
    m.upgrade(conn)
    assert conn.execute('SELECT custom_role_source FROM users').fetchone()[0] is None
    m.upgrade(sqlite3.connect(':memory:'))  # no table: a no-op


@pytest.mark.postgres
@pytest.mark.skipif(not PG_URL, reason='UCM_TEST_PG_URL not set')
def test_postgres_migration_adds_the_column_and_leaves_users_manual():
    m = importlib.import_module('migrations.109_user_custom_role_source')
    schema = f"migtest_109_{os.getenv('PYTEST_XDIST_WORKER', 'main')}"
    engine = create_engine(PG_URL)
    conn = engine.connect()
    try:
        conn.execute(text(f'DROP SCHEMA IF EXISTS {schema} CASCADE'))
        conn.execute(text(f'CREATE SCHEMA {schema}'))
        conn.execute(text(f'SET search_path TO {schema}'))
        conn.execute(text('CREATE TABLE users (id INTEGER PRIMARY KEY, username TEXT)'))
        conn.execute(text("INSERT INTO users VALUES (1, 'old')"))
        m.upgrade(conn)
        m.upgrade(conn)
        assert conn.execute(text('SELECT custom_role_source FROM users')).scalar() is None
    finally:
        conn.rollback()
        conn.execute(text(f'DROP SCHEMA IF EXISTS {schema} CASCADE'))
        conn.commit()
        conn.close()
        engine.dispose()


# ---- resolution ----------------------------------------------------------------

class TestResolution:
    def test_a_string_value_stays_a_base_role(self, app, provider):
        from api.v2.sso.helpers import _resolve_mapped_roles
        with app.app_context():
            p = db.session.get(SSOProvider, provider(mapping={'g': 'operator'}))
            assert _resolve_mapped_roles(p, {'groups': ['g']}) == ('operator', None)

    def test_object_with_both_and_with_only_a_custom_role(self, app, provider, role):
        from api.v2.sso.helpers import _resolve_mapped_roles
        name = role()
        with app.app_context():
            p = db.session.get(SSOProvider, provider(mapping={
                'both': {'role': 'auditor', 'custom_role': name},
                'only': {'role': None, 'custom_role': name}}))
            base, custom = _resolve_mapped_roles(p, {'groups': ['both']})
            assert (base, custom.name) == ('auditor', name)
            base, custom = _resolve_mapped_roles(p, {'groups': ['only']})
            assert (base, custom.name) == (None, name)

    def test_base_role_is_the_most_privileged_custom_role_the_first(self, app, provider, role):
        from api.v2.sso.helpers import _resolve_mapped_roles
        first, second = role(), role()
        with app.app_context():
            p = db.session.get(SSOProvider, provider(mapping={
                'a': {'role': 'viewer', 'custom_role': first},
                'b': {'role': 'admin', 'custom_role': second}}))
            base, custom = _resolve_mapped_roles(p, {'groups': ['b', 'a']})
            assert base == 'admin'
            assert custom.name == first  # mapping order, not group order

    def test_an_invalid_value_at_login_never_grants_more_than_viewer(self, app, provider):
        from api.v2.sso.helpers import _resolve_mapped_roles
        with app.app_context():
            p = db.session.get(SSOProvider, provider(mapping={
                'a': {'role': 'root', 'custom_role': 'gone'}, 'b': ['admin'], 'c': 7}))
            assert _resolve_mapped_roles(p, {'groups': ['a', 'b', 'c']}) == ('viewer', None)

    def test_case_insensitive_name_lookup(self, app, provider, role):
        from api.v2.sso.helpers import _resolve_mapped_roles
        name = role()
        with app.app_context():
            p = db.session.get(SSOProvider, provider(mapping={'g': {'custom_role': name.upper()}}))
            assert _resolve_mapped_roles(p, {'groups': ['g']})[1].name == name


# ---- creation and sync, for each protocol --------------------------------------

@pytest.mark.parametrize('ptype', TYPES)
class TestCreationAndSync:
    def test_creation_sets_the_custom_role_with_source_sso(self, app, provider, role, ptype):
        name = role()
        with app.app_context():
            pid = provider(ptype, {'g': {'role': 'operator', 'custom_role': name}})
            user = _login(app, pid, f'u-{_uid()}', ['g'])
            assert user.role == 'operator'
            assert user.custom_role.name == name
            assert user.custom_role_source == 'sso'
            assert user.to_dict()['custom_role_source'] == 'sso'

    def test_creation_without_a_custom_role_leaves_none(self, app, provider, ptype):
        with app.app_context():
            user = _login(app, provider(ptype, {'g': 'admin'}), f'u-{_uid()}', ['g'])
            assert (user.role, user.custom_role_id, user.custom_role_source) == ('admin', None, None)

    def test_custom_only_entry_uses_default_role_for_the_base(self, app, provider, role, ptype):
        name = role()
        with app.app_context():
            user = _login(app, provider(ptype, {'g': {'custom_role': name}}), f'u-{_uid()}', ['g'])
            assert user.role == 'viewer' and user.custom_role.name == name

    def test_without_sync_nothing_changes_after_creation(self, app, provider, role, ptype):
        a, b = role(), role()
        with app.app_context():
            pid = provider(ptype, {'ga': {'custom_role': a}, 'gb': {'custom_role': b}})
            name = f'u-{_uid()}'
            _login(app, pid, name, ['ga'])
            user = _login(app, pid, name, ['gb'])
            assert user.custom_role.name == a

    def test_sync_changes_the_custom_role_and_audits_it(self, app, provider, role, ptype):
        a, b = role(), role()
        with app.app_context():
            pid = provider(ptype, {'ga': {'custom_role': a}, 'gb': {'custom_role': b}}, sync=True)
            name = f'u-{_uid()}'
            _login(app, pid, name, ['ga'])
            user = _login(app, pid, name, ['gb'])
            assert user.custom_role.name == b and user.custom_role_source == 'sso'
            entry = AuditLog.query.filter_by(action='role_change', resource_name=name).first()
            assert entry is not None and a in entry.details and b in entry.details

    def test_sync_removes_an_sso_custom_role_when_no_match_gives_one(self, app, provider, role, ptype):
        a = role()
        with app.app_context():
            pid = provider(ptype, {'ga': {'custom_role': a}}, sync=True)
            name = f'u-{_uid()}'
            _login(app, pid, name, ['ga'])
            user = _login(app, pid, name, ['other'])
            assert user.custom_role_id is None and user.custom_role_source is None
            assert AuditLog.query.filter_by(action='role_change', resource_name=name).count() == 1

    def test_sync_never_removes_a_role_assigned_by_hand(self, app, provider, role, ptype):
        a, manual = role(), role()
        with app.app_context():
            pid = provider(ptype, {'ga': {'custom_role': a}}, sync=True)
            name = f'u-{_uid()}'
            user = _login(app, pid, name, ['other'])
            user.custom_role_id = db.session.query(CustomRole.id).filter_by(name=manual).scalar()
            db.session.commit()
            user = _login(app, pid, name, ['other'])
            assert user.custom_role.name == manual and user.custom_role_source is None

    def test_sync_never_replaces_a_role_assigned_by_hand(self, app, provider, role, ptype):
        a, manual = role(), role()
        with app.app_context():
            pid = provider(ptype, {'ga': {'custom_role': a}}, sync=True)
            name = f'u-{_uid()}'
            user = _login(app, pid, name, ['other'])
            user.custom_role_id = db.session.query(CustomRole.id).filter_by(name=manual).scalar()
            db.session.commit()
            user = _login(app, pid, name, ['ga'])
            assert user.custom_role.name == manual and user.custom_role_source is None


# ---- validation at save --------------------------------------------------------

class TestValidationOnSave:
    @pytest.mark.parametrize('mapping', [
        {'g': 'root'},
        {'g': ''},
        {'g': {'role': 'root'}},
        {'g': {'custom_role': 'no-such-role'}},
        {'g': {'role': None, 'custom_role': None}},
        {'g': {'role': 'admin', 'extra': 1}},
        {'g': 5},
        {'': 'admin'},
        ['admin'],
        '{not json',
    ])
    def test_bad_mapping_is_refused_on_create_and_update(self, auth_client, mapping):
        refused = _post(auth_client, role_mapping=mapping)
        assert refused.status_code == 400
        assert 'role' in get_json(refused)['message'].lower()
        made = _post(auth_client, role_mapping={'g': 'viewer'})
        assert made.status_code in (200, 201), made.data
        created = get_json(made)['data']
        r = auth_client.put(f"{PROVIDERS}/{created['id']}", data=json.dumps({'role_mapping': mapping}),
                            content_type=JSON)
        assert r.status_code == 400, r.data
        shown = get_json(auth_client.get(f"{PROVIDERS}/{created['id']}"))['data']
        assert shown['role_mapping'] == {'g': 'viewer'}

    def test_a_system_role_is_not_a_custom_role(self, app, auth_client):
        with app.app_context():
            system = CustomRole.query.filter_by(is_system=True).first()
            if system is None:
                pytest.skip('no system role seeded')
            name = system.name
        r = _post(auth_client, role_mapping={'g': {'custom_role': name}})
        assert r.status_code == 400

    def test_good_mappings_are_stored_as_sent(self, auth_client, role):
        name = role()
        mapping = {'a': 'admin', 'b': {'role': 'auditor', 'custom_role': name},
                   'c': {'custom_role': name}}
        created = get_json(_post(auth_client, role_mapping=mapping))['data']
        assert created['role_mapping'] == mapping

    def test_blank_editor_rows_are_dropped(self, auth_client):
        created = get_json(_post(auth_client, role_mapping={'': '', 'g': 'admin'}))['data']
        assert created['role_mapping'] == {'g': 'admin'}


# ---- guard on the custom role --------------------------------------------------

class TestRoleGuard:
    @staticmethod
    def _rid(app, name):
        with app.app_context():
            return CustomRole.query.filter_by(name=name).first().id

    def _cited(self, auth_client, name):
        return get_json(_post(auth_client, role_mapping={'g': {'custom_role': name}}))['data']

    def test_delete_is_refused_with_the_providers(self, app, auth_client, role):
        name = role()
        prov = self._cited(auth_client, name)
        rid = self._rid(app, name)
        r = auth_client.delete(f'/api/v2/rbac/roles/{rid}')
        assert r.status_code == 409 and prov['name'] in r.get_data(as_text=True)
        auth_client.put(f"{PROVIDERS}/{prov['id']}", data=json.dumps({'role_mapping': {}}),
                        content_type=JSON)
        assert auth_client.delete(f'/api/v2/rbac/roles/{rid}').status_code == 200

    def test_rename_is_refused_but_other_edits_pass(self, app, auth_client, role):
        name = role()
        prov = self._cited(auth_client, name)
        rid = self._rid(app, name)
        put = lambda **b: auth_client.put(f'/api/v2/rbac/roles/{rid}', data=json.dumps(b),
                                          content_type=JSON)
        r = put(name=f'renamed-{_uid()}')
        assert r.status_code == 409 and prov['name'] in r.get_data(as_text=True)
        assert put(description='still fine').status_code == 200
        assert put(name=name).status_code == 200


# ---- manual writes reset the provenance ----------------------------------------

def test_a_manual_write_of_the_custom_role_clears_the_source(app, auth_client, provider, role):
    a, b = role(), role()
    with app.app_context():
        user = _login(app, provider('ldap', {'g': {'custom_role': a}}), f'u-{_uid()}', ['g'])
        uid = user.id
        b_id = CustomRole.query.filter_by(name=b).first().id
    r = auth_client.put(f'/api/v2/users/{uid}', data=json.dumps({'custom_role_id': b_id}),
                        content_type=JSON)
    assert r.status_code == 200, r.data
    shown = get_json(auth_client.get(f'/api/v2/users/{uid}'))['data']
    assert shown['custom_role_id'] == b_id and shown['custom_role_source'] is None

    with app.app_context():
        db.session.get(User, uid).custom_role_source = 'sso'
        db.session.commit()
    r = auth_client.put(f'/api/v2/users/{uid}', data=json.dumps({'custom_role_id': None}),
                        content_type=JSON)
    assert r.status_code == 200, r.data
    shown = get_json(auth_client.get(f'/api/v2/users/{uid}'))['data']
    assert shown['custom_role_id'] is None and shown['custom_role_source'] is None


def test_the_backup_carries_the_source(app, provider, role):
    from services.backup_service import BackupService
    a = role()
    with app.app_context():
        name = f'u-{_uid()}'
        _login(app, provider('ldap', {'g': {'custom_role': a}}), name, ['g'])
        svc = BackupService()
        _key, data = svc._decrypt_framed(svc.create_backup('Correct-Horse-Battery-9'),
                                         'Correct-Horse-Battery-9')
        row = next(u for u in data['users'] if u['username'] == name)
        assert row['custom_role_source'] == 'sso'
