"""
SSO Authentication Tests

Tests SSO provider management, auth response contracts, rate limiting,
and role validation. Ensures all auth endpoints return consistent response
structures so the frontend can set permissions correctly.

Uses Flask test client with create_app factory.
"""
import pytest
import os
import sys
import json
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


@pytest.fixture(scope='module')
def app():
    """Create app with test configuration"""
    os.environ['SECRET_KEY'] = 'test-secret-key-for-testing'
    os.environ['JWT_SECRET_KEY'] = 'test-jwt-secret-key-for-testing'
    os.environ['UCM_ENV'] = 'test'
    os.environ['HTTP_REDIRECT'] = 'false'
    os.environ['INITIAL_ADMIN_PASSWORD'] = 'changeme123'
    os.environ['CSRF_DISABLED'] = 'true'

    with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as f:
        os.environ['UCM_DATABASE_PATH'] = f.name
        temp_db = f.name

    from app import create_app
    app = create_app('testing')
    app.config['TESTING'] = True
    app.config['WTF_CSRF_ENABLED'] = False

    yield app

    if os.path.exists(temp_db):
        os.unlink(temp_db)


@pytest.fixture(scope='module')
def client(app):
    return app.test_client()


@pytest.fixture(scope='module')
def auth_client(app):
    """Authenticated admin client"""
    client = app.test_client()
    r = client.post('/api/v2/auth/login',
        data=json.dumps({'username': 'admin', 'password': 'changeme123'}),
        content_type='application/json')
    assert r.status_code == 200, f'Login failed: {r.data}'
    return client


# ============================================================
# Auth Response Contract — all login endpoints must return
# the same fields so the frontend can set permissions
# ============================================================
class TestAuthResponseContract:
    """Verify all auth flows return consistent response structure"""

    REQUIRED_AUTH_FIELDS = {'user', 'csrf_token'}

    def test_password_login_response_structure(self, client):
        """POST /auth/login → response must have user + csrf_token"""
        r = client.post('/api/v2/auth/login',
            data=json.dumps({'username': 'admin', 'password': 'changeme123'}),
            content_type='application/json')
        assert r.status_code == 200
        data = json.loads(r.data)
        resp_data = data.get('data', data)
        assert 'user' in resp_data, 'Password login must return user object'
        assert 'csrf_token' in resp_data, 'Password login must return csrf_token'

    def test_verify_response_has_permissions(self, auth_client):
        """GET /auth/verify → must return permissions and role"""
        r = auth_client.get('/api/v2/auth/verify')
        assert r.status_code == 200
        data = json.loads(r.data)
        resp_data = data.get('data', data)
        assert 'permissions' in resp_data, 'Verify must return permissions'
        assert 'role' in resp_data, 'Verify must return role'
        assert 'csrf_token' in resp_data, 'Verify must return csrf_token'
        assert isinstance(resp_data['permissions'], list), 'Permissions must be a list'

    def test_admin_verify_has_wildcard_permission(self, auth_client):
        """Admin user should have ['*'] permissions"""
        r = auth_client.get('/api/v2/auth/verify')
        data = json.loads(r.data)
        resp_data = data.get('data', data)
        assert '*' in resp_data['permissions'], 'Admin should have wildcard permission'
        assert resp_data['role'] == 'admin'


