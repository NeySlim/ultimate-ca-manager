"""An OIDC or SAML sign-in test plays the login's round trip and changes nothing.

Each case of the parity matrix runs the test against a simulated IdP, checks that no account,
identity, SSO session, provider row or browser session moved, then plays the login with the
same IdP answer on the same database and compares the verdicts.
"""
import base64
import hashlib
import json
import time
import uuid
from datetime import timedelta
from urllib.parse import parse_qs, urlsplit

import pytest
from cryptography.hazmat.primitives import serialization
from onelogin.saml2.utils import OneLogin_Saml2_Utils
from sqlalchemy import text

from api.v2.sso import login_routes, saml_sp, sign_in_tests
from models import AuditLog, User, UserSSOIdentity, db
from models.sso import SAMLMessageId, SSOProvider, SSOSession, SSOSignInTest
from services.oidc_id_token import OIDCValidationError
from tests.test_saml_strict_validation import (  # noqa: F401 (fixture)
    ACS, IDP_ENTITY, SP_BASE, _response, idp_signer,
)
from utils.datetime_utils import utc_now

pytestmark = pytest.mark.usefixtures('drop_new_users')

HOST = urlsplit(SP_BASE).hostname
OIDC_CALLBACK = '/api/v2/sso/callback/oauth2'
TABLES = ('users', 'user_sso_identities', 'pro_sso_sessions', 'pro_sso_providers')
LOGIN_ACTIONS = ('login_success', 'login_failure')
SECRET_CLIENT = 'CS-' + uuid.uuid4().hex


# -- helpers ----------------------------------------------------------------

def _uid(prefix='sit'):
    return f'{prefix}-{uuid.uuid4().hex[:10]}'


def _admin_client(app, username='admin', password='changeme123'):
    client = app.test_client()
    r = client.post('/api/v2/auth/login', base_url=SP_BASE,
                    json={'username': username, 'password': password})
    assert r.status_code == 200, r.data
    token = (r.get_json().get('data') or {}).get('csrf_token')
    client.environ_base['HTTP_X_CSRF_TOKEN'] = token or ''
    return client


def _snapshot(app):
    with app.app_context():
        db.session.remove()
        return {t: sorted((tuple(row) for row in db.session.execute(text(f'SELECT * FROM {t}'))),
                          key=repr) for t in TABLES}


def _session_of(app, client):
    name = app.config.get('SESSION_COOKIE_NAME', 'session')
    cookie = client.get_cookie(name, domain=HOST)
    with client.session_transaction(base_url=SP_BASE) as s:
        data = dict(s)
    return (cookie.value if cookie else None), data


def _top_audit(app):
    with app.app_context():
        return db.session.query(db.func.max(AuditLog.id)).scalar() or 0


def _audit_since(app, floor):
    with app.app_context():
        return [(a.action, a.username, a.details, a.success)
                for a in AuditLog.query.filter(AuditLog.id > floor).order_by(AuditLog.id)]


def _location(r):
    assert r.status_code == 302, r.get_data(as_text=True)
    return r.headers['Location']


def _login_outcome(location):
    parts = urlsplit(location)
    if parts.path == '/login/sso-complete':
        return 'accepted', None
    assert parts.path == '/login', location
    return 'refused', parse_qs(parts.query)['error'][0]


def _set(app, pid, **fields):
    with app.app_context():
        row = db.session.get(SSOProvider, pid)
        for key, value in fields.items():
            setattr(row, key, value)
        db.session.commit()


def _read_report(client, test_id):
    r = client.get(f'/api/v2/sso/sign-in-tests/{test_id}', base_url=SP_BASE)
    assert r.status_code == 200, r.data
    data = r.get_json()['data']
    assert data['state'] == 'done', data
    return data['report']


# -- providers and the simulated IdPs -----------------------------------------

class _Resp:
    def __init__(self, body, ok=True):
        self._body, self.ok, self.text = body, ok, ''

    def json(self):
        return self._body


class OIDCIdP:
    """The token, UserInfo and ID token answers of one IdP, the same for a test and a login."""

    def __init__(self, sub, userinfo, id_claims=None):
        self.sub = sub
        self.userinfo = userinfo
        self.id_claims = {'sub': sub} if id_claims is None else id_claims
        self.access_token = 'AT-' + uuid.uuid4().hex
        self.id_token = 'IDT-' + uuid.uuid4().hex + '.x.y'
        self.tokens = {'access_token': self.access_token, 'id_token': self.id_token}
        self.token_ok = self.userinfo_ok = True
        self.post_error = self.id_error = self.get_error = None
        self.token_requests, self.nonces = [], []

    def post(self, url, data=None, **_k):
        self.token_requests.append(dict(data or {}))
        if self.post_error:
            raise ValueError(self.post_error)
        return _Resp(dict(self.tokens), self.token_ok)

    def get(self, url, headers=None, **_k):
        if self.get_error:
            raise ValueError(self.get_error)
        return _Resp(dict(self.userinfo), self.userinfo_ok)

    def verify(self, id_token, provider, nonce, verify=True, ssl_verify=True):
        self.nonces.append(nonce)
        if self.id_error:
            raise OIDCValidationError(self.id_error)
        return dict(self.id_claims)


@pytest.fixture
def oidc_provider(app):
    """The only enabled OAuth2 provider while a test runs (the login picks the first one)."""
    with app.app_context():
        others = [(p.id, p.enabled) for p in SSOProvider.query.filter_by(provider_type='oauth2')]
        for pid, _ in others:
            db.session.get(SSOProvider, pid).enabled = False
        row = SSOProvider(
            name=_uid('sit-oidc'), provider_type='oauth2', enabled=True,
            oauth2_client_id='ucm-client', oauth2_client_secret=SECRET_CLIENT,
            oauth2_auth_url='https://idp.example/authorize',
            oauth2_token_url='https://idp.example/token',
            oauth2_userinfo_url='https://idp.example/userinfo',
            oauth2_issuer='https://idp.example', id_token_verify=True,
            auto_create_users=True, default_role='viewer')
        db.session.add(row)
        db.session.commit()
        pid = row.id
    yield pid
    _drop_provider(app, pid)
    with app.app_context():
        for opid, enabled in others:
            db.session.get(SSOProvider, opid).enabled = enabled
        db.session.commit()


@pytest.fixture
def saml_provider(app, idp_signer, monkeypatch):
    monkeypatch.setattr(saml_sp, 'get_admin_base_url', lambda: None)
    monkeypatch.setattr(saml_sp, 'get_admin_canonical_origin', lambda: None)
    with app.app_context():
        others = [(p.id, p.enabled) for p in SSOProvider.query.filter_by(provider_type='saml')]
        for pid, _ in others:
            db.session.get(SSOProvider, pid).enabled = False
        row = SSOProvider(
            name=_uid('sit-saml'), provider_type='saml', enabled=True,
            saml_entity_id=IDP_ENTITY, saml_sso_url='https://idp.example.test/sso',
            saml_certificate=idp_signer[1], auto_create_users=True, default_role='viewer')
        db.session.add(row)
        db.session.commit()
        pid = row.id
    yield pid
    _drop_provider(app, pid)
    with app.app_context():
        for opid, enabled in others:
            db.session.get(SSOProvider, opid).enabled = enabled
        db.session.commit()


