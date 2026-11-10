"""The page that asked for a sign-in survives an OAuth2/OIDC or SAML login.

It never travels through the IdP: OAuth2 keeps it in the server session next to
``state``, SAML in the AuthnRequest row; it is used once and revalidated on return.
"""
import re
import uuid
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import pytest

from api.v2.sso import return_path, saml_sp
from models import db, User
from models.sso import SAMLMessageId, SSOProvider, SSOSession
from tests.test_saml_strict_validation import (  # noqa: F401 (fixtures)
    ACS, SP_BASE, _module_provider, _response, idp_signer, provider,
)

DONE = '/login/sso-complete'
REFUSED_FORMS = [
    '//evil.example', '/\\evil.example', 'https://evil.example', '/%2f%2fevil.example',
    '/certificates\r\nSet-Cookie: x=1', '/certificates\n', '/login', '/login/sso-complete',
    '/forgot-password', '/certificates/' + 'a' * 520, '/no-such-page', 'certificates',
    '/certificates?x=é', '',
]


@pytest.mark.parametrize('value', ['/certificates', '/certificates/12?tab=chain', '/ssh/cas',
                                   '/sso', '/users?tab=groups', '/dashboard', '/', '/cas/3#x'])
def test_known_paths_are_accepted(value):
    assert return_path.safe_next(value) == value


@pytest.mark.parametrize('value', REFUSED_FORMS + [None, 42, '/certificates/1/2'])
def test_refused_forms(value):
    assert return_path.safe_next(value) is None


@pytest.mark.parametrize('value', ['//evil.example', '/\\evil.example', '/%2f%2fevil.example',
                                   '/x\r\n', '/login', '/login/sso-complete', '/reset-password/t',
                                   '/' + 'a' * 512])
def test_shape_rules_hold_even_for_a_path_the_list_would_accept(monkeypatch, value):
    monkeypatch.setattr(return_path, '_KNOWN', (re.compile(r'.*', re.S),))
    assert return_path.safe_next('/anything?x=%41') == '/anything?x=%41'
    assert return_path.safe_next(value) is None


def _registry_paths():
    """Module paths and redirect sources of the frontend registry (palette entries excluded)."""
    text = (Path(__file__).resolve().parents[2] / 'frontend/src/navigation/registry.js').read_text()
    modules = text[text.index('const RAW_MODULES'):text.index('export const MODULES')]
    paths = set()
    found = list(re.finditer(r"^  \{ id: '[^']+', path: '([^']+)'(?:, paths: \[([^\]]*)\])?", modules, re.M))
    # Every module entry is read: one written in another shape would be missing on both sides
    assert len(found) == len(re.findall(r"\{\s*id:", modules)), 'a registry module is written in a shape this test cannot read'
    for m in found:
        paths.add(m.group(1))
        paths.update(re.findall(r"'([^']+)'", m.group(2) or ''))
    paths.update(re.findall(r"\{ from: '([^']+)'", text))
    return paths


def test_server_list_matches_the_frontend_registry():
    registry = _registry_paths()
    assert len(registry) > 20
    assert set(return_path.KNOWN_PATHS) == registry


def _location(r):
    assert r.status_code == 302, r.get_data(as_text=True)
    return r.headers['Location']


def _returned_next(location):
    parts = urlsplit(location)
    assert parts.path == DONE, location
    return parse_qs(parts.query).get('next', [None])[0]


# --- OAuth2 / OIDC ---------------------------------------------------------

@pytest.fixture
def oidc(app, monkeypatch):
    from api.v2.sso import login_routes

    with app.app_context():
        others = [(p.id, p.enabled) for p in SSOProvider.query.filter_by(provider_type='oauth2').all()]
        for pid, _ in others:
            db.session.get(SSOProvider, pid).enabled = False
        row = SSOProvider(
            name=f'next-oidc-{uuid.uuid4().hex[:6]}', provider_type='oauth2', enabled=True,
            oauth2_client_id='ucm-client', oauth2_client_secret='secret',
            oauth2_auth_url='https://idp.example/authorize',
            oauth2_token_url='https://idp.example/token',
            oauth2_userinfo_url='https://idp.example/userinfo',
            oauth2_issuer='https://idp.example', id_token_verify=True,
            auto_create_users=True, default_role='viewer',
        )
        db.session.add(row)
        db.session.commit()
        pid = row.id
    sub = f'next-sub-{uuid.uuid4().hex[:8]}'

    class Resp:
        ok = True
        text = ''

        def __init__(self, body):
            self._body = body

        def json(self):
            return self._body

    monkeypatch.setattr(login_routes, 'safe_request_post',
                        lambda *_a, **_k: Resp({'access_token': 'at', 'id_token': 'x.y.z'}))
    monkeypatch.setattr(login_routes, 'safe_request_get',
                        lambda *_a, **_k: Resp({'sub': sub, 'preferred_username': sub}))
    monkeypatch.setattr(login_routes, 'verify_id_token', lambda *_a, **_k: {'sub': sub})
    yield pid
    with app.app_context():
        SSOSession.query.filter_by(provider_id=pid).delete()
        User.query.filter_by(sso_provider_id=pid).delete()
        db.session.delete(db.session.get(SSOProvider, pid))
        for opid, enabled in others:
            db.session.get(SSOProvider, opid).enabled = enabled
        db.session.commit()


def _oidc_start(client, next_value=None):
    query = {} if next_value is None else {'next': next_value}
    location = _location(client.get('/api/v2/sso/login/oauth2', query_string=query))
    params = parse_qs(urlsplit(location).query)
    return location, params['state'][0]


