"""What each login door says when it refuses, and why they differ (DUP-SEC-008).

The password door merges "no such account" and "account deactivated" into one
401 "Invalid credentials", and answers before the password is checked. The LDAP
door names the reason — 403 "This account has been disabled", 403 "Access
denied: you are not a member of the required group(s)" — and answers only after
the directory accepted the user's own bind.

That is not a duplication waiting to be reconciled. Merging the LDAP messages
into the generic one leaves an operator guessing why a correct password is
refused; moving them ahead of the bind turns them into an account oracle. This
file pins both halves so either change fails here rather than in production.
"""
import inspect
import uuid
from datetime import timedelta

import pytest

from models import db, User
from models.sso import SSOProvider
from utils.datetime_utils import utc_now

PASSWORD = 'Pinned-Passw0rd!'


@pytest.fixture
def ldap_provider(app):
    with app.app_context():
        provider = SSOProvider(
            name=f'pinned-ldap-{uuid.uuid4().hex[:6]}', provider_type='ldap', enabled=True,
            ldap_server='ldap.example.test', ldap_port=389, ldap_base_dn='dc=example,dc=test',
            ldap_user_filter='(uid={username})', ldap_username_attr='uid',
            ldap_email_attr='mail', ldap_fullname_attr='cn',
        )
        db.session.add(provider)
        db.session.commit()
        provider_id = provider.id
    yield provider_id
    with app.app_context():
        row = db.session.get(SSOProvider, provider_id)
        if row is not None:
            db.session.delete(row)
            db.session.commit()


@pytest.fixture
def local_user(app):
    created = []

    def _make(*, active=True, locked=False):
        username = f'pin{uuid.uuid4().hex[:8]}'
        with app.app_context():
            user = User(username=username, email=f'{username}@example.test', role='viewer')
            user.set_password(PASSWORD)
            user.active = active
            if locked:
                user.locked_until = utc_now() + timedelta(minutes=30)
                user.failed_logins = 99
            db.session.add(user)
            db.session.commit()
        created.append(username)
        return username

    yield _make
    with app.app_context():
        User.query.filter(User.username.in_(created)).delete(synchronize_session=False)
        db.session.commit()


def _bind_succeeds(monkeypatch, username, error=None):
    """The directory accepted this user's own password."""
    import api.v2.sso.ldap_routes as ldap_routes

    def _fake(provider, user, password):
        if error:
            return None, error
        return {
            'dn': f'uid={username}', 'uid': username, 'username': username,
            'email': f'{username}@example.test', 'fullname': username, 'groups': [],
        }, None

    monkeypatch.setattr(ldap_routes, '_ldap_authenticate_user', _fake)


def _login(client, username, path, provider_id=None):
    payload = {'username': username, 'password': PASSWORD}
    if provider_id is not None:
        payload['provider_id'] = provider_id
    response = client.post(path, json=payload)
    return response.status_code, (response.get_json() or {}).get('message')


def test_an_unknown_name_gets_the_same_answer_at_both_doors(
    client, ldap_provider, monkeypatch
):
    """Before anything is proved, neither door may distinguish an account."""
    unknown = f'nosuch{uuid.uuid4().hex[:8]}'
    _bind_succeeds(monkeypatch, unknown, error='Invalid credentials')

    assert _login(client, unknown, '/api/v2/auth/login/password') == (
        401, 'Invalid credentials')
    assert _login(client, unknown, '/api/v2/sso/ldap/login', ldap_provider) == (
        401, 'Invalid credentials')


def test_the_password_door_hides_a_deactivated_account(client, local_user):
    """It answers before the password is checked, so it may not say more."""
    username = local_user(active=False)
    assert _login(client, username, '/api/v2/auth/login/password') == (
        401, 'Invalid credentials')


