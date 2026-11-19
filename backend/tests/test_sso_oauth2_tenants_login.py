"""Sign-in through a multi-tenant Entra provider, the real ID token verification against a simulated
authority: an identity belongs to its tenant (same ``sub`` in two tenants = two accounts), a tenant
taken off the list closes its accounts only, and the refusal says why in the audit and in the
provider's sign-in test. GUIDs invented."""
import time
import uuid

import pytest
from cryptography.hazmat.primitives.asymmetric import rsa

from models import db, User, UserSSOIdentity
from models.audit_log import AuditLog
from models.sso import SSOProvider, SSOSession
from tests.sso_identity_support import step_aside, users_of
from tests.test_oidc_id_token import _Response, _rsa_jwk, _token

AUTHORITY = 'https://idp.example/organizations/v2.0'
TEMPLATE = 'https://idp.example/{tenantid}/v2.0'
JWKS_URL = 'https://idp.example/common/discovery/v2.0/keys'
TENANT_A = '0f1e2d3c-4b5a-4968-8778-a6b5c4d3e2f1'
TENANT_B = '1a2b3c4d-5e6f-4a7b-8c9d-0e1f2a3b4c5d'
KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)
OK = '/login/sso-complete'


def _cleanup(pid):
    from api.v2.users.crud import _purge_user_dependencies
    names = [u.username for u in users_of(pid).all()]
    for (user_id,) in User.query.filter(User.username.in_(names)).with_entities(User.id).all():
        _purge_user_dependencies(user_id)
    User.query.filter(User.username.in_(names)).delete(synchronize_session=False)
    db.session.commit()


@pytest.fixture
def entra(app, monkeypatch):
    from api.v2.sso import login_routes
    from services.oidc_id_token import clear_oidc_cache

    with app.app_context():
        others = step_aside('oauth2')
        row = SSOProvider(
            name=f'entra-mt-{uuid.uuid4().hex[:6]}', provider_type='oauth2', enabled=True,
            oauth2_client_id='ucm-client', oauth2_client_secret='secret',
            oauth2_auth_url='https://idp.example/organizations/oauth2/v2.0/authorize',
            oauth2_token_url='https://idp.example/organizations/oauth2/v2.0/token',
            oauth2_userinfo_url='https://idp.example/oidc/userinfo', oauth2_issuer=AUTHORITY,
            oauth2_tenants=f'["{TENANT_A}", "{TENANT_B}"]', id_token_verify=True,
            auto_create_users=True, default_role='viewer')
        db.session.add(row)
        db.session.commit()
        pid = row.id
    clear_oidc_cache()

    state = {}
    documents = {f'{AUTHORITY}/.well-known/openid-configuration': {'issuer': TEMPLATE, 'jwks_uri': JWKS_URL},
                 JWKS_URL: {'keys': [dict(_rsa_jwk(KEY), issuer=TEMPLATE)]}}
    monkeypatch.setattr('services.oidc_id_token.safe_request_get',
                        lambda url, **_k: _Response(documents[url]))
    monkeypatch.setattr(login_routes, 'safe_request_post', lambda *_a, **_k: _Response(
        {'access_token': 'at', 'id_token': _token(KEY, state['claims'])}))
    monkeypatch.setattr(login_routes, 'safe_request_get', lambda *_a, **_k: _Response(state['userinfo']))

    def claims(tid, sub):
        now = int(time.time())
        return {'iss': TEMPLATE.replace('{tenantid}', tid), 'tid': tid, 'aud': 'ucm-client',
                'sub': sub, 'exp': now + 300, 'iat': now, 'nonce': 'n'}

    def login(tid, sub, username):
        state['claims'] = claims(tid, sub)
        state['userinfo'] = {'sub': sub, 'preferred_username': username,
                             'email': f'{username}@{tid[:8]}.example'}
        client = app.test_client()
        with client.session_transaction() as s:
            s.update(sso_state='st', sso_provider_id=pid, sso_pkce_verifier='v', sso_nonce='n')
        r = client.get('/api/v2/sso/callback/oauth2?state=st&code=c')
        assert r.status_code == 302
        return r.headers['Location']

    def sign_in(tid, sub, username):
        """What the provider's sign-in test reads: the same function as the login."""
        state['claims'] = claims(tid, sub)
        state['userinfo'] = {'sub': sub, 'preferred_username': username}
        with app.test_request_context('/api/v2/sso/callback/oauth2'):
            return login_routes.oidc_sign_in(db.session.get(SSOProvider, pid), 'c', 'v', 'n')

    def configure(**fields):
        with app.app_context():
            provider = db.session.get(SSOProvider, pid)
            for key, value in fields.items():
                setattr(provider, key, value)
            db.session.commit()
        clear_oidc_cache()

    def ids_of(username):
        with app.app_context():
            user = User.query.filter_by(username=username).first()
            return [r.external_id for r in user.sso_identities] if user else None

    login.pid, login.sign_in, login.configure, login.ids_of = pid, sign_in, configure, ids_of
    with app.app_context():
        yield login
    with app.app_context():
        db.session.rollback()
        SSOSession.query.filter_by(provider_id=pid).delete()
        _cleanup(pid)
        db.session.delete(db.session.get(SSOProvider, pid))
        others.back()
        db.session.commit()
    clear_oidc_cache()


