"""Adding a credential that signs in alone (a passkey, an mTLS certificate) proves the
account holder again (OWASP ASVS 4.0.3 V3.7.1): the password, or for an account
without one its authenticator code; forced enrolment, just past the password, is exempt."""
import json

import pyotp
import pytest

from models import User, db

pytestmark = pytest.mark.usefixtures('drop_new_users')

PASSWORD = 'TestPass123!'
ROUTES = ['/api/v2/webauthn/register/options', '/api/v2/mtls/certificates',
          '/api/v2/mtls/enroll', '/api/v2/mtls/enroll-import', '/api/v2/mtls/assign']


def _post(client, url, body):
    return client.post(url, data=json.dumps(body), content_type='application/json')


def _signed_in(app, create_user, username, role):
    create_user(username=username, role=role)
    client = app.test_client()
    r = _post(client, '/api/v2/auth/login', {'username': username, 'password': PASSWORD})
    assert r.status_code == 200, r.data
    return client


@pytest.fixture(scope='module')
def clients(app, create_user):
    return {role: _signed_in(app, create_user, f'reauth_{role}', role)
            for role in ('auditor', 'operator', 'admin')}


def _reauth(r):
    return ((r.get_json() or {}).get('details') or {}).get('reauth')


@pytest.mark.parametrize('route', ROUTES)
@pytest.mark.parametrize('role', ['auditor', 'operator', 'admin'])
def test_no_password_is_refused(clients, role, route):
    r = _post(clients[role], route, {'name': 'probe'})
    assert r.status_code == 403, r.data
    if role == 'auditor' and route == '/api/v2/mtls/certificates':
        assert _reauth(r) is None  # its scope is refused before any password
    else:
        assert _reauth(r) == 'password', r.data


@pytest.mark.parametrize('route', ROUTES)
@pytest.mark.parametrize('role', ['operator', 'admin'])
def test_a_wrong_password_is_refused(app, create_user, role, route):
    # An account per case: failures count towards a lock
    c = _signed_in(app, create_user, f'reauth_wrong_{role}_{ROUTES.index(route)}', role)
    r = _post(c, route, {'password': 'not-the-password'})
    assert r.status_code == 403, r.data
    assert r.get_json()['message'] == 'Invalid password'


@pytest.mark.parametrize('route', ROUTES)
@pytest.mark.parametrize('role', ['auditor', 'operator', 'admin'])
def test_the_password_lets_the_route_go_on(clients, role, route):
    r = _post(clients[role], route, {'password': PASSWORD})
    if role == 'auditor' and route == '/api/v2/mtls/certificates':
        assert r.status_code == 403  # no write:user_certificates
    else:
        # Past the proof: what follows refuses for its own reasons (no CA, no PEM...)
        assert _reauth(r) is None and r.status_code != 401, r.data
    if route == ROUTES[0]:
        assert r.status_code == 200, r.data
        assert r.get_json()['data']['challenge']


def test_forced_enrolment_registers_a_key_without_asking_again(app, create_user):
    c = _signed_in(app, create_user, 'reauth_enrolling', 'viewer')
    with c.session_transaction() as s:
        s['must_enroll_2fa'] = True
    r = _post(c, ROUTES[0], {})
    assert r.status_code == 200, r.data


@pytest.fixture
def provider_only(app, create_user):
    """An account its provider alone opens: no local password."""
    from api.v2.sso.account_state import SSO_NO_PASSWORD

    def _make(username, totp=False):
        c = _signed_in(app, create_user, username, 'operator')
        secret = pyotp.random_base32() if totp else None
        with app.app_context():
            user = User.query.filter_by(username=username).first()
            user.password_hash = SSO_NO_PASSWORD
            user.totp_secret, user.totp_confirmed = secret, bool(totp)
            user.totp_last_step = None
            db.session.commit()
        return c, secret
    return _make


def test_an_account_without_a_password_answers_with_its_code(provider_only):
    c, secret = provider_only('reauth_sso_totp', totp=True)
    r = _post(c, ROUTES[0], {'password': PASSWORD})
    assert r.status_code == 403 and _reauth(r) == 'code', r.data
    r = _post(c, ROUTES[0], {'code': '000000' if pyotp.TOTP(secret).now() != '000000' else '111111'})
    assert r.status_code == 403 and _reauth(r) == 'code', r.data
    code = pyotp.TOTP(secret).now()
    r = _post(c, ROUTES[0], {'code': code})
    assert r.status_code == 200, r.data
    # A code counts once
    r = _post(c, ROUTES[0], {'code': code})
    assert r.status_code == 403, r.data


def test_an_account_without_password_nor_code_is_refused(provider_only):
    c, _ = provider_only('reauth_sso_bare')
    for route in ROUTES:
        r = _post(c, route, {'password': PASSWORD, 'code': '123456'})
        assert r.status_code == 403, (route, r.data)
        assert _reauth(r) == 'none', (route, r.data)


def test_the_profile_says_which_proof_the_account_gives(app, clients, provider_only):
    assert clients['operator'].get('/api/v2/account/profile').get_json()['data']['has_local_password'] is True
    c, _ = provider_only('reauth_sso_profile')
    assert c.get('/api/v2/account/profile').get_json()['data']['has_local_password'] is False