# ============================================================
# SSO Provider CRUD
# ============================================================
class TestSSOProviderCRUD:
    """Test SSO provider management endpoints"""

    def test_list_providers_requires_auth(self, client):
        """GET /sso/providers → 401 without auth"""
        fresh = client.application.test_client()
        r = fresh.get('/api/v2/sso/providers')
        assert r.status_code == 401

    def test_list_providers(self, auth_client):
        """GET /sso/providers → list"""
        r = auth_client.get('/api/v2/sso/providers')
        assert r.status_code == 200
        data = json.loads(r.data)
        assert isinstance(data.get('data', data), list)

    def test_create_ldap_provider(self, auth_client):
        """POST /sso/providers → create LDAP provider"""
        r = auth_client.post('/api/v2/sso/providers',
            data=json.dumps({
                'name': 'test-ldap',
                'provider_type': 'ldap',
                'display_name': 'Test LDAP',
                'enabled': False,
                'default_role': 'operator',
                'ldap_server': 'ldap.test.com',
                'ldap_port': 389,
                'ldap_bind_dn': 'cn=admin,dc=test',
                'ldap_bind_password': 'secret',
                'ldap_base_dn': 'ou=users,dc=test',
                'ldap_user_filter': '(uid={username})',
                'ldap_username_attr': 'uid',
                'ldap_email_attr': 'mail',
                'ldap_fullname_attr': 'cn',
            }),
            content_type='application/json')
        assert r.status_code in (200, 201), f'Create LDAP failed: {r.data}'
        data = json.loads(r.data)
        provider = data.get('data', data)
        assert provider['name'] == 'test-ldap'
        assert provider['default_role'] == 'operator'

    def test_create_provider_invalid_role_defaults_to_viewer(self, auth_client):
        """POST /sso/providers with invalid default_role → fallback to viewer"""
        r = auth_client.post('/api/v2/sso/providers',
            data=json.dumps({
                'name': 'test-bad-role',
                'provider_type': 'oauth2',
                'default_role': 'superadmin',
                'oauth2_client_id': 'test-client',
                'oauth2_client_secret': 'test-secret',
                'oauth2_auth_url': 'https://auth.test.com/authorize',
                'oauth2_token_url': 'https://auth.test.com/token',
                'oauth2_userinfo_url': 'https://auth.test.com/userinfo',
            }),
            content_type='application/json')
        assert r.status_code in (200, 201)
        data = json.loads(r.data)
        provider = data.get('data', data)
        assert provider['default_role'] == 'viewer', \
            f'Invalid role should fallback to viewer, got {provider["default_role"]}'

    def test_update_provider_invalid_role(self, auth_client):
        """PUT /sso/providers/<id> with invalid role → fallback to viewer"""
        # First, get providers to find the test one
        r = auth_client.get('/api/v2/sso/providers')
        providers = json.loads(r.data).get('data', [])
        test_provider = next((p for p in providers if p['name'] == 'test-ldap'), None)
        if not test_provider:
            pytest.skip('No test provider found')

        r = auth_client.put(f'/api/v2/sso/providers/{test_provider["id"]}',
            data=json.dumps({'default_role': 'root'}),
            content_type='application/json')
        assert r.status_code == 200
        data = json.loads(r.data)
        provider = data.get('data', data)
        assert provider['default_role'] == 'viewer'

    def test_available_providers_public(self, client):
        """GET /sso/available → public endpoint, no auth"""
        r = client.get('/api/v2/sso/available')
        assert r.status_code == 200
        data = json.loads(r.data)
        assert isinstance(data.get('data', data), list)


# ============================================================
# LDAP Login — Rate Limiting & Input Validation
# ============================================================
class TestLDAPLogin:
    """Test LDAP login endpoint security"""

    def test_ldap_login_missing_credentials(self, client):
        """POST /sso/ldap/login without credentials → 400"""
        r = client.post('/api/v2/sso/ldap/login',
            data=json.dumps({}),
            content_type='application/json')
        assert r.status_code == 400

    def test_ldap_login_missing_password(self, client):
        """POST /sso/ldap/login without password → 400"""
        r = client.post('/api/v2/sso/ldap/login',
            data=json.dumps({'username': 'alice'}),
            content_type='application/json')
        assert r.status_code == 400

    def test_ldap_login_no_provider(self, client):
        """POST /sso/ldap/login with no enabled provider → 400"""
        r = client.post('/api/v2/sso/ldap/login',
            data=json.dumps({'username': 'alice', 'password': 'test123'}),
            content_type='application/json')
        # No enabled LDAP provider in test DB
        assert r.status_code == 400

    def test_ldap_login_error_is_generic(self, client):
        """LDAP auth errors should not leak user enumeration info"""
        r = client.post('/api/v2/sso/ldap/login',
            data=json.dumps({'username': 'alice', 'password': 'wrong'}),
            content_type='application/json')
        if r.status_code == 401:
            data = json.loads(r.data)
            msg = data.get('message', '').lower()
            assert 'not found' not in msg, 'Error should not reveal user existence'
            assert 'invalid password' not in msg, 'Error should not distinguish user vs password'