def test_the_ldap_door_names_a_deactivated_account(
    client, local_user, ldap_provider, monkeypatch
):
    """It answers after the bind, so it may say why."""
    username = local_user(active=False)
    _bind_succeeds(monkeypatch, username)
    assert _login(client, username, '/api/v2/sso/ldap/login', ldap_provider) == (
        403, 'This account has been disabled')


def test_the_ldap_door_names_a_directory_disabled_account(
    client, local_user, ldap_provider, monkeypatch
):
    username = local_user()
    _bind_succeeds(monkeypatch, username, error='account_disabled')
    assert _login(client, username, '/api/v2/sso/ldap/login', ldap_provider) == (
        403, 'This account has been disabled in Active Directory / LDAP')


def test_the_ldap_door_names_a_missing_group(
    client, local_user, ldap_provider, monkeypatch
):
    username = local_user()
    _bind_succeeds(monkeypatch, username, error='group_denied')
    assert _login(client, username, '/api/v2/sso/ldap/login', ldap_provider) == (
        403, 'Access denied: you are not a member of the required group(s)')


def test_a_wrong_ldap_password_says_nothing_more(
    client, local_user, ldap_provider, monkeypatch
):
    username = local_user()
    _bind_succeeds(monkeypatch, username, error='Invalid credentials')
    assert _login(client, username, '/api/v2/sso/ldap/login', ldap_provider) == (
        401, 'Invalid credentials')


def test_each_door_keeps_its_own_lockout_wording(client, local_user, ldap_provider,
                                                 monkeypatch):
    # The password door has not checked the password yet: a locked account
    # answers like an unknown name, or the status would reveal it exists.
    locked = local_user(locked=True)
    assert _login(client, locked, '/api/v2/auth/login/password') == \
        _login(client, f'nobody-{uuid.uuid4().hex[:8]}', '/api/v2/auth/login/password') == \
        (401, 'Invalid credentials')

    # The LDAP door checks the lock before the bind: same answer as a wrong password.
    locked_ldap = local_user(locked=True)
    _bind_succeeds(monkeypatch, locked_ldap)
    assert _login(client, locked_ldap, '/api/v2/sso/ldap/login', ldap_provider) == (
        401, 'Invalid credentials')


def test_the_ldap_door_hides_a_locked_account(client, local_user, ldap_provider, monkeypatch):
    locked = local_user(locked=True)
    unknown = f'nobody-{uuid.uuid4().hex[:8]}'
    _bind_succeeds(monkeypatch, unknown, error='Invalid credentials')
    door = '/api/v2/sso/ldap/login'
    assert _login(client, locked, door, ldap_provider) == \
        _login(client, unknown, door, ldap_provider) == (401, 'Invalid credentials')
    missing = 2_000_000_000  # no such provider
    assert _login(client, locked, door, missing) == _login(client, unknown, door, missing) == \
        (400, 'No LDAP provider configured')


def test_a_locked_ldap_refusal_is_audited(app, client, local_user, ldap_provider, monkeypatch):
    from models import AuditLog

    locked = local_user(locked=True)
    _bind_succeeds(monkeypatch, locked)
    assert _login(client, locked, '/api/v2/sso/ldap/login', ldap_provider)[0] == 401
    with app.app_context():
        assert AuditLog.query.filter_by(action='login_failure', username=locked).filter(
            AuditLog.details.contains('account locked')).count() == 1


def test_the_named_reasons_are_decided_after_the_bind():
    """The property that makes them safe to say out loud.

    If ``account_disabled`` or ``group_denied`` were ever returned before
    ``user_conn.bind()``, an unauthenticated caller could read an account's
    state out of a 403. Checked on the source, because no amount of mocking
    the bind can demonstrate an ordering.
    """
    from api.v2.sso.connection_tests import _ldap_authenticate_user

    source = inspect.getsource(_ldap_authenticate_user)
    bind = source.index('user_conn.bind()')
    for reason in ("'account_disabled'", "'group_denied'"):
        assert source.index(reason) > bind, f'{reason} is decided before the bind'
