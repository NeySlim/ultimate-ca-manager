"""The users API no longer returns `mfa_enabled`.

The column was never set by anything, so the user detail showing it said 2FA
was off for everyone. The 2FA state is `two_factor_enabled` / `totp_enabled`.
"""
import uuid

from models import User, db
from tests.test_webauthn_second_factor import enforce_2fa, make_user  # noqa: F401 (fixtures)


def _user(app, confirmed):
    with app.app_context():
        u = User(username=f'mfa_{uuid.uuid4().hex[:8]}', email=f'{uuid.uuid4().hex[:8]}@test.local', role='viewer')
        u.set_password('Tq7#vLm2pXw9')
        u.totp_confirmed = confirmed
        db.session.add(u)
        db.session.commit()
        return u.id


def _get(auth_client, user_id):
    r = auth_client.get(f'/api/v2/users/{user_id}')
    assert r.status_code == 200, r.data
    return r.get_json()['data']


def test_mfa_enabled_is_not_returned(app, auth_client):
    assert 'mfa_enabled' not in _get(auth_client, _user(app, False))


def test_two_factor_state_follows_totp(app, auth_client):
    assert _get(auth_client, _user(app, True))['two_factor_enabled'] is True
    assert _get(auth_client, _user(app, False))['two_factor_enabled'] is False


def _state(app, auth_client, username):
    with app.app_context():
        uid = User.query.filter_by(username=username).first().id
    listed = auth_client.get(f'/api/v2/users?search={username}').get_json()['data']
    row = next(u for u in listed if u['id'] == uid)
    return _get(auth_client, uid)['two_factor_enabled'], row['two_factor_enabled']


def test_a_key_turned_on_as_second_factor_counts(app, auth_client, make_user):
    from tests.test_webauthn_second_factor_optin import _password_session, _put
    username, _key, _ = make_user(totp=False)
    assert _state(app, auth_client, username) == (False, False)  # a key alone asks for nothing
    assert _put(_password_session(app, username), {'enabled': True}).status_code == 200
    assert _state(app, auth_client, username) == (True, True)


def test_a_key_under_enforced_2fa_counts(app, auth_client, make_user, enforce_2fa):
    username, _key, _ = make_user(totp=False)
    assert _state(app, auth_client, username) == (True, True)