# ============================================================
# Role Resolution — _resolve_role helper
# ============================================================
class TestRoleResolution:
    """Test the _resolve_role helper function directly"""

    def test_resolve_role_with_valid_mapping(self, app):
        """Role mapping matches → mapped role"""
        with app.app_context():
            from api.v2.sso import _resolve_role
            from unittest.mock import MagicMock

            provider = MagicMock()
            provider.role_mapping = json.dumps({'admins': 'admin', 'ops': 'operator'})
            provider.default_role = 'viewer'

            role = _resolve_role(provider, {'groups': ['admins']})
            assert role == 'admin'

    def test_resolve_role_no_match_uses_default(self, app):
        """No role mapping match → default_role"""
        with app.app_context():
            from api.v2.sso import _resolve_role
            from unittest.mock import MagicMock

            provider = MagicMock()
            provider.role_mapping = json.dumps({'admins': 'admin'})
            provider.default_role = 'operator'

            role = _resolve_role(provider, {'groups': ['users']})
            assert role == 'operator'

    def test_resolve_role_no_mapping_uses_default(self, app):
        """No role_mapping configured → default_role"""
        with app.app_context():
            from api.v2.sso import _resolve_role
            from unittest.mock import MagicMock

            provider = MagicMock()
            provider.role_mapping = None
            provider.default_role = 'admin'

            role = _resolve_role(provider, {'groups': []})
            assert role == 'admin'

    def test_resolve_role_invalid_default_falls_to_viewer(self, app):
        """Invalid default_role → viewer"""
        with app.app_context():
            from api.v2.sso import _resolve_role
            from unittest.mock import MagicMock

            provider = MagicMock()
            provider.role_mapping = None
            provider.default_role = 'superadmin'

            role = _resolve_role(provider, {})
            assert role == 'viewer'

    def test_resolve_role_invalid_mapped_role_falls_to_viewer(self, app):
        """Mapped role value is invalid → viewer"""
        with app.app_context():
            from api.v2.sso import _resolve_role
            from unittest.mock import MagicMock

            provider = MagicMock()
            provider.role_mapping = json.dumps({'admins': 'root'})
            provider.default_role = 'operator'

            role = _resolve_role(provider, {'groups': ['admins']})
            assert role == 'viewer'

    def test_resolve_role_multi_match_highest_privilege_wins(self, app):
        """Several matching groups → highest-privilege role regardless of entry order (#221)"""
        with app.app_context():
            from api.v2.sso import _resolve_role
            from unittest.mock import MagicMock

            provider = MagicMock()
            # Least-privileged entry listed first — order must not matter.
            provider.role_mapping = json.dumps({'staff': 'viewer', 'auditors': 'auditor', 'pki-admins': 'admin'})
            provider.default_role = 'viewer'

            role = _resolve_role(provider, {'groups': ['staff', 'pki-admins', 'auditors']})
            assert role == 'admin'

    def test_resolve_role_multi_match_ignores_invalid_entry(self, app):
        """Multi-match with one invalid mapped role → invalid counts as viewer, not admin"""
        with app.app_context():
            from api.v2.sso import _resolve_role
            from unittest.mock import MagicMock

            provider = MagicMock()
            provider.role_mapping = json.dumps({'staff': 'root', 'ops': 'operator'})
            provider.default_role = 'viewer'

            role = _resolve_role(provider, {'groups': ['staff', 'ops']})
            assert role == 'operator'

    def test_resolve_role_groups_as_string(self, app):
        """External roles as string (not list) → still works"""
        with app.app_context():
            from api.v2.sso import _resolve_role
            from unittest.mock import MagicMock

            provider = MagicMock()
            provider.role_mapping = json.dumps({'admins': 'admin'})
            provider.default_role = 'viewer'

            role = _resolve_role(provider, {'groups': 'admins'})
            assert role == 'admin'