def _drop_provider(app, pid):
    with app.app_context():
        db.session.rollback()
        SSOSession.query.filter_by(provider_id=pid).delete()
        db.session.commit()
        SSOSignInTest.query.filter_by(provider_id=pid).delete()
        SAMLMessageId.query.filter_by(provider_id=pid).delete()
        for user in User.query.filter(User.sso_identities.any(UserSSOIdentity.provider_id == pid)):
            db.session.delete(user)
        db.session.delete(db.session.get(SSOProvider, pid))
        db.session.commit()


def _install_idp(monkeypatch, idp):
    monkeypatch.setattr(login_routes, 'safe_request_post', idp.post)
    monkeypatch.setattr(login_routes, 'safe_request_get', idp.get)
    monkeypatch.setattr(login_routes, 'verify_id_token', idp.verify)


# -- one round trip of each kind ----------------------------------------------

def _start(client, pid):
    r = client.post(f'/api/v2/sso/providers/{pid}/test-sign-in', base_url=SP_BASE)
    assert r.status_code == 200, r.data
    return r.get_json()['data']


def _oidc_callback(client, state, error=None, code=None):
    query = {'state': state, **({'error': error} if error else {'code': code or 'CODE-x'})}
    return client.get(OIDC_CALLBACK, base_url=SP_BASE, query_string=query)


def _oidc_test(client, pid, error=None, code=None):
    started = _start(client, pid)
    state = parse_qs(urlsplit(started['url']).query)['state'][0]
    location = _location(_oidc_callback(client, state, error, code))
    assert location == '/sso-test-complete?result=done', location
    return started, state


def _oidc_login(app, error=None):
    client = app.test_client()
    location = _location(client.get('/api/v2/sso/login/oauth2', base_url=SP_BASE))
    state = parse_qs(urlsplit(location).query)['state'][0]
    return client, _login_outcome(_location(_oidc_callback(client, state, error)))


def _request_id(url):
    xml = OneLogin_Saml2_Utils.decode_base64_and_inflate(parse_qs(urlsplit(url).query)['SAMLRequest'][0])
    from onelogin.saml2.xml_utils import OneLogin_Saml2_XML
    return OneLogin_Saml2_XML.to_etree(xml).get('ID')


def _saml_test(client, pid, answer):
    started = _start(client, pid)
    request_id = _request_id(started['url'])
    r = client.post(ACS, base_url=SP_BASE, data={'SAMLResponse': answer(request_id)})
    assert _location(r) == '/sso-test-complete?result=done'
    return started, request_id


def _saml_login(app, answer):
    client = app.test_client()
    r = client.get('/api/v2/sso/login/saml', base_url=SP_BASE)
    assert r.status_code == 302, r.data
    request_id = client.get_cookie(saml_sp.REQUEST_COOKIE, domain=HOST, path=ACS).value
    r = client.post(ACS, base_url=SP_BASE, data={'SAMLResponse': answer(request_id)})
    return client, _login_outcome(_location(r))


# -- the parity matrix ----------------------------------------------------------

class Case:
    """One identity at the IdP and the state of the UCM accounts it meets."""

    def __init__(self, app, pid, protocol):
        self.app, self.pid, self.protocol = app, pid, protocol
        self.username = _uid('sit-user')
        self.email = f'{self.username}@example.test'
        self.external_id = _uid('sit-sub')
        self.groups = ['staff']
        self.created = []

    def add_user(self, username=None, *, provider_id=None, external_id=None, local=False,
                 active=True, email=None, role='viewer'):
        with self.app.app_context():
            user = User(username=username or self.username, email=email or f'{_uid()}@example.test',
                        role=role, active=active)
            if local:
                user.set_password('Local-Passw0rd!x')
            else:
                user.password_hash = '!SSO_NO_PASSWORD!'
            if provider_id is not None:
                row = UserSSOIdentity(provider_id=provider_id)
                row.bind(external_id)
                user.sso_identities.append(row)
            db.session.add(user)
            db.session.commit()
            self.created.append(user.id)
            return user.id

    def other_provider(self):
        with self.app.app_context():
            row = SSOProvider(name=_uid('sit-other'), provider_type='ldap', enabled=False,
                              ldap_server='ldap.example.test', default_role='viewer')
            db.session.add(row)
            db.session.commit()
            self.others = getattr(self, 'others', []) + [row.id]
            return row.id

    def cleanup(self):
        with self.app.app_context():
            db.session.rollback()
            SSOSession.query.filter_by(provider_id=self.pid).delete()
            db.session.commit()
            for user_id in self.created:
                user = db.session.get(User, user_id)
                if user is not None:
                    db.session.delete(user)
            for user in User.query.filter_by(username=self.username):
                db.session.delete(user)
            db.session.commit()
            for other in getattr(self, 'others', []):
                row = db.session.get(SSOProvider, other)
                if row is not None:
                    UserSSOIdentity.query.filter_by(provider_id=other).delete()
                    db.session.delete(row)
            db.session.commit()


def _account_case(case, name):
    """Set the accounts up for ``name``; returns what the report must say of the account."""
    app, pid = case.app, case.pid
    if name == 'create':
        return 'create'
    if name == 'open_bound':
        case.add_user(provider_id=pid, external_id=case.external_id)
        return 'open'
    if name == 'open_attached_pending':
        case.add_user(provider_id=pid, external_id=None)  # SSO-05: attached, not bound yet
        return 'open'
    if name == 'conflict_local':
        case.add_user(local=True)
    elif name == 'conflict_other_identity':
        case.add_user(provider_id=pid, external_id=_uid('sit-other-sub'))
    elif name == 'conflict_other_provider':
        case.add_user(provider_id=case.other_provider(), external_id=_uid('sit-x'))
    elif name == 'email_conflict':
        case.add_user(_uid('sit-owner'), provider_id=case.other_provider(),
                      external_id=_uid('sit-x'), email=case.email)
    elif name == 'auto_create_disabled':
        _set(app, pid, auto_create_users=False)
    elif name == 'unmapped':
        _set(app, pid, role_mapping=json.dumps({'admins': 'admin'}))
    elif name == 'no_default_role':
        _set(app, pid, default_role=None)
    elif name == 'account_disabled':
        case.add_user(provider_id=pid, external_id=case.external_id, active=False)
    elif name == 'mapped_role_create':
        _set(app, pid, role_mapping=json.dumps({'staff': 'operator'}))
        return 'create'
    elif name == 'role_sync_open':
        _set(app, pid, role_mapping=json.dumps({'staff': 'auditor'}), sync_role_on_login=True)
        case.add_user(provider_id=pid, external_id=case.external_id, role='viewer')
        return 'open'
    else:
        raise AssertionError(name)
    return None


ACCOUNT_CASES = ('create', 'open_bound', 'open_attached_pending', 'conflict_local',
                 'conflict_other_identity', 'conflict_other_provider', 'email_conflict',
                 'auto_create_disabled', 'unmapped', 'no_default_role', 'account_disabled',
                 'mapped_role_create', 'role_sync_open')
