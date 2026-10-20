"""SSO provider secrets are shown in clear only to callers holding admin:system."""
import json
import uuid

import pytest

from models import db
from models.sso import SSOProvider

OAUTH_SECRET = 'oauth-secret-Zq81'
LDAP_PASSWORD = 'ldap-bind-pw-Xk42'


def _login(app, username):
    client = app.test_client()
    r = client.post('/api/v2/auth/login',
                    data=json.dumps({'username': username, 'password': 'TestPass123!'}),
                    content_type='application/json')
    assert r.status_code == 200, r.data
    return client


def _user_with_role(app, create_user, monkeypatch, base_role, permissions):
    """A user of base_role plus a custom role granting `permissions`.

    Stock UCM keeps read:sso and admin:system out of custom roles, so the
    grantable set is widened here to exercise the route's own check.
    """
    import auth.permissions as perms
    monkeypatch.setattr(perms, 'CUSTOM_ROLE_GRANTABLE_PERMISSIONS',
                        list(perms.CUSTOM_ROLE_GRANTABLE_PERMISSIONS) + permissions)
    from models import User
    from models.rbac import CustomRole
    n = uuid.uuid4().hex[:8]
    user = create_user(username=f'sso_sec_{n}', role=base_role)
    with app.app_context():
        role = CustomRole(name=f'sso-secrets-{n}', permissions=permissions)
        db.session.add(role)
        db.session.flush()
        db.session.get(User, user['id']).custom_role_id = role.id
        db.session.commit()
    return _login(app, user['username'])


@pytest.fixture
def providers(app):
    ids = {}
    with app.app_context():
        n = uuid.uuid4().hex[:8]
        oauth = SSOProvider(name=f'oauth-{n}', provider_type='oauth2',
                            oauth2_client_id='cid', enabled=False)
        oauth.oauth2_client_secret = OAUTH_SECRET
        ldap = SSOProvider(name=f'ldap-{n}', provider_type='ldap',
                           ldap_server='ldap.example.test', enabled=False)
        ldap.ldap_bind_password = LDAP_PASSWORD
        db.session.add_all([oauth, ldap])
        db.session.commit()
        ids = {'oauth2': oauth.id, 'ldap': ldap.id}
    yield ids
    with app.app_context():
        for pid in ids.values():
            row = db.session.get(SSOProvider, pid)
            if row:
                db.session.delete(row)
        db.session.commit()


def _get(client, pid, query=''):
    return client.get(f'/api/v2/sso/providers/{pid}{query}')


def _data(r):
    return r.get_json()['data']


SECRET_FIELD = {'oauth2': 'oauth2_client_secret', 'ldap': 'ldap_bind_password'}
SECRET_VALUE = {'oauth2': OAUTH_SECRET, 'ldap': LDAP_PASSWORD}


class TestIncludeSecrets:
    @pytest.mark.parametrize('kind', ['oauth2', 'ldap'])
    def test_admin_gets_clear_secret(self, auth_client, providers, kind):
        r = _get(auth_client, providers[kind], '?include_secrets=true')
        assert r.status_code == 200
        assert _data(r)[SECRET_FIELD[kind]] == SECRET_VALUE[kind]

    @pytest.mark.parametrize('kind', ['oauth2', 'ldap'])
    @pytest.mark.parametrize('query', ['', '?include_secrets=false', '?include_secrets=1',
                                       '?include_secrets=True'])
    def test_secret_is_masked_without_the_flag(self, auth_client, providers, kind, query):
        r = _get(auth_client, providers[kind], query)
        assert r.status_code == 200
        assert _data(r)[SECRET_FIELD[kind]] == '***'
        assert SECRET_VALUE[kind] not in r.get_data(as_text=True)

    @pytest.mark.parametrize('kind', ['oauth2', 'ldap'])
    def test_operator_with_read_sso_is_refused(self, app, create_user, monkeypatch, providers, kind):
        op = _user_with_role(app, create_user, monkeypatch, 'operator', ['read:sso'])
        r = _get(op, providers[kind], '?include_secrets=true')
        assert r.status_code == 403
        assert 'Secrets available to administrators only' in r.get_data(as_text=True)
        assert SECRET_VALUE[kind] not in r.get_data(as_text=True)
        ok = _get(op, providers[kind])
        assert ok.status_code == 200
        assert _data(ok)[SECRET_FIELD[kind]] == '***'

    def test_custom_role_with_admin_system_gets_secret(self, app, create_user, monkeypatch, providers):
        c = _user_with_role(app, create_user, monkeypatch, 'viewer', ['read:sso', 'admin:system'])
        r = _get(c, providers['oauth2'], '?include_secrets=true')
        assert r.status_code == 200
        assert _data(r)['oauth2_client_secret'] == OAUTH_SECRET

    def test_user_without_read_sso_is_refused_either_way(self, app, create_user, providers):
        name = f'sso_nosso_{uuid.uuid4().hex[:6]}'
        create_user(username=name, role='viewer')
        viewer = _login(app, name)
        for q in ('', '?include_secrets=true'):
            assert _get(viewer, providers['oauth2'], q).status_code == 403


class TestListAndModel:
    def test_list_never_exposes_a_secret(self, auth_client, providers):
        r = auth_client.get('/api/v2/sso/providers')
        assert r.status_code == 200
        body = r.get_data(as_text=True)
        assert OAUTH_SECRET not in body and LDAP_PASSWORD not in body

    def test_secrets_are_encrypted_at_rest_and_roundtrip(self, app, providers):
        with app.app_context():
            o = db.session.get(SSOProvider, providers['oauth2'])
            l = db.session.get(SSOProvider, providers['ldap'])
            assert o._oauth2_client_secret and o._oauth2_client_secret != OAUTH_SECRET
            assert l._ldap_bind_password and l._ldap_bind_password != LDAP_PASSWORD
            assert o.oauth2_client_secret == OAUTH_SECRET
            assert l.ldap_bind_password == LDAP_PASSWORD
            assert o.to_dict()['oauth2_client_secret'] == '***'
            assert l.to_dict()['ldap_bind_password'] == '***'
            assert o.to_dict(include_secrets=True)['oauth2_client_secret'] == OAUTH_SECRET
            assert l.to_dict(include_secrets=True)['ldap_bind_password'] == LDAP_PASSWORD