# ============================================================
# Role Resolution — _resolve_role_from_mapping (#81)
# ============================================================
class TestResolveRoleFromMapping:
    """`_resolve_role_from_mapping` returns the mapped role or None,
    never falls back to default_role. Used at login to avoid #81
    (UI role overwritten on every SSO login)."""

    def test_mapping_match_returns_mapped(self, app):
        with app.app_context():
            from api.v2.sso import _resolve_role_from_mapping
            from unittest.mock import MagicMock

            provider = MagicMock()
            provider.role_mapping = json.dumps({'admins': 'admin'})
            provider.default_role = 'viewer'

            assert _resolve_role_from_mapping(provider, {'groups': ['admins']}) == 'admin'

    def test_no_mapping_returns_none(self, app):
        with app.app_context():
            from api.v2.sso import _resolve_role_from_mapping
            from unittest.mock import MagicMock

            provider = MagicMock()
            provider.role_mapping = None
            provider.default_role = 'admin'

            assert _resolve_role_from_mapping(provider, {'groups': ['anyone']}) is None

    def test_mapping_no_match_returns_none(self, app):
        with app.app_context():
            from api.v2.sso import _resolve_role_from_mapping
            from unittest.mock import MagicMock

            provider = MagicMock()
            provider.role_mapping = json.dumps({'admins': 'admin'})
            provider.default_role = 'operator'

            assert _resolve_role_from_mapping(provider, {'groups': ['users']}) is None