PROVIDER_STATES = ('enabled', 'disabled')


def _reset_provider(app, pid):
    _set(app, pid, auto_create_users=True, role_mapping=None, default_role='viewer',
         sync_role_on_login=False, id_token_verify=True, enabled=True)
    with app.app_context():
        row = db.session.get(SSOProvider, pid)
        if row.provider_type == 'oauth2' and row.oauth2_client_secret != SECRET_CLIENT:
            row.oauth2_client_secret = SECRET_CLIENT
            db.session.commit()


def _check_nothing_moved(app, client, before, session_before, floor, report):
    """Invariant 1 and 8: tables and browser session as before, one audit entry of the test."""
    assert _snapshot(app) == before
    cookie, data = _session_of(app, client)
    assert cookie == session_before[0]
    strip = lambda d: {k: v for k, v in d.items() if k != 'last_activity'}  # noqa: E731
    assert strip(data) == strip(session_before[1])
    assert data.get('auth_method') != 'sso'
    entries = _audit_since(app, floor)
    assert [e[0] for e in entries] == [sign_in_tests.AUDIT_ACTION], entries
    assert not any(e[0] in LOGIN_ACTIONS for e in entries)
    assert entries[0][1] == session_before[1].get('username')
    assert report['verdict'] in entries[0][2]


def _compare_login(app, case, report, expected_account, login):
    """The login with the same IdP answer, on the same accounts, gives the same verdict."""
    _set(app, case.pid, enabled=True)
    with app.app_context():
        existing = {u.username: u.id for u in User.query.filter(User.username == case.username)}
    client, (verdict, code) = login()
    assert (report['verdict'], report['code']) == (verdict, code), report
    if verdict != 'accepted':
        return
    with client.session_transaction(base_url=SP_BASE) as s:
        opened = s['username']
    assert report['account']['username'] == opened
    assert report['account']['outcome'] == expected_account
    assert (opened in existing) == (expected_account == 'open')
    with app.app_context():
        user = User.query.filter_by(username=opened).one()
        assert report['role'] == user.role
        case.created.append(user.id)


def _oidc_userinfo(case):
    return {'sub': case.external_id, 'preferred_username': case.username, 'email': case.email,
            'email_verified': True, 'name': 'Sit User', 'groups': list(case.groups)}


@pytest.mark.parametrize('state', PROVIDER_STATES)
@pytest.mark.parametrize('name', ACCOUNT_CASES)
def test_oidc_parity_account(app, oidc_provider, monkeypatch, name, state):
    case = Case(app, oidc_provider, 'oauth2')
    try:
        expected = _account_case(case, name)
        idp = OIDCIdP(case.external_id, _oidc_userinfo(case))
        _install_idp(monkeypatch, idp)
        if state == 'disabled':
            _set(app, oidc_provider, enabled=False)
        client = _admin_client(app)
        before, floor = _snapshot(app), _top_audit(app)
        started = _start(client, oidc_provider)
        session_before = _session_of(app, client)
        state_value = parse_qs(urlsplit(started['url']).query)['state'][0]
        assert _location(_oidc_callback(client, state_value)) == '/sso-test-complete?result=done'
        report = _read_report(client, started['id'])
        _check_nothing_moved(app, client, before, session_before, floor, report)
        assert report['provider_enabled'] is (state == 'enabled')
        _compare_login(app, case, report, expected, lambda: _oidc_login(app))
    finally:
        case.cleanup()
        _reset_provider(app, oidc_provider)


def _boom(*_a, **_k):
    raise RuntimeError('unexpected failure while reading the identity')


def _oidc_protocol_case(idp, name, provider_id, app, monkeypatch):
    """IdP answers the login refuses before any account; returns the callback error param."""
    if name == 'idp_error':
        return 'access_denied'
    if name == 'token_http_error':
        idp.token_ok = False
    elif name == 'token_endpoint_rejected':
        idp.post_error = 'redirect refused'
    elif name == 'no_access_token':
        idp.tokens.pop('access_token')
    elif name == 'no_id_token':
        idp.tokens.pop('id_token')
    elif name == 'id_token_invalid':
        idp.id_error = 'ID token audience mismatch'
    elif name == 'userinfo_failed':
        idp.userinfo_ok = False
    elif name == 'userinfo_endpoint_rejected':
        idp.get_error = 'redirect refused'
    elif name == 'client_secret_unreadable':
        from cryptography.fernet import Fernet
        foreign = Fernet(Fernet.generate_key()).encrypt(b'saved under another key').decode()
        _set(app, provider_id, _oauth2_client_secret=foreign)
    elif name == 'callback_error':
        monkeypatch.setattr(login_routes, 'oidc_identity', _boom)
    elif name == 'subject_mismatch':
        idp.id_claims = {'sub': 'somebody-else'}
    elif name == 'no_username':
        idp.userinfo = {'sub': idp.sub}
    elif name == 'compatibility_mode':
        _set(app, provider_id, id_token_verify=False)
    else:
        raise AssertionError(name)
    return None


OIDC_PROTOCOL_CASES = ('idp_error', 'token_http_error', 'token_endpoint_rejected',
                       'no_access_token', 'no_id_token', 'id_token_invalid', 'userinfo_failed',
                       'userinfo_endpoint_rejected', 'subject_mismatch', 'no_username',
                       'compatibility_mode', 'client_secret_unreadable', 'callback_error')
# Where each of these stops: the login's own refusal, not an earlier one.
OIDC_CODES = {
    'userinfo_endpoint_rejected': ('invalid_credentials', 'userinfo endpoint rejected'),
    'client_secret_unreadable': ('token_exchange_failed', 'client secret cannot be read'),
    'callback_error': ('callback_error', 'unexpected error'),
}


@pytest.mark.parametrize('state', PROVIDER_STATES)
@pytest.mark.parametrize('name', OIDC_PROTOCOL_CASES)
def test_oidc_parity_protocol(app, oidc_provider, monkeypatch, name, state):
    case = Case(app, oidc_provider, 'oauth2')
    try:
        idp = OIDCIdP(case.external_id, _oidc_userinfo(case))
        error = _oidc_protocol_case(idp, name, oidc_provider, app, monkeypatch)
        _install_idp(monkeypatch, idp)
        if state == 'disabled':
            _set(app, oidc_provider, enabled=False)
        client = _admin_client(app)
        before, floor = _snapshot(app), _top_audit(app)
        started = _start(client, oidc_provider)
        session_before = _session_of(app, client)
        state_value = parse_qs(urlsplit(started['url']).query)['state'][0]
        assert _location(_oidc_callback(client, state_value, error)) == '/sso-test-complete?result=done'
        report = _read_report(client, started['id'])
        _check_nothing_moved(app, client, before, session_before, floor, report)
        if name == 'compatibility_mode':
            assert report['verdict'] == 'accepted' and report['not_verified'], report
        else:
            assert report['verdict'] == 'refused' and report['stage'] == 'protocol', report
        if name in OIDC_CODES:
            code, reason = OIDC_CODES[name]
            assert report['code'] == code and reason in report['reason'], report
        _compare_login(app, case, report, 'create', lambda: _oidc_login(app, error))
    finally:
        case.cleanup()
        _reset_provider(app, oidc_provider)


