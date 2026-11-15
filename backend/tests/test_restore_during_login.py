"""A restore that commits while a login checks its credentials refuses the session it opens.

The session carries the epoch read as its request started, before any identity check
(auth/session_epoch.py): every door (password, second factor, passkey, LDAP, OIDC, SAML,
certificate) ends in begin_session, and each has its own test here.
"""
import uuid

import pytest
from sqlalchemy import event

from auth.session_epoch import EPOCH_KEY
from models import User, db
from tests.test_factor_change_sessions import (  # noqa: F401 (fixtures)
    PASSWORD, _cleanup, _code, _drop_session_table_from_metadata, _make_user, _post,
    _signed_in, nodes)
from tests.test_saml_strict_validation import (  # noqa: F401 (fixtures)
    _module_provider, idp_signer, provider)
from tests.test_sso_login_identity import ldap, oidc  # noqa: F401 (fixtures)


def _restore_meanwhile(monkeypatch, owner, name, advance=None, static=False):
    """Wrap ``owner.name``: on its first call a restore commits, then the check runs as before."""
    from auth.session_epoch import advance_epoch
    original = getattr(owner, name)
    done = []

    def checked(*args, **kwargs):
        if not done:
            done.append(True)
            (advance or advance_epoch)()
        return original(*args, **kwargs)
    monkeypatch.setattr(owner, name, staticmethod(checked) if static else checked)
    return done


def _password_step(c, user):
    return _post(c, '/api/v2/auth/login/password',
                 {'username': user['username'], 'password': PASSWORD})


@pytest.fixture
def user(app):
    info = _make_user(app)
    yield info
    _cleanup(app, info)


@pytest.fixture
def totp_user(app):
    info = _make_user(app, totp=True)
    yield info
    _cleanup(app, info)


def test_a_password_login_a_restore_overtakes_opens_no_valid_session(app, user, monkeypatch):
    done = _restore_meanwhile(monkeypatch, User, 'check_password')
    c = app.test_client()
    assert _password_step(c, user).status_code == 200
    assert done and not _signed_in(c)
    # The next login begins after the restore: its session holds
    again = app.test_client()
    assert _password_step(again, user).status_code == 200
    assert _signed_in(again)


def test_a_password_step_before_a_restore_cannot_finish_with_its_second_factor(
        app, totp_user, monkeypatch):
    done = _restore_meanwhile(monkeypatch, User, 'check_password')
    c = app.test_client()
    r = _password_step(c, totp_user)
    assert r.status_code == 200 and r.get_json()['data'].get('requires_2fa'), r.data
    assert done
    r = _post(c, '/api/v2/auth/login/2fa', {'code': _code(app, totp_user)})
    assert r.status_code == 401 and not _signed_in(c)


def test_a_totp_step_a_restore_overtakes_opens_no_valid_session(app, totp_user, monkeypatch):
    from auth import totp
    c = app.test_client()
    assert _password_step(c, totp_user).status_code == 200
    done = _restore_meanwhile(monkeypatch, totp, 'consume_totp')
    r = _post(c, '/api/v2/auth/login/2fa', {'code': _code(app, totp_user)})
    assert r.status_code == 200, r.data
    assert done and not _signed_in(c)


def test_a_security_key_step_a_restore_overtakes_opens_no_valid_session(app, monkeypatch):
    from services.webauthn_service import WebAuthnService
    from tests.test_webauthn_second_factor import SoftKey
    key_user = _make_user(app, key=SoftKey(), choice=True)
    try:
        c = app.test_client()
        r = _password_step(c, key_user)
        assert 'webauthn' in r.get_json()['data']['methods'], r.data
        challenge = _post(c, '/api/v2/auth/login/2fa/webauthn/options').get_json()['data'][
            'options']['challenge']
        done = _restore_meanwhile(monkeypatch, WebAuthnService, 'verify_authentication', static=True)
        r = _post(c, '/api/v2/auth/login/2fa/webauthn/verify',
                  {'response': key_user['key'].assert_(challenge)})
        assert r.status_code == 200, r.data
        assert done and not _signed_in(c)
    finally:
        _cleanup(app, key_user)