# ============================================================
# SSO User Provisioning — _get_or_create_sso_user (#81)
# ============================================================
class TestSSOUserProvisioning:
    """Verify role/userinfo decoupling on SSO login (issue #81)."""

    def _make_provider(self, **kwargs):
        from unittest.mock import MagicMock
        provider = MagicMock()
        provider.id = kwargs.get('id', 1)
        provider.provider_type = kwargs.get('provider_type', 'oauth2')
        provider.auto_create_users = kwargs.get('auto_create_users', True)
        provider.auto_update_users = kwargs.get('auto_update_users', True)
        provider.sync_role_on_login = kwargs.get('sync_role_on_login', False)
        provider.default_role = kwargs.get('default_role', 'viewer')
        provider.role_mapping = kwargs.get('role_mapping', None)
        return provider

    def _ensure_user(self, app, username='sso.alice', role='admin'):
        from models import db, User
        u = User.query.filter_by(username=username).first()
        if u:
            u.role = role
            u.password_hash = '!sso-no-password!'
            db.session.commit()
            return u
        u = User(
            username=username,
            email=f'{username}@example.test',
            full_name='Alice',
            role=role,
            active=True,
            password_hash='!sso-no-password!',
        )
        db.session.add(u)
        db.session.commit()
        return u

    def test_existing_user_role_preserved_when_sync_disabled(self, app):
        """Default behaviour (#81 fix): UI-set role survives SSO re-login."""
        with app.app_context():
            from api.v2.sso import _get_or_create_sso_user
            self._ensure_user(app, 'sso.alice', role='admin')
            provider = self._make_provider(default_role='viewer', sync_role_on_login=False)

            user, err = _get_or_create_sso_user(
                provider, 'sso.alice', 'alice@example.test', 'Alice',
                {'groups': ['users']}
            )
            assert err is None
            assert user.role == 'admin', "Existing UI-set role must NOT be overwritten"

    def test_existing_user_role_synced_via_mapping(self, app):
        """sync_role_on_login=True + matching mapping → role updated."""
        with app.app_context():
            from api.v2.sso import _get_or_create_sso_user
            self._ensure_user(app, 'sso.bob', role='viewer')
            provider = self._make_provider(
                default_role='viewer',
                sync_role_on_login=True,
                role_mapping=json.dumps({'admins': 'admin'}),
            )

            user, err = _get_or_create_sso_user(
                provider, 'sso.bob', 'bob@example.test', 'Bob',
                {'groups': ['admins']}
            )
            assert err is None
            assert user.role == 'admin'

    def test_existing_user_role_kept_when_no_mapping_match(self, app):
        """sync_role_on_login=True but no mapping match → role unchanged
        (NEVER falls back to default_role for existing users — #81)."""
        with app.app_context():
            from api.v2.sso import _get_or_create_sso_user
            self._ensure_user(app, 'sso.carol', role='operator')
            provider = self._make_provider(
                default_role='viewer',
                sync_role_on_login=True,
                role_mapping=json.dumps({'admins': 'admin'}),
            )

            user, err = _get_or_create_sso_user(
                provider, 'sso.carol', 'carol@example.test', 'Carol',
                {'groups': ['users']}
            )
            assert err is None
            assert user.role == 'operator', "default_role must NOT be applied to existing users"

    def test_existing_user_userinfo_synced_without_role(self, app):
        """auto_update_users updates email/name without touching role."""
        with app.app_context():
            from api.v2.sso import _get_or_create_sso_user
            self._ensure_user(app, 'sso.dave', role='admin')
            provider = self._make_provider(
                default_role='viewer',
                auto_update_users=True,
                sync_role_on_login=False,
            )

            user, err = _get_or_create_sso_user(
                provider, 'sso.dave', 'dave.new@example.test', 'Dave Updated',
                {'groups': []}
            )
            assert err is None
            assert user.email == 'dave.new@example.test'
            assert user.full_name == 'Dave Updated'
            assert user.role == 'admin'

    def test_new_user_creation_uses_default_role(self, app):
        """Creation path keeps default_role fallback."""
        with app.app_context():
            from api.v2.sso import _get_or_create_sso_user
            from models import User
            User.query.filter_by(username='sso.new').delete()
            from models import db
            db.session.commit()
            provider = self._make_provider(default_role='operator')

            user, err = _get_or_create_sso_user(
                provider, 'sso.new', 'new@example.test', 'New User',
                {'groups': []}
            )
            assert err is None
            assert user is not None
            assert user.role == 'operator'

    def test_new_sso_user_coexists_with_local_email(self, app):
        """#136 (option A): an SSO login whose email belongs to a *local* account
        creates a distinct SSO account — no refusal, identity is the stable id."""
        with app.app_context():
            from api.v2.sso import _get_or_create_sso_user
            from models import db, User

            shared = 'shared136@example.test'
            for uname in ('local.bob136', 'sso.bob136'):
                User.query.filter_by(username=uname).delete()
            db.session.commit()

            local = User(
                username='local.bob136', email=shared, full_name='Local Bob',
                role='admin', active=True, password_hash='hashed-local-pw',
                auth_source='local',
            )
            db.session.add(local)
            db.session.commit()

            provider = self._make_provider(provider_type='oauth2', default_role='viewer')
            user, err = _get_or_create_sso_user(
                provider, 'sso.bob136', shared, 'SSO Bob', {'sub': 'sub-bob-136', 'groups': []}
            )

            assert err is None
            assert user is not None and user.username == 'sso.bob136'
            assert user.sso_external_id == 'sub-bob-136'
            # Both accounts coexist with the same email.
            assert User.query.filter_by(email=shared).count() == 2

    def test_stable_id_match_survives_username_and_email_change(self, app):
        """Primary match is the stable external id, robust to username/email drift."""
        with app.app_context():
            from api.v2.sso import _get_or_create_sso_user
            from models import db, User

            User.query.filter_by(username='stable.user').delete()
            db.session.commit()
            provider = self._make_provider(provider_type='oauth2', default_role='viewer',
                                           auto_update_users=True)
            u = User(username='stable.user', email='old@example.test', full_name='S',
                     role='operator', active=True, password_hash='!SSO_NO_PASSWORD!',
                     auth_source='oauth2', sso_provider_id=provider.id,
                     sso_external_id='sub-stable-1')
            db.session.add(u)
            db.session.commit()
            uid = u.id

            # IdP now sends a different username AND email, same sub → same account.
            user, err = _get_or_create_sso_user(
                provider, 'renamed.user', 'new@example.test', 'S',
                {'sub': 'sub-stable-1', 'groups': []}
            )
            assert err is None
            assert user is not None and user.id == uid

    def test_tofu_binds_external_id_on_first_login_after_link(self, app):
        """An admin-linked account (no external id yet) gets the stable id bound
        on first SSO login, then matches by it next time."""
        with app.app_context():
            from api.v2.sso import _get_or_create_sso_user
            from models import db, User

            User.query.filter(User.email == 'tofu@example.test').delete()
            db.session.commit()
            provider = self._make_provider(provider_type='oauth2', default_role='viewer')
            linked = User(username='tofu.local', email='tofu@example.test', full_name='T',
                          role='admin', active=True, password_hash='pw',
                          auth_source='oauth2', sso_provider_id=provider.id,
                          sso_external_id=None)
            db.session.add(linked)
            db.session.commit()
            uid = linked.id

            # First SSO login: matched by email (linked), binds the sub.
            user, err = _get_or_create_sso_user(
                provider, 'tofu.sso', 'tofu@example.test', 'T', {'sub': 'sub-tofu', 'groups': []}
            )
            assert err is None and user.id == uid
            assert user.sso_external_id == 'sub-tofu'

    def test_sso_login_adopts_linked_account_by_email(self, app):
        """#138: a linked account is adopted by email even when the SSO username
        differs from the (preserved) local username — no new row, no refusal."""
        with app.app_context():
            from api.v2.sso import _get_or_create_sso_user
            from models import db, User

            email = 'linked136@example.test'
            User.query.filter(User.email == email).delete()
            db.session.commit()

            provider = self._make_provider(provider_type='ldap', default_role='viewer')
            # Admin linked the LOCAL account, keeping its local username 'jdoe.local'.
            linked = User(
                username='jdoe.local', email=email, full_name='J Doe', role='admin',
                active=True, password_hash='hashed-local-pw',
                auth_source='ldap', sso_provider_id=provider.id,
            )
            db.session.add(linked)
            db.session.commit()
            uid = linked.id

            # LDAP sends a different username ('jdoe') — must still adopt by email.
            user, err = _get_or_create_sso_user(
                provider, 'jdoe', email, 'J Doe', {'groups': []}
            )
            assert err is None
            assert user is not None and user.id == uid
            assert user.username == 'jdoe.local'  # username preserved
            assert User.query.filter_by(email=email).count() == 1

    def test_sso_login_email_case_insensitive_adopt(self, app):
        """Linked-account adoption tolerates email case differences."""
        with app.app_context():
            from api.v2.sso import _get_or_create_sso_user
            from models import db, User

            User.query.filter(User.email == 'Case.User@example.test').delete()
            db.session.commit()
            provider = self._make_provider(provider_type='ldap', default_role='viewer')
            linked = User(
                username='case.local', email='Case.User@example.test', full_name='C',
                role='viewer', active=True, password_hash='x',
                auth_source='ldap', sso_provider_id=provider.id,
            )
            db.session.add(linked)
            db.session.commit()
            uid = linked.id

            user, err = _get_or_create_sso_user(
                provider, 'case.sso', 'case.user@example.test', 'C', {'groups': []}
            )
            assert err is None
            assert user is not None and user.id == uid