def _saml_answer(case, signer, **overrides):
    attributes = {'username': [case.username], 'email': [case.email], 'groups': case.groups}
    args = dict(name_id=case.external_id, attributes=attributes)
    args.update(overrides)
    return lambda request_id: _response(signer, in_response_to=request_id, **args)


@pytest.mark.parametrize('state', PROVIDER_STATES)
@pytest.mark.parametrize('name', ACCOUNT_CASES)
def test_saml_parity_account(app, saml_provider, idp_signer, name, state):
    case = Case(app, saml_provider, 'saml')
    try:
        expected = _account_case(case, name)
        answer = _saml_answer(case, idp_signer)
        if state == 'disabled':
            _set(app, saml_provider, enabled=False)
        client = _admin_client(app)
        before, floor = _snapshot(app), _top_audit(app)
        started = _start(client, saml_provider)
        session_before = _session_of(app, client)
        r = client.post(ACS, base_url=SP_BASE,
                        data={'SAMLResponse': answer(_request_id(started['url']))})
        assert _location(r) == '/sso-test-complete?result=done'
        report = _read_report(client, started['id'])
        _check_nothing_moved(app, client, before, session_before, floor, report)
        _compare_login(app, case, report, expected, lambda: _saml_login(app, answer))
    finally:
        case.cleanup()
        _reset_provider(app, saml_provider)


@pytest.fixture(scope='module')
def other_signer():
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.asymmetric import rsa
    from cryptography.x509.oid import NameOID
    import datetime
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, 'impostor.example.test')])
    now = datetime.datetime.now(datetime.timezone.utc)
    cert = (x509.CertificateBuilder().subject_name(name).issuer_name(name)
            .public_key(key.public_key()).serial_number(x509.random_serial_number())
            .not_valid_before(now - datetime.timedelta(minutes=5))
            .not_valid_after(now + datetime.timedelta(days=1)).sign(key, hashes.SHA256()))
    key_pem = key.private_bytes(serialization.Encoding.PEM,
                                serialization.PrivateFormat.TraditionalOpenSSL,
                                serialization.NoEncryption()).decode()
    return key_pem, cert.public_bytes(serialization.Encoding.PEM).decode()


SAML_PROTOCOL_CASES = ('bad_signature', 'wrong_audience', 'expired', 'no_not_on_or_after',
                       'assertion_replayed', 'no_username', 'assertion_id_absent',
                       'assertion_id_too_long', 'assertion_id_unread', 'callback_error')
# An assertion without ID fails python3-saml's schema check first; the login's own check of a
# missing ID (saml_assertion) is reached only when the ID reads back empty, as in 'unread'.
SAML_REASONS = {
    'assertion_id_absent': 'saml-schema-protocol-2.0.xsd',
    'assertion_id_too_long': 'assertion ID missing or longer than',
    'assertion_id_unread': 'assertion ID missing or longer than',
    'callback_error': 'unexpected error',
}


def _drop_assertion_id(monkeypatch, marker):
    """The IdP signs a response whose assertion carries no ID attribute."""
    sign = OneLogin_Saml2_Utils.add_sign
    monkeypatch.setattr(OneLogin_Saml2_Utils, 'add_sign', staticmethod(
        lambda xml, *a, **k: sign(xml.replace(f' ID="{marker}"', ''), *a, **k)))


@pytest.mark.parametrize('state', PROVIDER_STATES)
@pytest.mark.parametrize('name', SAML_PROTOCOL_CASES)
def test_saml_parity_protocol(app, saml_provider, idp_signer, other_signer, monkeypatch, name,
                              state):
    case = Case(app, saml_provider, 'saml')
    try:
        signer, overrides = idp_signer, {}
        if name == 'bad_signature':
            signer = other_signer
        elif name == 'wrong_audience':
            overrides['audience'] = 'https://elsewhere.example.test/sp'
        elif name == 'expired':
            overrides.update(issued=-30, expires=-20)
        elif name == 'no_not_on_or_after':
            overrides['scd_expiry'] = False
        elif name == 'assertion_replayed':
            overrides['assertion_id'] = '_a' + uuid.uuid4().hex
            with app.app_context():
                later = time.time() + 300
                assert saml_sp.consume_assertion(overrides['assertion_id'], saml_provider, later)
        elif name == 'no_username':
            overrides.update(attributes={'groups': ['staff']}, name_id=' ')
        elif name == 'assertion_id_absent':
            overrides['assertion_id'] = '_a' + uuid.uuid4().hex
            _drop_assertion_id(monkeypatch, overrides['assertion_id'])
        elif name == 'assertion_id_too_long':
            overrides['assertion_id'] = '_a' + 'x' * (saml_sp.MAX_MESSAGE_ID_LENGTH + 1)
        elif name == 'assertion_id_unread':
            from onelogin.saml2.auth import OneLogin_Saml2_Auth
            monkeypatch.setattr(OneLogin_Saml2_Auth, 'get_last_assertion_id', lambda self: None)
        elif name == 'callback_error':
            monkeypatch.setattr(login_routes, 'saml_identity', _boom)
        answer = _saml_answer(case, signer, **overrides)
        if state == 'disabled':
            _set(app, saml_provider, enabled=False)
        client = _admin_client(app)
        before, floor = _snapshot(app), _top_audit(app)
        started = _start(client, saml_provider)
        session_before = _session_of(app, client)
        r = client.post(ACS, base_url=SP_BASE,
                        data={'SAMLResponse': answer(_request_id(started['url']))})
        assert _location(r) == '/sso-test-complete?result=done'
        report = _read_report(client, started['id'])
        _check_nothing_moved(app, client, before, session_before, floor, report)
        assert report['verdict'] == 'refused' and report['stage'] == 'protocol', report
        if name in SAML_REASONS:
            code = 'callback_error' if name == 'callback_error' else 'saml_validation_failed'
            assert report['code'] == code and SAML_REASONS[name] in report['reason'], report
        _compare_login(app, case, report, None, lambda: _saml_login(app, answer))
    finally:
        case.cleanup()
        _reset_provider(app, saml_provider)


# -- two enabled providers of one type: the login uses one of them only -------------------

def _second_oidc(app, enabled=True):
    with app.app_context():
        row = SSOProvider(
            name=_uid('sit-oidc2'), provider_type='oauth2', enabled=enabled,
            oauth2_client_id='ucm-client', oauth2_client_secret=SECRET_CLIENT,
            oauth2_auth_url='https://idp.example/authorize',
            oauth2_token_url='https://idp.example/token',
            oauth2_userinfo_url='https://idp.example/userinfo',
            oauth2_issuer='https://idp.example', id_token_verify=True,
            auto_create_users=True, default_role='viewer')
        db.session.add(row)
        db.session.commit()
        return row.id


def _login_pick(app, protocol):
    with app.app_context():
        return login_routes.login_provider(protocol).id


