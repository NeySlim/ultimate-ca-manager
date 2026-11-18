"""Every authenticated-session response carries the same session fields.

Six endpoints describe the same thing to the SPA: the five login routes
(password, 2FA, mTLS, WebAuthn, LDAP) and ``GET /api/v2/auth/verify``. They
were six hand-written dicts, and they had drifted:
``force_password_change`` was on the five login responses and missing from
``/verify``.

That gap is not cosmetic. ``AuthContext.checkSession`` calls ``/verify`` on
every mount, so a page reload replaced the login response with one that had
no opinion about the forced change, and the modal — which is the whole
enforcement — went away. The SSO flows never saw it at all: they redirect to
``/login/sso-complete`` and the SPA builds its state from ``/verify`` alone.
"""
from __future__ import annotations

import pytest

from models import User, UserSSOIdentity, db

# The session fields that belong to every authenticated-session response.
SESSION_FIELDS = frozenset({
    'user', 'role', 'permissions', 'auth_method', 'csrf_token',
    'force_password_change', 'timezone', 'date_format', 'show_time',
})


@pytest.fixture
def forced_admin(app):
    """The admin account with a pending forced password change."""
    with app.app_context():
        user = User.query.filter_by(username='admin').first()
        previous = user.force_password_change
        user.force_password_change = True
        db.session.commit()
    yield
    with app.app_context():
        user = User.query.filter_by(username='admin').first()
        user.force_password_change = previous
        db.session.commit()


def _login(client):
    return client.post('/api/v2/auth/login',
                       json={'username': 'admin', 'password': 'changeme123'})


class TestVerifyReportsForcedPasswordChange:
    def test_verify_matches_login(self, app, forced_admin):
        """Same session, same user: both must say the change is forced."""
        client = app.test_client()

        login = _login(client)
        assert login.status_code == 200, login.get_data(as_text=True)
        login_data = login.get_json()['data']
        assert login_data['force_password_change'] is True

        verify = client.get('/api/v2/auth/verify')
        assert verify.status_code == 200
        verify_data = verify.get_json()['data']
        assert verify_data['authenticated'] is True
        assert verify_data['force_password_change'] is True, (
            '/verify dropped the forced-change state, so reloading the page '
            'skips the modal that enforces it')

    def test_verify_says_false_when_nothing_is_forced(self, app):
        client = app.test_client()
        with app.app_context():
            user = User.query.filter_by(username='admin').first()
            user.force_password_change = False
            db.session.commit()

        assert _login(client).status_code == 200
        data = client.get('/api/v2/auth/verify').get_json()['data']
        assert data['force_password_change'] is False


class TestSessionFieldParity:
    def test_login_and_verify_agree_on_the_session_fields(self, app):
        client = app.test_client()
        login_data = _login(client).get_json()['data']
        verify_data = client.get('/api/v2/auth/verify').get_json()['data']

        missing_from_login = SESSION_FIELDS - set(login_data)
        missing_from_verify = SESSION_FIELDS - set(verify_data)
        assert not missing_from_login, f'login is missing {missing_from_login}'
        assert not missing_from_verify, f'/verify is missing {missing_from_verify}'

        for field in ('role', 'permissions', 'force_password_change',
                      'timezone', 'date_format', 'show_time'):
            assert login_data[field] == verify_data[field], (
                f'{field} differs between login and /verify')
        # A reloaded page knows the user only from /verify (#386: the test
        # email defaults to the signed-in user's address)
        assert verify_data['user']['email'] == login_data['user']['email']

    def test_every_login_route_answers_the_session_fields(self, app, monkeypatch):
        """Password, 2FA and LDAP sign-ins carry the fields /verify carries, with
        the forced change of the account that signed in."""
        import uuid

        import pyotp

        import api.v2.sso.ldap_routes as ldap_routes
        from models.sso import SSOProvider, SSOSession
        from models.user import UserSession

        tag = uuid.uuid4().hex[:8]
        password = 'Parity-Login-Pass1!'
        with app.app_context():
            totp = User(username=f'parity2fa{tag}', email=f'parity2fa{tag}@example.test',
                        role='viewer', active=True, totp_secret=pyotp.random_base32(),
                        totp_confirmed=True, force_password_change=True)
            totp.set_password(password)
            provider = SSOProvider(
                name=f'parity-ldap-{tag}', provider_type='ldap', enabled=True,
                ldap_server='ldap.example.test', ldap_port=389, ldap_base_dn='dc=example,dc=test',
                ldap_user_filter='(uid={username})', ldap_username_attr='uid',
                ldap_email_attr='mail', ldap_fullname_attr='cn')
            db.session.add_all([totp, provider])
            db.session.commit()
            secret, provider_id = totp.totp_secret, provider.id

        ldap_name = f'parityldap{tag}'
        monkeypatch.setattr(ldap_routes, '_ldap_authenticate_user', lambda p, u, pw, before_bind=None: ({
            'dn': f'uid={ldap_name}', 'uid': ldap_name, 'username': ldap_name,
            'email': f'{ldap_name}@example.test', 'fullname': ldap_name, 'groups': []}, None))
        try:
            client = app.test_client()
            assert client.post('/api/v2/auth/login/password', json={
                'username': totp.username, 'password': password}).status_code == 200
            two_fa = client.post('/api/v2/auth/login/2fa',
                                 json={'code': pyotp.TOTP(secret).now()})
            ldap = app.test_client().post('/api/v2/sso/ldap/login', json={
                'username': ldap_name, 'password': 'pw', 'provider_id': provider_id})
            for name, response, forced in (('2fa', two_fa, True), ('ldap', ldap, False)):
                assert response.status_code == 200, (name, response.data)
                data = response.get_json()['data']
                assert SESSION_FIELDS <= set(data), (name, SESSION_FIELDS - set(data))
                assert data['force_password_change'] is forced, name
        finally:
            with app.app_context():
                ids = [u.id for u in User.query.filter(
                    User.username.in_([totp.username, ldap_name]))]
                UserSession.query.filter(UserSession.user_id.in_(ids)).delete(
                    synchronize_session=False)
                # SQLite applies no ON DELETE CASCADE: the attachments go first
                UserSSOIdentity.query.filter(db.or_(UserSSOIdentity.user_id.in_(ids),
                                                    UserSSOIdentity.provider_id == provider_id)).delete(
                    synchronize_session=False)
                SSOSession.query.filter_by(provider_id=provider_id).delete()
                User.query.filter(User.id.in_(ids)).delete(synchronize_session=False)
                SSOProvider.query.filter_by(id=provider_id).delete()
                db.session.commit()


class TestPreservedContract:
    def test_verify_keeps_its_own_fields(self, app):
        client = app.test_client()
        assert _login(client).status_code == 200
        data = client.get('/api/v2/auth/verify').get_json()['data']
        for field in ('authenticated', 'user_id', 'must_enroll_2fa',
                      'session_timeout', 'preferences'):
            assert field in data, f'/verify lost {field}'
        # /verify returns a narrower user block than login does, plus the
        # email a reloaded page needs (#386).
        assert set(data['user']) == {'id', 'username', 'email', 'role'}

    def test_login_keeps_the_wide_user_block(self, app):
        client = app.test_client()
        data = _login(client).get_json()['data']
        assert set(data['user']) == {
            'id', 'username', 'email', 'full_name', 'role', 'active'}

    def test_unauthenticated_verify_is_unchanged(self, app):
        client = app.test_client()
        r = client.get('/api/v2/auth/verify')
        assert r.status_code == 200
        data = r.get_json()['data']
        assert data['authenticated'] is False
        assert 'force_password_change' not in data
