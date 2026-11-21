"""What the OAuth2 presets of the provider screen give works: an Entra provider saved with
``{tenant}`` still in an URL is refused, and a GitHub account (UserInfo ``id``, no ``sub``,
no ID token) is recognised by its numeric id, never by its login."""
from tests.sso_identity_support import step_aside, users_of
import uuid

import pytest

from models import db, User
from models.sso import SSOProvider, SSOSession

ENTRA = 'https://login.microsoftonline.com/{tenant}'


def _entra_payload(**overrides):
    payload = {
        'name': f'entra-{uuid.uuid4().hex[:6]}', 'provider_type': 'oauth2', 'enabled': False,
        'oauth2_client_id': 'client-example',
        'oauth2_auth_url': 'https://login.microsoftonline.com/tenant-example/oauth2/v2.0/authorize',
        'oauth2_token_url': 'https://login.microsoftonline.com/tenant-example/oauth2/v2.0/token',
        'oauth2_userinfo_url': 'https://graph.microsoft.com/oidc/userinfo',
        'oauth2_issuer': 'https://login.microsoftonline.com/tenant-example/v2.0',
    }
    payload.update(overrides)
    return payload


@pytest.fixture
def no_oauth2(app):
    with app.app_context():
        aside = step_aside('oauth2')
    yield
    with app.app_context():
        for row in SSOProvider.query.filter(SSOProvider.name.like('entra-%')).all():
            db.session.delete(row)
        aside.back()
        db.session.commit()


@pytest.mark.parametrize('field,value', [
    ('oauth2_auth_url', f'{ENTRA}/oauth2/v2.0/authorize'),
    ('oauth2_token_url', f'{ENTRA}/oauth2/v2.0/token'),
    ('oauth2_issuer', f'{ENTRA}/v2.0'),
])
def test_a_tenant_placeholder_left_in_is_refused_at_creation(auth_client, no_oauth2, field, value):
    response = auth_client.post('/api/v2/sso/providers', json=_entra_payload(**{field: value}))
    assert response.status_code == 400
    assert field in response.get_json()['message']
    assert '{tenant}' in response.get_json()['message']


def test_a_tenant_placeholder_left_in_is_refused_at_update(app, auth_client, no_oauth2):
    created = auth_client.post('/api/v2/sso/providers', json=_entra_payload())
    assert created.status_code == 200
    pid = created.get_json()['data']['id']
    response = auth_client.put(f'/api/v2/sso/providers/{pid}',
                               json={'oauth2_issuer': f'{ENTRA}/v2.0'})
    assert response.status_code == 400
    assert '{tenant}' in response.get_json()['message']
    with app.app_context():
        assert db.session.get(SSOProvider, pid).oauth2_issuer.endswith('/tenant-example/v2.0')


class _Resp:
    ok = True
    text = ''

    def __init__(self, body):
        self._body = body

    def json(self):
        return self._body


@pytest.fixture
def github(app, monkeypatch):
    """A provider as the GitHub preset saves it: no ID token, verification off."""
    from api.v2.sso import login_routes

    with app.app_context():
        others = step_aside('oauth2')
        row = SSOProvider(
            name=f'github-{uuid.uuid4().hex[:6]}', provider_type='oauth2', enabled=True,
            oauth2_client_id='client-example', oauth2_client_secret='secret-example',
            oauth2_auth_url='https://github.com/login/oauth/authorize',
            oauth2_token_url='https://github.com/login/oauth/access_token',
            oauth2_userinfo_url='https://api.github.com/user',
            id_token_verify=False, auto_create_users=True, default_role='viewer',
            attribute_mapping='{"login": "username"}',
        )
        db.session.add(row)
        db.session.commit()
        pid = row.id

    state = {}
    monkeypatch.setattr(login_routes, 'safe_request_post',
                        lambda *_a, **_k: _Resp({'access_token': 'gho_example', 'scope': 'read:user'}))
    monkeypatch.setattr(login_routes, 'safe_request_get', lambda *_a, **_k: _Resp(state['userinfo']))

    def login(userinfo):
        state['userinfo'] = dict(userinfo)
        client = app.test_client()
        with client.session_transaction() as s:
            s['sso_state'] = 'st'
            s['sso_provider_id'] = pid
            s['sso_pkce_verifier'] = 'v'
            s['sso_nonce'] = 'n'
        r = client.get('/api/v2/sso/callback/oauth2?state=st&code=c')
        assert r.status_code == 302
        return r.headers['Location']

    login.pid = pid
    yield login
    with app.app_context():
        SSOSession.query.filter_by(provider_id=pid).delete()
        for user in users_of(pid).all():
            from api.v2.users.crud import _purge_user_dependencies
            _purge_user_dependencies(user.id)
            db.session.delete(user)
        db.session.delete(db.session.get(SSOProvider, pid))
        others.back()
        db.session.commit()