class TestExternalIdExtraction:
    """_extract_external_id resolves the stable id per protocol (#138)."""

    def _p(self, ptype):
        from unittest.mock import MagicMock
        p = MagicMock(); p.provider_type = ptype; return p

    def test_oauth2_uses_sub(self, app):
        with app.app_context():
            from api.v2.sso.ldap_routes import _extract_external_id
            assert _extract_external_id(self._p('oauth2'), {'sub': 'abc-123', 'email': 'x'}) == 'abc-123'

    def test_saml_persistent_nameid(self, app):
        with app.app_context():
            from api.v2.sso.ldap_routes import _extract_external_id
            ed = {'name_id': 'G-9', 'name_id_format':
                  'urn:oasis:names:tc:SAML:2.0:nameid-format:persistent'}
            assert _extract_external_id(self._p('saml'), ed) == 'G-9'

    def test_saml_transient_nameid_ignored(self, app):
        with app.app_context():
            from api.v2.sso.ldap_routes import _extract_external_id
            ed = {'name_id': 'ephemeral-xyz', 'name_id_format':
                  'urn:oasis:names:tc:SAML:2.0:nameid-format:transient'}
            assert _extract_external_id(self._p('saml'), ed) is None

    def test_ldap_uses_uid_then_dn(self, app):
        with app.app_context():
            from api.v2.sso.ldap_routes import _extract_external_id
            assert _extract_external_id(self._p('ldap'), {'uid': 'uuid-1', 'dn': 'cn=a'}) == 'uuid-1'
            assert _extract_external_id(self._p('ldap'), {'uid': None, 'dn': 'cn=a'}) == 'cn=a'

    def test_missing_id_returns_none(self, app):
        with app.app_context():
            from api.v2.sso.ldap_routes import _extract_external_id
            assert _extract_external_id(self._p('oauth2'), {'email': 'x'}) is None