@pytest.mark.parametrize('second_enabled', (True, False))
def test_a_report_names_the_enabled_provider_the_login_uses_instead(
        app, oidc_provider, monkeypatch, second_enabled):
    case = Case(app, oidc_provider, 'oauth2')
    second = _second_oidc(app, enabled=second_enabled)
    try:
        _install_idp(monkeypatch, OIDCIdP(case.external_id, _oidc_userinfo(case)))
        client = _admin_client(app)
        chosen = _login_pick(app, 'oauth2')
        assert chosen in (oidc_provider, second)
        with app.app_context():
            chosen_name = db.session.get(SSOProvider, chosen).name
        for pid in (oidc_provider, second):
            started, _state = _oidc_test(client, pid)
            report = _read_report(client, started['id'])
            if pid == chosen:
                assert report.get('shadowed_by') is None, report
            else:
                assert report['shadowed_by'] == {'id': chosen, 'name': chosen_name}, report
        # The login itself goes through the provider named, whatever the test of the other said.
        login = app.test_client()
        assert _location(login.get('/api/v2/sso/login/oauth2', base_url=SP_BASE))
        with login.session_transaction(base_url=SP_BASE) as s:
            assert s['sso_provider_id'] == chosen
    finally:
        case.cleanup()
        _drop_provider(app, second)


# -- invariant 2: a test transaction never ends as a login, nor the reverse ---------

def _no_account(app, username):
    with app.app_context():
        return User.query.filter_by(username=username).first() is None


def test_oidc_a_test_state_never_completes_a_login(app, oidc_provider, monkeypatch):
    case = Case(app, oidc_provider, 'oauth2')
    try:
        _install_idp(monkeypatch, OIDCIdP(case.external_id, _oidc_userinfo(case)))
        client = _admin_client(app)
        started = _start(client, oidc_provider)
        state = parse_qs(urlsplit(started['url']).query)['state'][0]
        with app.app_context():  # gone (purged), its state reaches the login's checks
            SSOSignInTest.query.filter_by(token=started['id']).delete()
            db.session.commit()
        assert _location(_oidc_callback(client, state)) == '/login?error=invalid_state'
        assert _session_of(app, client)[1]['username'] == 'admin'
        assert _no_account(app, case.username)
    finally:
        case.cleanup()


def test_oidc_a_login_state_never_yields_a_test_report(app, oidc_provider, monkeypatch):
    case = Case(app, oidc_provider, 'oauth2')
    try:
        _install_idp(monkeypatch, OIDCIdP(case.external_id, _oidc_userinfo(case)))
        client = _admin_client(app)
        started = _start(client, oidc_provider)  # pending in this same browser
        location = _location(client.get('/api/v2/sso/login/oauth2', base_url=SP_BASE))
        state = parse_qs(urlsplit(location).query)['state'][0]
        assert _location(_oidc_callback(client, state)) == '/login/sso-complete'
        with app.app_context():
            test = SSOSignInTest.query.filter_by(token=started['id']).one()
            assert (test.state, test.report) == (SSOSignInTest.PENDING, None)
        assert _session_of(app, client)[1]['username'] == case.username
    finally:
        case.cleanup()


def test_saml_a_test_request_never_completes_a_login(app, saml_provider, idp_signer):
    case = Case(app, saml_provider, 'saml')
    try:
        client = _admin_client(app)
        started = _start(client, saml_provider)
        request_id = _request_id(started['url'])
        with app.app_context():
            SSOSignInTest.query.filter_by(token=started['id']).delete()
            db.session.commit()
        client.set_cookie(saml_sp.REQUEST_COOKIE, request_id, domain=HOST, path=ACS)
        r = client.post(ACS, base_url=SP_BASE,
                        data={'SAMLResponse': _saml_answer(case, idp_signer)(request_id)})
        assert _location(r) == '/login?error=saml_login_expired'
        assert _session_of(app, client)[1]['username'] == 'admin'
        assert _no_account(app, case.username)
    finally:
        case.cleanup()


def test_saml_a_login_request_never_yields_a_test_report(app, saml_provider, idp_signer):
    case = Case(app, saml_provider, 'saml')
    try:
        client = _admin_client(app)
        started = _start(client, saml_provider)
        assert client.get('/api/v2/sso/login/saml', base_url=SP_BASE).status_code == 302
        login_id = client.get_cookie(saml_sp.REQUEST_COOKIE, domain=HOST, path=ACS).value
        r = client.post(ACS, base_url=SP_BASE,
                        data={'SAMLResponse': _saml_answer(case, idp_signer)(login_id)})
        assert _location(r) == '/login/sso-complete'
        with app.app_context():
            test = SSOSignInTest.query.filter_by(token=started['id']).one()
            assert (test.state, test.report) == (SSOSignInTest.PENDING, None)
    finally:
        case.cleanup()


def test_saml_an_unsolicited_response_is_never_a_test(app, saml_provider, idp_signer):
    """SAML Profiles §4.1.5: an unsolicited <Response> MUST NOT contain an InResponseTo."""
    case = Case(app, saml_provider, 'saml')
    try:
        _set(app, saml_provider, saml_allow_idp_initiated=True)
        client = _admin_client(app)
        started = _start(client, saml_provider)
        r = client.post(ACS, base_url=SP_BASE,
                        data={'SAMLResponse': _saml_answer(case, idp_signer)(None)})
        assert _location(r) == '/login/sso-complete'
        with app.app_context():
            assert SSOSignInTest.query.filter_by(token=started['id']).one().state == 'pending'
        _set(app, saml_provider, enabled=False)
        r = app.test_client().post(ACS, base_url=SP_BASE,
                                   data={'SAMLResponse': _saml_answer(case, idp_signer)(None)})
        assert _location(r) == '/login?error=provider_not_found'
    finally:
        _set(app, saml_provider, saml_allow_idp_initiated=False)
        case.cleanup()
        _reset_provider(app, saml_provider)


# -- invariant 3: a disabled provider signs nobody in ---------------------------------

def test_oidc_a_login_started_before_the_provider_was_disabled_is_refused(app, oidc_provider,
                                                                         monkeypatch):
    case = Case(app, oidc_provider, 'oauth2')
    try:
        _install_idp(monkeypatch, OIDCIdP(case.external_id, _oidc_userinfo(case)))
        client = app.test_client()
        location = _location(client.get('/api/v2/sso/login/oauth2', base_url=SP_BASE))
        state = parse_qs(urlsplit(location).query)['state'][0]
        _set(app, oidc_provider, enabled=False)
        assert _location(_oidc_callback(client, state)) == '/login?error=provider_not_found'
        assert _location(_oidc_callback(app.test_client(), 'unknown')) == '/login?error=provider_not_found'
        assert _no_account(app, case.username)
    finally:
        case.cleanup()
        _reset_provider(app, oidc_provider)


def test_saml_a_login_started_before_the_provider_was_disabled_is_refused(app, saml_provider,
                                                                         idp_signer):
    case = Case(app, saml_provider, 'saml')
    try:
        client = app.test_client()
        assert client.get('/api/v2/sso/login/saml', base_url=SP_BASE).status_code == 302
        login_id = client.get_cookie(saml_sp.REQUEST_COOKIE, domain=HOST, path=ACS).value
        _set(app, saml_provider, enabled=False)
        r = client.post(ACS, base_url=SP_BASE,
                        data={'SAMLResponse': _saml_answer(case, idp_signer)(login_id)})
        assert _location(r) == '/login?error=provider_not_found'
        assert _no_account(app, case.username)
    finally:
        case.cleanup()
        _reset_provider(app, saml_provider)