def test_a_github_account_is_bound_by_its_numeric_id(app, github):
    """GitHub's /user has ``id`` and no ``sub``: the login changes hands, the id does not."""
    first = {'id': 583231, 'login': 'octo-example', 'name': 'Octo Example', 'email': None}
    assert github(first) == '/login/sso-complete'
    with app.app_context():
        user = users_of(github.pid).one()
        assert user.username == 'octo-example'
        assert [r.external_id for r in user.sso_identities] == ['583231']
        session_ids = [s.session_id for s in SSOSession.query.filter_by(provider_id=github.pid)]
        assert session_ids == ['583231']
        user_id = user.id

    # Renamed at GitHub: the same account opens, by its id
    assert github(dict(first, login='octo-renamed')) == '/login/sso-complete'
    with app.app_context():
        assert [u.id for u in users_of(github.pid).all()] == [user_id]
        assert User.query.filter_by(username='octo-renamed').first() is None


def test_another_github_account_with_a_former_login_is_not_let_in(app, github):
    """A login freed at GitHub and taken by someone else does not open its former owner's account."""
    assert github({'id': 583231, 'login': 'octo-example'}) == '/login/sso-complete'
    location = github({'id': 999001, 'login': 'octo-example'})
    assert location != '/login/sso-complete'
    with app.app_context():
        assert [r.external_id for u in users_of(github.pid) for r in u.sso_identities] == ['583231']


def test_sub_wins_over_id_when_both_are_sent(app, github):
    assert github({'sub': 'stable-sub', 'id': 7, 'login': 'both-example'}) == '/login/sso-complete'
    with app.app_context():
        assert [r.external_id for u in users_of(github.pid) for r in u.sso_identities] == ['stable-sub']


def _github_token_endpoint(sent):
    """GitHub answers form-encoded unless the client asks for JSON in Accept."""
    import requests

    def post(*_a, **kwargs):
        sent.append(kwargs.get('headers'))
        response = requests.Response()
        response.status_code = 200
        if 'application/json' in ((kwargs.get('headers') or {}).get('Accept') or ''):
            response._content = b'{"access_token": "gho_example", "scope": "read:user", "token_type": "bearer"}'
            response.headers['Content-Type'] = 'application/json'
        else:
            response._content = b'access_token=gho_example&scope=read%3Auser&token_type=bearer'
            response.headers['Content-Type'] = 'application/x-www-form-urlencoded'
        return response
    return post


def test_github_signs_in_against_its_real_token_response(app, github, monkeypatch):
    """The token request asks for JSON (RFC 6749 section 5.1), which GitHub only sends on Accept."""
    from api.v2.sso import login_routes

    sent = []
    monkeypatch.setattr(login_routes, 'safe_request_post', _github_token_endpoint(sent))
    assert github({'id': 583231, 'login': 'octo-example'}) == '/login/sso-complete'
    assert sent and sent[0]['Accept'] == 'application/json'
    with app.app_context():
        assert users_of(github.pid).count() == 1
