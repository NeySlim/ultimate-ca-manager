"""The users API no longer returns `mfa_enabled`.

The column was never set by anything, so the user detail showing it said 2FA
was off for everyone. The 2FA state is `two_factor_enabled` / `totp_enabled`.
"""
import uuid

from models import User, db


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