def _oidc_return(client, state):
    return _location(client.get('/api/v2/sso/callback/oauth2', query_string={'state': state, 'code': 'c'}))


def test_oidc_returns_a_known_page(app, oidc):
    client = app.test_client()
    location, state = _oidc_start(client, '/certificates/12?tab=chain')
    # Nothing new goes to the IdP.
    assert 'certificates' not in location and 'next' not in parse_qs(urlsplit(location).query)
    assert _returned_next(_oidc_return(client, state)) == '/certificates/12?tab=chain'


def test_oidc_without_next_lands_as_before(app, oidc):
    client = app.test_client()
    _, state = _oidc_start(client)
    assert _oidc_return(client, state) == DONE


@pytest.mark.parametrize('value', REFUSED_FORMS)
def test_oidc_ignores_a_refused_value(app, oidc, value):
    client = app.test_client()
    _, state = _oidc_start(client, value)
    with client.session_transaction() as s:
        assert 'sso_next' not in s
    assert _oidc_return(client, state) == DONE


def test_oidc_value_is_revalidated_on_return(app, oidc):
    client = app.test_client()
    _, state = _oidc_start(client)
    with client.session_transaction() as s:
        s['sso_next'] = '//evil.example'
    assert _oidc_return(client, state) == DONE


def test_oidc_value_belongs_to_its_own_login(app, oidc):
    client = app.test_client()
    _oidc_start(client, '/certificates')
    # A second login started without a page does not inherit the first one's.
    _, state = _oidc_start(client)
    assert _oidc_return(client, state) == DONE


def test_oidc_value_is_used_once(app, oidc):
    client = app.test_client()
    _, state = _oidc_start(client, '/cas')
    # A failed return spends it: a later return with the same state gets nothing.
    assert _location(client.get('/api/v2/sso/callback/oauth2',
                                query_string={'state': state, 'error': 'access_denied'})).startswith('/login?error=')
    with client.session_transaction() as s:
        s['sso_state'] = state
        s['sso_pkce_verifier'] = 'v'
        s['sso_nonce'] = 'n'
    assert _oidc_return(client, state) == DONE


def test_oidc_bad_state_spends_the_value(app, oidc):
    client = app.test_client()
    _, state = _oidc_start(client, '/cas')
    assert _location(client.get('/api/v2/sso/callback/oauth2',
                                query_string={'state': 'forged', 'code': 'c'})) == '/login?error=invalid_state'
    with client.session_transaction() as s:
        assert 'sso_next' not in s


# --- SAML ------------------------------------------------------------------

def _saml_start(client, next_value=None):
    query = {} if next_value is None else {'next': next_value}
    r = client.get('/api/v2/sso/login/saml', base_url=SP_BASE, query_string=query)
    location = _location(r)
    assert 'SAMLRequest=' in location
    # RelayState stays the library's default: the page never travels through the IdP.
    assert parse_qs(urlsplit(location).query)['RelayState'] == [f'{SP_BASE}/api/v2/sso/login/saml']
    return client.get_cookie(saml_sp.REQUEST_COOKIE, domain='ucm.example.test', path=ACS).value


def _saml_return(app, request_id, idp_signer):
    # A fresh browser context holding only the cross-site request cookie: the
    # SameSite=Lax session cookie does not come back on the IdP's POST.
    client = app.test_client()
    client.set_cookie(saml_sp.REQUEST_COOKIE, request_id, domain='ucm.example.test', path=ACS)
    r = client.post(ACS, base_url=SP_BASE,
                    data={'SAMLResponse': _response(idp_signer, in_response_to=request_id)})
    return _location(r)


def test_saml_returns_a_known_page(app, provider, idp_signer):
    request_id = _saml_start(app.test_client(), '/ssh/certificates?x=1')
    assert _returned_next(_saml_return(app, request_id, idp_signer)) == '/ssh/certificates?x=1'


def test_saml_without_next_lands_as_before(app, provider, idp_signer):
    request_id = _saml_start(app.test_client())
    assert _saml_return(app, request_id, idp_signer) == DONE


@pytest.mark.parametrize('value', REFUSED_FORMS)
def test_saml_ignores_a_refused_value(app, provider, idp_signer, value):
    request_id = _saml_start(app.test_client(), value)
    with app.app_context():
        row = SAMLMessageId.query.filter_by(kind=SAMLMessageId.KIND_REQUEST, message_id=request_id).one()
        assert row.next_path is None
    assert _saml_return(app, request_id, idp_signer) == DONE


def test_saml_value_is_revalidated_on_return(app, provider, idp_signer):
    request_id = _saml_start(app.test_client())
    with app.app_context():
        SAMLMessageId.query.filter_by(kind=SAMLMessageId.KIND_REQUEST, message_id=request_id).one() \
            .next_path = '//evil.example'
        db.session.commit()
    assert _saml_return(app, request_id, idp_signer) == DONE


def test_saml_value_belongs_to_its_own_request(app, provider, idp_signer):
    client = app.test_client()
    first = _saml_start(client, '/certificates')
    second = _saml_start(client)
    assert _saml_return(app, second, idp_signer) == DONE
    assert _returned_next(_saml_return(app, first, idp_signer)) == '/certificates'


def test_saml_value_is_used_once(app, provider, idp_signer):
    request_id = _saml_start(app.test_client(), '/cas')
    assert _returned_next(_saml_return(app, request_id, idp_signer)) == '/cas'
    assert _saml_return(app, request_id, idp_signer) == '/login?error=saml_login_expired'
    with app.app_context():
        assert SAMLMessageId.query.filter_by(kind=SAMLMessageId.KIND_REQUEST,
                                             message_id=request_id).count() == 0