# -- invariant 4: the report belongs to whoever started the test -------------------------

def _second_admin(app, case, role='admin'):
    name = _uid('sit-admin')
    with app.app_context():
        user = User(username=name, email=f'{name}@example.test', role=role, active=True)
        user.set_password('Second-Adm1n-Passw0rd!')
        db.session.add(user)
        db.session.commit()
        case.created.append(user.id)
    with app.app_context():
        u = User.query.filter_by(username=name).one()
        u.force_password_change = False
        db.session.commit()
    return name, _admin_client(app, name, 'Second-Adm1n-Passw0rd!')


def test_only_the_account_that_started_a_test_reads_its_report(app, oidc_provider, monkeypatch):
    case = Case(app, oidc_provider, 'oauth2')
    try:
        _install_idp(monkeypatch, OIDCIdP(case.external_id, _oidc_userinfo(case)))
        owner_name, owner = _second_admin(app, case)
        _other_name, other = _second_admin(app, case)
        started, _state = _oidc_test(owner, oidc_provider)
        path = f"/api/v2/sso/sign-in-tests/{started['id']}"
        assert other.get(path, base_url=SP_BASE).status_code == 404
        assert app.test_client().get(path, base_url=SP_BASE).status_code == 401
        assert owner.get(path, base_url=SP_BASE).status_code == 200
        with app.app_context():  # demoted, the session still open: no longer holds write:sso
            User.query.filter_by(username=owner_name).one().role = 'viewer'
            db.session.commit()
        assert owner.get(path, base_url=SP_BASE).status_code == 403
    finally:
        case.cleanup()


def test_a_saml_return_without_the_session_cookie_still_reports_to_its_owner(
        app, saml_provider, idp_signer):
    """The response comes back as a cross-site POST: only the test's own cookie follows it."""
    case = Case(app, saml_provider, 'saml')
    try:
        client = _admin_client(app)
        started = _start(client, saml_provider)
        bare = app.test_client()
        cookie = client.get_cookie(sign_in_tests.BROWSER_COOKIE, domain=HOST, path=ACS)
        assert cookie is not None and cookie.secure and cookie.http_only
        bare.set_cookie(sign_in_tests.BROWSER_COOKIE, cookie.value, domain=HOST, path=ACS)
        r = bare.post(ACS, base_url=SP_BASE,
                      data={'SAMLResponse': _saml_answer(case, idp_signer)(_request_id(started['url']))})
        assert _location(r) == '/sso-test-complete?result=done'
        assert _read_report(client, started['id'])['verdict'] == 'accepted'
    finally:
        case.cleanup()


def test_a_return_to_another_browser_is_refused_and_leaves_the_test_pending(
        app, oidc_provider, monkeypatch):
    case = Case(app, oidc_provider, 'oauth2')
    try:
        _install_idp(monkeypatch, OIDCIdP(case.external_id, _oidc_userinfo(case)))
        client = _admin_client(app)
        started = _start(client, oidc_provider)
        state = parse_qs(urlsplit(started['url']).query)['state'][0]
        stranger = _admin_client(app)
        assert _location(_oidc_callback(stranger, state)) == '/sso-test-complete?result=other_browser'
        with app.app_context():
            assert SSOSignInTest.query.filter_by(token=started['id']).one().state == 'pending'
        assert _location(_oidc_callback(client, state)) == '/sso-test-complete?result=done'
    finally:
        case.cleanup()


# -- invariant 5: used once, expires, and the login's checks apply as they are -----------

def test_a_second_return_with_the_same_state_is_a_replay(app, oidc_provider, monkeypatch):
    case = Case(app, oidc_provider, 'oauth2')
    try:
        _install_idp(monkeypatch, OIDCIdP(case.external_id, _oidc_userinfo(case)))
        client = _admin_client(app)
        started, state = _oidc_test(client, oidc_provider)
        report = _read_report(client, started['id'])
        floor = _top_audit(app)
        assert _location(_oidc_callback(client, state)) == '/sso-test-complete?result=used'
        assert _read_report(client, started['id']) == report
        assert [(e[0], e[3]) for e in _audit_since(app, floor)] == [(sign_in_tests.AUDIT_ACTION, False)]
    finally:
        case.cleanup()


def test_a_second_post_of_the_same_saml_response_is_a_replay(app, saml_provider, idp_signer):
    case = Case(app, saml_provider, 'saml')
    try:
        client = _admin_client(app)
        started = _start(client, saml_provider)
        answer = _saml_answer(case, idp_signer)(_request_id(started['url']))
        cookie = client.get_cookie(sign_in_tests.BROWSER_COOKIE, domain=HOST, path=ACS).value
        assert _location(client.post(ACS, base_url=SP_BASE, data={'SAMLResponse': answer})) \
            == '/sso-test-complete?result=done'
        client.set_cookie(sign_in_tests.BROWSER_COOKIE, cookie, domain=HOST, path=ACS)
        assert _location(client.post(ACS, base_url=SP_BASE, data={'SAMLResponse': answer})) \
            == '/sso-test-complete?result=used'
    finally:
        case.cleanup()


def test_a_test_expires_ten_minutes_after_its_start_and_its_report_after_its_return(
        app, oidc_provider, monkeypatch):
    case = Case(app, oidc_provider, 'oauth2')
    try:
        _install_idp(monkeypatch, OIDCIdP(case.external_id, _oidc_userinfo(case)))
        client = _admin_client(app)
        started = _start(client, oidc_provider)
        with app.app_context():
            test = SSOSignInTest.query.filter_by(token=started['id']).one()
            assert test.expires_at - test.created_at == timedelta(minutes=10)
            test.expires_at = utc_now() - timedelta(seconds=1)
            db.session.commit()
        state = parse_qs(urlsplit(started['url']).query)['state'][0]
        assert _location(_oidc_callback(client, state)) == '/sso-test-complete?result=expired'
        assert client.get(f"/api/v2/sso/sign-in-tests/{started['id']}", base_url=SP_BASE).status_code == 404

        done, _state = _oidc_test(client, oidc_provider)
        with app.app_context():
            test = SSOSignInTest.query.filter_by(token=done['id']).one()
            assert test.expires_at - test.finished_at == timedelta(minutes=10)
            test.expires_at = utc_now() - timedelta(seconds=1)
            db.session.commit()
        assert client.get(f"/api/v2/sso/sign-in-tests/{done['id']}", base_url=SP_BASE).status_code == 404
        _start(client, oidc_provider)  # a start purges what expired
        assert _erased(app, started['id']) and _erased(app, done['id'])
    finally:
        case.cleanup()


def _expire(app, token):
    with app.app_context():
        SSOSignInTest.query.filter_by(token=token).one().expires_at = utc_now() - timedelta(seconds=1)
        db.session.commit()


def _row(app, token):
    with app.app_context():
        db.session.remove()
        test = SSOSignInTest.query.filter_by(token=token).first()
        return None if test is None else {c.name: getattr(test, c.name)
                                          for c in SSOSignInTest.__table__.columns}