def test_a_passkey_login_a_restore_overtakes_opens_no_valid_session(app, user, monkeypatch):
    from services.webauthn_service import WebAuthnService
    monkeypatch.setattr(WebAuthnService, 'verify_authentication', staticmethod(
        lambda user_id, response, host, **_k: (True, '', db.session.get(User, user['id']))))
    done = _restore_meanwhile(monkeypatch, WebAuthnService, 'verify_authentication', static=True)
    c = app.test_client()
    r = _post(c, '/api/v2/auth/login/webauthn/verify',
              {'username': user['username'], 'response': {'id': 'x'}})
    assert r.status_code == 200, r.data
    assert done and not _signed_in(c)


# --- SSO --------------------------------------------------------------------

def test_an_ldap_login_a_restore_overtakes_opens_no_valid_session(app, ldap, monkeypatch):
    from api.v2.sso import ldap_routes
    name = f'ldap-{uuid.uuid4().hex[:8]}'
    monkeypatch.setattr(ldap_routes, '_ldap_authenticate_user', lambda _p, username, _pw: (
        {'username': username, 'dn': f'uid={username},dc=example', 'uid': f'uuid-{username}'}, None))
    done = _restore_meanwhile(monkeypatch, ldap_routes, '_ldap_authenticate_user')
    c = app.test_client()
    r = c.post('/api/v2/sso/ldap/login',
               json={'username': name, 'password': 'pw', 'provider_id': ldap.provider_id})
    assert r.status_code == 200, r.data
    assert done and not _signed_in(c)


def test_an_oidc_login_a_restore_overtakes_opens_no_valid_session(app, oidc, monkeypatch):
    from api.v2.sso import login_routes
    done = _restore_meanwhile(monkeypatch, login_routes, 'verify_id_token')
    name = f'oidc-{uuid.uuid4().hex[:8]}'
    location, verify = oidc({'sub': f'sub-{name}', 'preferred_username': name,
                             'email': f'{name}@corp.test'})
    assert '/login/sso-complete' in location, location
    assert done and verify.get('authenticated') is not True


@pytest.mark.usefixtures('drop_new_users')
def test_a_saml_login_a_restore_overtakes_opens_no_valid_session(app, provider, idp_signer,
                                                                  monkeypatch):
    from api.v2.sso import saml_sp
    from tests.test_saml_strict_validation import ACS, OK, SP_BASE, _response
    done = _restore_meanwhile(monkeypatch, saml_sp, 'consume_assertion')
    c = app.test_client()
    r = c.post(ACS, base_url=SP_BASE, data={'SAMLResponse': _response(idp_signer)})
    assert r.status_code == 302 and r.headers['Location'].endswith(OK), r.headers
    assert done
    assert c.get('/api/v2/account/profile', base_url=SP_BASE).status_code == 401


# --- Certificates -----------------------------------------------------------

def _certificate_signs_in(monkeypatch, app, uid):
    import middleware.mtls_middleware as mtls_middleware
    from services.mtls_auth_service import MTLSAuthService
    from tests.test_session_lifecycle import _cert_login
    monkeypatch.setattr(MTLSAuthService, 'is_mtls_enabled', staticmethod(lambda: True))
    monkeypatch.setattr(mtls_middleware, '_extract_certificate', lambda: {'serial': '0a'})
    _cert_login(monkeypatch, app, uid)
    return _restore_meanwhile(monkeypatch, MTLSAuthService, 'authenticate_certificate', static=True)


def _certificate_put_away(monkeypatch):
    """The browser stops presenting it: only the session it opened can sign the next call in."""
    from services.mtls_auth_service import MTLSAuthService
    monkeypatch.setattr(MTLSAuthService, 'is_mtls_enabled', staticmethod(lambda: False))


@pytest.mark.parametrize('path', ['/api/v2/account/profile', '/'])
def test_a_certificate_sign_in_a_restore_overtakes_opens_no_valid_session(
        app, user, monkeypatch, path):
    """On an API call and on the SPA shell, where the middleware signs in too."""
    done = _certificate_signs_in(monkeypatch, app, user['id'])
    c = app.test_client()
    c.get(path)
    assert done
    _certificate_put_away(monkeypatch)
    assert not _signed_in(c)