class TestSamlStableMatch:
    """SAML logins match by persistent NameID across username/email changes."""

    def _make_provider(self, **kw):
        from unittest.mock import MagicMock
        p = MagicMock()
        p.id = kw.get('id', 1); p.provider_type = 'saml'
        p.auto_create_users = True; p.auto_update_users = True
        p.sync_role_on_login = False; p.default_role = 'viewer'; p.role_mapping = None
        return p

    def test_saml_match_by_nameid(self, app):
        with app.app_context():
            from api.v2.sso import _get_or_create_sso_user
            from models import db, User
            User.query.filter_by(username='saml.local').delete(); db.session.commit()
            provider = self._make_provider()
            u = User(username='saml.local', email='s@example.test', full_name='S',
                     role='admin', active=True, password_hash='!SSO_NO_PASSWORD!',
                     auth_source='saml', sso_provider_id=provider.id,
                     sso_external_id='nameid-persistent-1')
            db.session.add(u); db.session.commit(); uid = u.id

            ed = {'name_id': 'nameid-persistent-1',
                  'name_id_format': 'urn:oasis:names:tc:SAML:2.0:nameid-format:persistent',
                  'attributes': {}}
            user, err = _get_or_create_sso_user(
                provider, 'saml.renamed', 'changed@example.test', 'S', ed)
            assert err is None and user.id == uid


# ============================================================
# LDAP Rate Limiting — Lockout helpers
# ============================================================
class TestLDAPRateLimiting:
    """Test LDAP brute-force protection"""

    def test_lockout_check_nonexistent_user(self, app):
        """Non-existent user should not be locked"""
        with app.app_context():
            from api.v2.sso import _check_ldap_lockout
            assert _check_ldap_lockout('nonexistent_user_xyz') is False

    def test_record_failed_attempts_and_lockout(self, app):
        """After 5 failed attempts, user should be locked"""
        with app.app_context():
            from api.v2.sso import (
                _record_ldap_failed_attempt,
                _check_ldap_lockout,
                _clear_ldap_failed_attempts,
            )
            from models import db, User

            # Use the admin user for testing
            user = User.query.filter_by(username='admin').first()
            assert user is not None

            # Clear any existing lockout
            user.failed_logins = 0
            user.locked_until = None
            db.session.commit()

            # Default max attempts is 5
            max_attempts = 5

            # Record failures up to threshold
            for i in range(max_attempts):
                assert _check_ldap_lockout('admin') is False
                _record_ldap_failed_attempt('admin')

            # Should now be locked
            assert _check_ldap_lockout('admin') is True

            # Clear and verify unlocked
            _clear_ldap_failed_attempts('admin')
            assert _check_ldap_lockout('admin') is False

            # Verify user state is clean
            db.session.refresh(user)
            assert user.failed_logins == 0
            assert user.locked_until is None


# ============================================================
# SSO Helper — _parse_json_field
# ============================================================
class TestParseJsonField:
    """Test JSON field parsing (handles string, double-encoded, dict)"""

    def test_parse_none(self, app):
        with app.app_context():
            from api.v2.sso import _parse_json_field
            assert _parse_json_field(None) == {}

    def test_parse_empty_string(self, app):
        with app.app_context():
            from api.v2.sso import _parse_json_field
            assert _parse_json_field('') == {}

    def test_parse_dict(self, app):
        with app.app_context():
            from api.v2.sso import _parse_json_field
            assert _parse_json_field({'a': 1}) == {'a': 1}

    def test_parse_json_string(self, app):
        with app.app_context():
            from api.v2.sso import _parse_json_field
            assert _parse_json_field('{"a": 1}') == {'a': 1}

    def test_parse_double_encoded(self, app):
        with app.app_context():
            from api.v2.sso import _parse_json_field
            assert _parse_json_field('"{\\"a\\": 1}"') == {'a': 1}

    def test_parse_invalid_json(self, app):
        with app.app_context():
            from api.v2.sso import _parse_json_field
            assert _parse_json_field('not json') == {}

    def test_parse_json_array_returns_list(self, app):
        with app.app_context():
            from api.v2.sso import _parse_json_field
            assert _parse_json_field('[1, 2, 3]') == [1, 2, 3]