def _exists(app, token):
    return _row(app, token) is not None


def _erased(app, token):
    row = _row(app, token)
    return row is not None and (row['report'], row['secret'], row['browser_hash']) == (None, None, '')


def test_an_expired_report_is_purged_by_the_scheduled_task(app, oidc_provider, monkeypatch):
    """Where nobody starts another test, the report (name, e-mail, groups) still goes."""
    case = Case(app, oidc_provider, 'oauth2')
    try:
        _install_idp(monkeypatch, OIDCIdP(case.external_id, _oidc_userinfo(case)))
        done, _state = _oidc_test(_admin_client(app), oidc_provider)
        live, _state = _oidc_test(_admin_client(app), oidc_provider)
        _expire(app, done['id'])
        status = app.scheduler.run_task_now('sso_sign_in_test_purge')
        assert status and status['last_status'] == 'ok' and status['interval'] == 60, status
        assert status['per_node'] is False, status  # HA: the elected node runs it
        assert _erased(app, done['id'])
        assert _row(app, live['id'])['report'] is not None
    finally:
        case.cleanup()


def test_a_read_and_a_return_purge_what_expired(app, oidc_provider, monkeypatch):
    case = Case(app, oidc_provider, 'oauth2')
    try:
        _install_idp(monkeypatch, OIDCIdP(case.external_id, _oidc_userinfo(case)))
        client = _admin_client(app)
        first, _state = _oidc_test(client, oidc_provider)
        _expire(app, first['id'])
        assert client.get(f"/api/v2/sso/sign-in-tests/{first['id']}", base_url=SP_BASE).status_code == 404
        assert _erased(app, first['id'])

        second, _state = _oidc_test(client, oidc_provider)
        pending = _start(client, oidc_provider)
        _expire(app, second['id'])
        state = parse_qs(urlsplit(pending['url']).query)['state'][0]
        assert _location(_oidc_callback(client, state)) == '/sso-test-complete?result=done'
        assert _erased(app, second['id'])
        assert _row(app, pending['id'])['report'] is not None
    finally:
        case.cleanup()


def test_a_return_still_answers_when_the_purge_fails(app, oidc_provider, monkeypatch):
    case = Case(app, oidc_provider, 'oauth2')
    try:
        _install_idp(monkeypatch, OIDCIdP(case.external_id, _oidc_userinfo(case)))
        client = _admin_client(app)
        started = _start(client, oidc_provider)
        monkeypatch.setattr(sign_in_tests, '_purge_expired', _boom)
        state = parse_qs(urlsplit(started['url']).query)['state'][0]
        assert _location(_oidc_callback(client, state)) == '/sso-test-complete?result=done'
        assert _read_report(client, started['id'])['verdict'] == 'accepted'
    finally:
        case.cleanup()


# -- a return after the expiry is still a test's, for a day ------------------------------

KEPT = ('id', 'token', 'provider_id', 'user_id', 'protocol', 'transaction_hash', 'state',
        'created_at', 'expires_at', 'finished_at')
ERASED = {'secret': None, 'report': None, 'browser_hash': ''}


def _age(app, token, past):
    with app.app_context():
        SSOSignInTest.query.filter_by(token=token).one().expires_at = utc_now() - past
        db.session.commit()


def _purge_by(app, client, token, how):
    if how == 'read':
        assert client.get(f'/api/v2/sso/sign-in-tests/{token}', base_url=SP_BASE).status_code == 404
    else:
        assert app.scheduler.run_task_now('sso_sign_in_test_purge')['last_status'] == 'ok'


def _late_returns(app, client, case, protocol, pid, signer):
    """A pending test and a finished one, each with the return to play again later."""
    if protocol == 'oauth2':
        pending = _start(client, pid)
        state = parse_qs(urlsplit(pending['url']).query)['state'][0]
        done, done_state = _oidc_test(client, pid)
        return [(pending['id'], lambda: _oidc_callback(client, state), 'expired'),
                (done['id'], lambda: _oidc_callback(client, done_state), 'used')]
    answer = _saml_answer(case, signer)
    pending = _start(client, pid)
    late = answer(_request_id(pending['url']))
    done = _start(client, pid)
    replay = answer(_request_id(done['url']))
    assert _location(client.post(ACS, base_url=SP_BASE, data={'SAMLResponse': replay})) \
        == '/sso-test-complete?result=done'
    return [(pending['id'], lambda: client.post(ACS, base_url=SP_BASE, data={'SAMLResponse': late}),
             'expired'),
            (done['id'], lambda: client.post(ACS, base_url=SP_BASE, data={'SAMLResponse': replay}),
             'used')]


@pytest.mark.parametrize('how', ('read', 'task'))
@pytest.mark.parametrize('protocol', ('oauth2', 'saml'))
def test_a_return_after_the_expiry_is_still_a_test_and_the_row_keeps_nothing_personal(
        app, request, monkeypatch, protocol, how):
    pid = request.getfixturevalue('oidc_provider' if protocol == 'oauth2' else 'saml_provider')
    signer = request.getfixturevalue('idp_signer') if protocol == 'saml' else None
    case = Case(app, pid, protocol)
    try:
        if protocol == 'oauth2':
            _install_idp(monkeypatch, OIDCIdP(case.external_id, _oidc_userinfo(case)))
        client = _admin_client(app)
        returns = _late_returns(app, client, case, protocol, pid, signer)
        tokens = [token for token, _r, _x in returns]
        for token in tokens:
            _age(app, token, timedelta(seconds=1))
        before = {token: _row(app, token) for token in tokens}
        assert before[tokens[1]]['report'] and case.username in before[tokens[1]]['report']
        _purge_by(app, client, tokens[0], how)

        for token in tokens:  # every column: what names the transaction stays, nothing else
            row = _row(app, token)
            assert set(row) == set(KEPT) | set(ERASED)
            assert {k: row[k] for k in KEPT} == {k: before[token][k] for k in KEPT}
            assert {k: row[k] for k in ERASED} == ERASED
            assert case.username not in repr(row) and case.email not in repr(row)

        floor = _top_audit(app)
        for _token, again, result in returns:
            assert _location(again()) == f'/sso-test-complete?result={result}'
        assert [(e[0], e[3]) for e in _audit_since(app, floor)] == \
            [(sign_in_tests.AUDIT_ACTION, False)] * 2  # never a login_failure
        assert _session_of(app, client)[1]['username'] == 'admin'
        assert _no_account(app, case.username)

        for token in tokens:
            _age(app, token, timedelta(hours=23))
        _purge_by(app, client, tokens[0], how)
        assert all(_row(app, token) is not None for token in tokens)
        for token in tokens:
            _age(app, token, timedelta(hours=24, seconds=1))
        _purge_by(app, client, tokens[0], how)
        assert all(_row(app, token) is None for token in tokens)
    finally:
        case.cleanup()


