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

    def claims(tid, sub, **extra):
        now = int(time.time())
        return {'iss': TEMPLATE.replace('{tenantid}', tid), 'tid': tid, 'aud': 'ucm-client',
                'sub': sub, 'exp': now + 300, 'iat': now, 'nonce': 'n', **extra}

    def login(tid, sub, username, email=None, **extra):
        state['claims'] = claims(tid, sub, **extra)
        state['userinfo'] = {'sub': sub, 'preferred_username': username,
                             'email': email or f'{username}@{tid[:8]}.example'}
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


def _attached(pid, username, email, **row):
    """An account an administrator attached to the provider, not bound yet; ``row`` sets the
    attachment's columns (its expected tenant)."""
    user = User(username=username, email=email, role='admin', active=True,
                password_hash='!SSO_NO_PASSWORD!')
    user.sso_identities.append(UserSSOIdentity(provider_id=pid, **row))
    db.session.add(user)
    db.session.commit()


def test_an_attachment_without_a_tenant_is_not_adopted_by_e_mail(entra):
    """Another listed tenant's administrator chooses the e-mail of its users: no adoption by it."""
    _attached(entra.pid, 'mt-boss', 'boss@corp.example')
    location = entra(TENANT_B, 'sub-x', 'mt-intruder', email='boss@corp.example')
    assert not location.endswith(OK) and 'sso_email_conflict' in location
    assert entra.ids_of('mt-boss') == [None]
    assert entra.ids_of('mt-intruder') is None


def test_an_attachment_without_a_tenant_is_not_adopted_by_name(entra):
    _attached(entra.pid, 'mt-boss2', 'boss2@corp.example')
    location = entra(TENANT_B, 'sub-y', 'mt-boss2')
    assert not location.endswith(OK) and 'sso_username_conflict' in location
    assert entra.ids_of('mt-boss2') == [None]


def test_an_attachment_is_adopted_from_its_expected_tenant_only(entra):
    _attached(entra.pid, 'mt-chief', 'chief@corp.example', expected_tenant=TENANT_A)
    location = entra(TENANT_B, 'sub-b', 'mt-other', email='chief@corp.example')
    assert 'sso_email_conflict' in location
    assert entra.ids_of('mt-chief') == [None] and entra.ids_of('mt-other') is None
    detail = AuditLog.query.filter(AuditLog.action == 'login_failure').order_by(AuditLog.id.desc()).first()
    assert f'it expects tenant {TENANT_A}' in detail.details
    assert entra(TENANT_A, 'sub-a', 'mt-other', email='chief@corp.example').endswith(OK)
    assert entra.ids_of('mt-chief') == [f'{TENANT_A}/sub-a'] and entra.ids_of('mt-other') is None


def test_an_attachment_is_adopted_by_name_from_its_expected_tenant_only(entra):
    _attached(entra.pid, 'mt-chief2', 'chief2@corp.example', expected_tenant=TENANT_A)
    assert 'sso_username_conflict' in entra(TENANT_B, 'sub-b', 'mt-chief2')
    assert entra.ids_of('mt-chief2') == [None]
    assert entra(TENANT_A, 'sub-a', 'mt-chief2').endswith(OK)
    assert entra.ids_of('mt-chief2') == [f'{TENANT_A}/sub-a']


def test_an_expected_tenant_taken_off_the_list_adopts_nothing(entra):
    """Read by the account resolution itself: the token check refuses that tenant first."""
    from api.v2.sso.helpers import OIDC_TENANT_KEY
    from api.v2.sso.ldap_routes import _resolve_sso_account
    _attached(entra.pid, 'mt-gone', 'gone@corp.example', expected_tenant=TENANT_B)
    identity = {'sub': 'sub-g', OIDC_TENANT_KEY: TENANT_B}
    provider = db.session.get(SSOProvider, entra.pid)
    assert _resolve_sso_account(provider, 'mt-gone', 'gone@corp.example', identity)[0] is not None
    entra.configure(oauth2_tenants=f'["{TENANT_A}"]')
    db.session.expire_all()
    provider = db.session.get(SSOProvider, entra.pid)
    user, row, _rebind, conflict, owner = _resolve_sso_account(
        provider, 'mt-gone', 'gone@corp.example', identity)
    assert user is None and row is None and conflict.username == 'mt-gone'
    assert owner.username == 'mt-gone'