def test_the_same_subject_in_two_tenants_is_two_accounts(entra):
    assert entra(TENANT_A, 'same-sub', 'mt-alice').endswith(OK)
    assert entra(TENANT_B, 'same-sub', 'mt-bob').endswith(OK)
    assert entra.ids_of('mt-alice') == [f'{TENANT_A}/same-sub']
    assert entra.ids_of('mt-bob') == [f'{TENANT_B}/same-sub']
    assert entra(TENANT_A, 'same-sub', 'mt-alice').endswith(OK)
    sessions = {s.session_id for s in SSOSession.query.filter_by(provider_id=entra.pid)}
    assert sessions == {f'{TENANT_A}/same-sub', f'{TENANT_B}/same-sub'}


def test_an_account_of_tenant_a_does_not_open_from_tenant_b(entra):
    assert entra(TENANT_A, 'sub-1', 'mt-carol').endswith(OK)
    location = entra(TENANT_B, 'sub-1', 'mt-carol')
    assert not location.endswith(OK)
    assert entra.ids_of('mt-carol') == [f'{TENANT_A}/sub-1']
    assert UserSSOIdentity.query.filter_by(provider_id=entra.pid).count() == 1


def test_a_removed_tenant_closes_its_accounts_only(entra):
    assert entra(TENANT_A, 'sub-a', 'mt-dave').endswith(OK)
    assert entra(TENANT_B, 'sub-b', 'mt-erin').endswith(OK)
    entra.configure(oauth2_tenants=f'["{TENANT_A}"]')
    assert entra(TENANT_B, 'sub-b', 'mt-erin').endswith('error=invalid_credentials')
    assert entra(TENANT_A, 'sub-a', 'mt-dave').endswith(OK)
    detail = AuditLog.query.filter(AuditLog.resource_id == str(entra.pid),
                                   AuditLog.action == 'login_failure').order_by(AuditLog.id.desc()).first()
    assert f'tenant {TENANT_B} is not accepted' in detail.details


def test_the_sign_in_test_reads_the_reason_and_the_tenant_scoped_id(entra):
    from api.v2.sso.ldap_routes import _extract_external_id
    identity, refusal = entra.sign_in(TENANT_A, 'sub-t', 'mt-test')
    assert refusal is None
    assert _extract_external_id(db.session.get(SSOProvider, entra.pid), identity.external_data) \
        == f'{TENANT_A}/sub-t'
    entra.configure(oauth2_tenants=f'["{TENANT_B}"]')
    identity, refusal = entra.sign_in(TENANT_A, 'sub-t', 'mt-test')
    assert identity is None and refusal.code == 'invalid_credentials'
    assert f'tenant {TENANT_A} is not accepted' in refusal.reason


def test_a_tenant_claimed_by_userinfo_is_not_the_one_read(entra):
    """The tenant of the identity is the verified ``tid``, never one UserInfo names."""
    from api.v2.sso.helpers import OIDC_TENANT_KEY
    from api.v2.sso import login_routes
    real_get = login_routes.safe_request_get
    login_routes.safe_request_get = lambda *_a, **_k: _Response(
        {'sub': 'sub-u', 'preferred_username': 'mt-frank', OIDC_TENANT_KEY: TENANT_B})
    try:
        identity, refusal = entra.sign_in(TENANT_A, 'sub-u', 'mt-frank')
    finally:
        login_routes.safe_request_get = real_get
    assert refusal is None and identity.external_data[OIDC_TENANT_KEY] == TENANT_A


def test_compatibility_mode_with_tenants_refuses_the_sign_in(entra):
    entra.configure(id_token_verify=False)
    identity, refusal = entra.sign_in(TENANT_A, 'sub-c', 'mt-gina')
    assert identity is None and 'require ID token verification' in refusal.reason


def test_compatibility_mode_with_tenants_refuses_even_without_an_id_token(entra):
    """Without an ID token the identity would rest on UserInfo alone, which names no tenant."""
    from api.v2.sso import login_routes
    entra.configure(id_token_verify=False)
    real_post = login_routes.safe_request_post
    login_routes.safe_request_post = lambda *_a, **_k: _Response({'access_token': 'at'})
    try:
        identity, refusal = entra.sign_in(TENANT_A, 'sub-n', 'mt-hugo')
    finally:
        login_routes.safe_request_post = real_post
    assert identity is None and 'require ID token verification' in refusal.reason


def test_a_single_tenant_provider_keeps_the_bare_subject(entra):
    from api.v2.sso.helpers import OIDC_TENANT_KEY
    from api.v2.sso.ldap_routes import _extract_external_id
    entra.configure(oauth2_tenants=None)
    provider = db.session.get(SSOProvider, entra.pid)
    assert _extract_external_id(provider, {'sub': 'bare', OIDC_TENANT_KEY: TENANT_A}) == 'bare'