def test_pkce_nonce_and_redirect_uri_are_the_logins(app, oidc_provider, monkeypatch):
    case = Case(app, oidc_provider, 'oauth2')
    try:
        idp = OIDCIdP(case.external_id, _oidc_userinfo(case))
        _install_idp(monkeypatch, idp)
        client = _admin_client(app)
        started, _state = _oidc_test(client, oidc_provider)
        query = parse_qs(urlsplit(started['url']).query)
        verifier = idp.token_requests[-1]['code_verifier']
        challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b'=').decode()
        assert query['code_challenge'] == [challenge] and query['code_challenge_method'] == ['S256']
        assert idp.nonces[-1] == query['nonce'][0]
        assert query['redirect_uri'] == [SP_BASE + OIDC_CALLBACK]
        assert idp.token_requests[-1]['redirect_uri'] == SP_BASE + OIDC_CALLBACK
    finally:
        case.cleanup()


def test_the_start_is_an_authenticated_csrf_protected_write(app, oidc_provider):
    from security.csrf import CSRFProtection
    path = f'/api/v2/sso/providers/{oidc_provider}/test-sign-in'
    assert not CSRFProtection.is_exempt(path)
    assert app.test_client().post(path, base_url=SP_BASE).status_code == 401
    assert app.test_client().get(path, base_url=SP_BASE).status_code in (404, 405)


def test_an_ldap_provider_has_no_sign_in_test(app, auth_client):
    with app.app_context():
        row = SSOProvider(name=_uid('sit-ldap'), provider_type='ldap', enabled=False,
                          ldap_server='ldap.example.test')
        db.session.add(row)
        db.session.commit()
        pid = row.id
    try:
        assert _admin_client(app).post(f'/api/v2/sso/providers/{pid}/test-sign-in',
                                       base_url=SP_BASE).status_code == 400
    finally:
        with app.app_context():
            db.session.delete(db.session.get(SSOProvider, pid))
            db.session.commit()


# -- invariant 7: no secret in the report, the audit or the log --------------------------

def test_no_secret_of_an_oidc_test_reaches_the_report_the_audit_or_the_log(
        app, oidc_provider, monkeypatch, caplog):
    case = Case(app, oidc_provider, 'oauth2')
    try:
        _set(app, oidc_provider, role_mapping=json.dumps({'admins': 'admin'}))  # a refusal, with diagnosis
        idp = OIDCIdP(case.external_id, _oidc_userinfo(case))
        _install_idp(monkeypatch, idp)
        client = _admin_client(app)
        floor = _top_audit(app)
        code = 'CODE-' + uuid.uuid4().hex
        caplog.clear()
        with caplog.at_level('DEBUG'):
            started = _start(client, oidc_provider)
            with app.app_context():
                pending = SSOSignInTest.query.filter_by(token=started['id']).one()
                assert pending.secret and 'code_verifier' not in pending.secret
            state = parse_qs(urlsplit(started['url']).query)['state'][0]
            assert _location(_oidc_callback(client, state, code=code)).endswith('result=done')
            report = _read_report(client, started['id'])
        assert report['code'] == 'sso_unmapped' and report['diagnosis']
        secrets = [SECRET_CLIENT, idp.access_token, idp.id_token, code,
                   idp.token_requests[-1]['code_verifier'], state]
        audit = json.dumps(_audit_since(app, floor))
        for secret in secrets:
            assert secret not in json.dumps(report)
            assert secret not in audit
            assert secret not in caplog.text, secret
        with app.app_context():
            assert SSOSignInTest.query.filter_by(token=started['id']).one().secret is None
    finally:
        case.cleanup()
        _reset_provider(app, oidc_provider)


def test_no_assertion_of_a_saml_test_reaches_the_report_the_audit_or_the_log(
        app, saml_provider, idp_signer, caplog):
    case = Case(app, saml_provider, 'saml')
    try:
        client = _admin_client(app)
        floor = _top_audit(app)
        caplog.clear()
        with caplog.at_level('DEBUG'):
            started = _start(client, saml_provider)
            answer = _saml_answer(case, idp_signer)(_request_id(started['url']))
            r = client.post(ACS, base_url=SP_BASE, data={'SAMLResponse': answer})
            assert _location(r).endswith('result=done')
            report = _read_report(client, started['id'])
        xml = base64.b64decode(answer).decode()
        signature = xml.split('<ds:SignatureValue>')[1].split('</ds:SignatureValue>')[0]
        audit = json.dumps(_audit_since(app, floor))
        for secret in (answer, signature.strip()[:40], answer[:80]):
            assert secret not in json.dumps(report)
            assert secret not in audit
            assert secret not in caplog.text
    finally:
        case.cleanup()


# -- invariant 8: traced apart -----------------------------------------------------------

def test_the_test_action_is_not_a_login_action():
    from services.audit._constants import CATEGORIES
    assert sign_in_tests.AUDIT_ACTION not in CATEGORIES['auth']
    assert sign_in_tests.AUDIT_ACTION not in LOGIN_ACTIONS


def test_the_login_counters_read_no_entry_of_a_test(app, oidc_provider, monkeypatch):
    """The dashboard, the PDF report (services/reporting) and the audit categories count
    audit rows by action name: a test writes none of login_success or login_failure."""
    case = Case(app, oidc_provider, 'oauth2')
    try:
        _install_idp(monkeypatch, OIDCIdP(case.external_id, _oidc_userinfo(case)))
        floor = _top_audit(app)
        _oidc_test(_admin_client(app), oidc_provider)
        with app.app_context():
            logs = AuditLog.query.filter(AuditLog.id > floor).all()
            counts = {}
            for log in logs:
                counts[log.action] = counts.get(log.action, 0) + 1
        # The admin login before the test counts once; the test adds no login of any kind.
        assert counts == {'login_success': 1, sign_in_tests.AUDIT_ACTION: 1}, counts
    finally:
        case.cleanup()


# -- invariant 10: maintenance -------------------------------------------------------------

def test_a_start_during_maintenance_is_refused_and_leaves_no_transaction(app, oidc_provider):
    from config.settings import Config
    from services import cluster_maintenance as cm
    client = _admin_client(app)
    with app.app_context():
        before = SSOSignInTest.query.count()
    view = cm.view_of(app)
    saved = Config.HA_MODE, cm.OBSERVE_TTL_SECONDS
    Config.HA_MODE, cm.OBSERVE_TTL_SECONDS = True, 3600
    now = utc_now()
    view.set({'token': 'tok', 'reason': cm.REASON_MANUAL, 'phase': cm.PHASE_MANUAL,
              'started_at': now, 'expires_at': now + timedelta(minutes=5), 'restored_at': None,
              'node_id': 'node-x', 'actor': 'admin'}, now)
    try:
        r = client.post(f'/api/v2/sso/providers/{oidc_provider}/test-sign-in', base_url=SP_BASE)
        assert r.status_code == 503 and r.headers['Retry-After'] == str(cm.RETRY_AFTER_SECONDS)
        assert client.get_cookie(sign_in_tests.BROWSER_COOKIE, domain=HOST,
                                 path=OIDC_CALLBACK) is None
    finally:
        view.row, view.observed, view.process_started, view.deadline = None, None, None, 0.0
        Config.HA_MODE, cm.OBSERVE_TTL_SECONDS = saved
    with app.app_context():
        assert SSOSignInTest.query.count() == before