def test_a_legacy_account_is_not_taken_by_name(entra):
    """An account without row nor password is claimable by name by a single-issuer provider only."""
    db.session.add(User(username='mt-legacy', email='legacy@corp.example', role='admin', active=True,
                        password_hash='!SSO_NO_PASSWORD!', force_password_change=False))
    db.session.commit()
    try:
        assert 'sso_username_conflict' in entra(TENANT_A, 'sub-l', 'mt-legacy')
        assert entra.ids_of('mt-legacy') == []
    finally:
        User.query.filter_by(username='mt-legacy').delete()
        db.session.commit()


def _identity(username):
    db.session.expire_all()
    return User.query.filter_by(username=username).one().sso_identities[0]


@pytest.fixture
def plain(entra):
    """Makes local accounts, removed after the test whether a provider was attached or not."""
    from api.v2.users.crud import _purge_user_dependencies
    made = []

    def make(username):
        db.session.add(User(username=username, email=f'{username}@corp.example', role='viewer',
                            active=True, password_hash='x'))
        db.session.commit()
        made.append(username)
        return User.query.filter_by(username=username).one().id
    yield make
    db.session.rollback()
    for user in User.query.filter(User.username.in_(made)).all():
        _purge_user_dependencies(user.id)
        db.session.delete(user)
    db.session.commit()


@pytest.mark.parametrize('tenant', [TENANT_B.upper(), None], ids=['listed', 'none'])
def test_attaching_sets_the_expected_tenant_from_the_list(entra, auth_client, plain, tenant):
    uid = plain('mt-attach')
    body = {'provider_id': entra.pid} if tenant is None else {'provider_id': entra.pid, 'expected_tenant': tenant}
    r = auth_client.post(f'/api/v2/users/{uid}/sso-identities', json=body)
    assert r.status_code == 201, r.get_json()
    assert _identity('mt-attach').expected_tenant == (tenant.lower() if tenant else None)
    assert r.get_json()['data']['sso_identities'][0]['expected_tenant'] == (tenant.lower() if tenant else None)


@pytest.mark.parametrize('tenant', ['9188040d-6c67-4c5b-b112-36a304b66dad', 'common', 42],
                         ids=['unlisted', 'word', 'number'])
def test_attaching_refuses_a_tenant_off_the_list(entra, auth_client, plain, tenant):
    uid = plain('mt-attach2')
    r = auth_client.post(f'/api/v2/users/{uid}/sso-identities',
                         json={'provider_id': entra.pid, 'expected_tenant': tenant})
    assert r.status_code == 400
    db.session.expire_all()
    assert User.query.get(uid).sso_identities == []


def test_an_expected_tenant_needs_a_provider_with_tenants(entra, auth_client, plain):
    entra.configure(oauth2_tenants=None)
    uid = plain('mt-attach3')
    r = auth_client.post(f'/api/v2/users/{uid}/sso-identities',
                         json={'provider_id': entra.pid, 'expected_tenant': TENANT_A})
    assert r.status_code == 400 and 'accepted tenants' in r.get_json()['message']


def test_a_reset_keeps_the_former_tenant_and_takes_another_listed_one(entra, auth_client):
    assert entra(TENANT_A, 'sub-r', 'mt-reset').endswith(OK)
    row = _identity('mt-reset')
    uid, rid = row.user_id, row.id
    reset = f'/api/v2/users/{uid}/sso-identities/{rid}/reset'
    assert auth_client.post(reset).status_code == 200
    assert (_identity('mt-reset').external_id, _identity('mt-reset').expected_tenant) == (None, TENANT_A)
    # From another tenant the same name adopts nothing; from the former one it binds again
    assert 'sso_username_conflict' in entra(TENANT_B, 'sub-r', 'mt-reset')
    assert entra(TENANT_A, 'sub-r2', 'mt-reset').endswith(OK)
    assert _identity('mt-reset').external_id == f'{TENANT_A}/sub-r2'
    r = auth_client.post(reset, json={'expected_tenant': TENANT_B})
    assert r.status_code == 200 and _identity('mt-reset').expected_tenant == TENANT_B
    assert auth_client.post(reset, json={'expected_tenant': '9188040d-6c67-4c5b-b112-36a304b66dad'}) \
        .status_code == 400
    assert _identity('mt-reset').expected_tenant == TENANT_B