def test_a_certificate_login_route_a_restore_overtakes_opens_no_valid_session(
        app, user, monkeypatch):
    from services.certificate_parser import CertificateParser
    from tests.test_session_lifecycle import _cert_login
    monkeypatch.setattr(CertificateParser, 'extract_from_flask_native',
                        staticmethod(lambda peercert: {'serial': '0a'}))
    _cert_login(monkeypatch, app, user['id'])
    from services.mtls_auth_service import MTLSAuthService
    done = _restore_meanwhile(monkeypatch, MTLSAuthService, 'authenticate_certificate', static=True)
    c = app.test_client()
    r = c.post('/api/v2/auth/login/mtls', environ_base={'peercert': {'subject': ()}})
    assert r.status_code == 200, r.data
    assert done and not _signed_in(c)


# --- Two nodes --------------------------------------------------------------

def test_a_restore_by_one_node_refuses_the_login_another_node_was_serving(nodes, monkeypatch):
    """Node A commits the restore while node B checks the password; B's session is refused
    on both nodes, and B's next login holds."""
    from auth.session_epoch import advance_epoch
    first_node, second_node = nodes
    account = _make_user(first_node)

    def on_the_first_node():
        db.session.commit()  # B's read transaction ends, as between two statements
        with first_node.app_context():
            advance_epoch()
    try:
        done = _restore_meanwhile(monkeypatch, User, 'check_password', advance=on_the_first_node)
        c = second_node.test_client()
        assert _password_step(c, account).status_code == 200
        assert done and not _signed_in(c)
        cookie = c.get_cookie('session')
        stale = first_node.test_client()
        stale.set_cookie('session', cookie.value if cookie else '')
        assert not _signed_in(stale)
        again = second_node.test_client()
        assert _password_step(again, account).status_code == 200
        assert _signed_in(again)
    finally:
        _cleanup(first_node, account)


# --- What the read costs, and what it never refuses -------------------------

class _Statements:
    """SQL statements the engine runs, and those that read the epoch."""

    def __init__(self, engine):
        self.all, self.epoch = 0, 0
        self.engine = engine

    def __call__(self, conn, cursor, statement, parameters, context, executemany):
        self.all += 1
        if EPOCH_KEY in repr(parameters):
            self.epoch += 1

    def __enter__(self):
        event.listen(self.engine, 'before_cursor_execute', self)
        return self

    def __exit__(self, *exc):
        event.remove(self.engine, 'before_cursor_execute', self)


def _statements(app, call):
    with app.app_context():
        engine = db.engine
    with _Statements(engine) as seen:
        call()
    return seen


NO_SESSION_PATHS = [
    ('get', '/assets/index-abc123.js'), ('get', '/favicon.ico'), ('get', '/'),
    ('get', '/certificates'), ('get', '/api/v2/health'), ('get', '/health/ready'),
    ('post', '/ocsp'), ('get', '/cgi-bin/pkiclient.exe?operation=GetCACaps'),
]


@pytest.mark.parametrize('method,path', NO_SESSION_PATHS)
def test_a_request_that_opens_no_session_never_reads_the_epoch(app, method, path):
    c = app.test_client()
    seen = _statements(app, lambda: getattr(c, method)(path))
    assert seen.epoch == 0, (path, seen.all)


@pytest.mark.parametrize('path', ['/assets/index-abc123.js', '/favicon.ico', '/', '/certificates'])
def test_files_and_the_shell_are_served_when_the_epoch_cannot_be_read(app, monkeypatch, path):
    from auth import session_epoch

    def away():
        raise RuntimeError('database away')
    monkeypatch.setattr(session_epoch, 'current_epoch', away)
    assert app.test_client().get(path).status_code < 500


def test_a_login_reads_the_epoch_once(app, user):
    c = app.test_client()
    seen = _statements(app, lambda: _password_step(c, user))
    assert seen.epoch == 1, seen.all
    assert _signed_in(c)


def test_a_restore_during_a_request_that_opens_no_session_refuses_no_later_login(app, user):
    """The epoch read at a request's start is that request's only: the next login reads its own."""
    from auth.session_epoch import advance_epoch
    c = app.test_client()
    assert c.get('/api/v2/auth/verify').status_code in (200, 401)
    with app.app_context():
        advance_epoch()
    assert _password_step(c, user).status_code == 200
    assert _signed_in(c)