def test_a_reset_of_a_former_tenant_taken_off_the_list_sets_none(entra, auth_client):
    assert entra(TENANT_B, 'sub-o', 'mt-reset2').endswith(OK)
    row = _identity('mt-reset2')
    entra.configure(oauth2_tenants=f'["{TENANT_A}"]')
    assert auth_client.post(f'/api/v2/users/{row.user_id}/sso-identities/{row.id}/reset').status_code == 200
    assert (_identity('mt-reset2').external_id, _identity('mt-reset2').expected_tenant) == (None, None)


def _role_of(username):
    db.session.expire_all()
    return User.query.filter_by(username=username).one().role


def test_role_claims_are_read_from_the_honoured_tenants_only(entra):
    """Each listed tenant's administrators assign the app roles of their users."""
    entra.configure(role_mapping='{"UCM.Admin": "admin"}', default_role='viewer',
                    oauth2_role_tenants=f'["{TENANT_A}"]')
    assert entra(TENANT_A, 'sub-ra', 'mt-roles-a', roles=['UCM.Admin']).endswith(OK)
    assert _role_of('mt-roles-a') == 'admin'
    assert entra(TENANT_B, 'sub-rb', 'mt-roles-b', roles=['UCM.Admin']).endswith(OK)
    assert _role_of('mt-roles-b') == 'viewer'


def test_a_tenant_whose_roles_are_not_honoured_changes_no_role_on_sign_in(entra):
    entra.configure(role_mapping='{"UCM.Admin": "admin", "UCM.Reader": "auditor"}',
                    default_role='viewer', sync_role_on_login=True,
                    oauth2_role_tenants=f'["{TENANT_A}"]')
    assert entra(TENANT_B, 'sub-sb', 'mt-sync-b', roles=['UCM.Reader']).endswith(OK)
    assert _role_of('mt-sync-b') == 'viewer'
    User.query.filter_by(username='mt-sync-b').one().role = 'operator'
    db.session.commit()
    assert entra(TENANT_B, 'sub-sb', 'mt-sync-b', roles=['UCM.Admin']).endswith(OK)
    assert _role_of('mt-sync-b') == 'operator'
    # The same claim from an honoured tenant syncs the role
    assert entra(TENANT_A, 'sub-sa', 'mt-sync-a', roles=['UCM.Reader']).endswith(OK)
    assert entra(TENANT_A, 'sub-sa', 'mt-sync-a', roles=['UCM.Admin']).endswith(OK)
    assert _role_of('mt-sync-a') == 'admin'


def test_group_claims_follow_the_same_rule(entra):
    """Group values (object ids, or names a tenant chooses) are mapped like app roles."""
    group = '5b6c7d8e-9f01-4a2b-8c3d-4e5f60718293'
    entra.configure(role_mapping=f'{{"{group}": "admin"}}', default_role='viewer',
                    oauth2_role_tenants=f'["{TENANT_A}"]')
    assert entra(TENANT_B, 'sub-gb', 'mt-group-b', groups=[group]).endswith(OK)
    assert _role_of('mt-group-b') == 'viewer'
    assert entra(TENANT_A, 'sub-ga', 'mt-group-a', groups=[group]).endswith(OK)
    assert _role_of('mt-group-a') == 'admin'


def test_without_a_default_role_a_tenant_whose_roles_are_not_honoured_is_refused(entra):
    entra.configure(role_mapping='{"UCM.Admin": "admin"}', default_role=None,
                    oauth2_role_tenants=f'["{TENANT_A}"]')
    assert 'sso_no_default_role' in entra(TENANT_B, 'sub-nd', 'mt-nodefault', roles=['UCM.Admin'])
    detail = AuditLog.query.filter(AuditLog.action == 'login_failure').order_by(AuditLog.id.desc()).first()
    assert 'role claims of its tenant are not honoured' in detail.details
