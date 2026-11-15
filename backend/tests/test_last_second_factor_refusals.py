"""Every route that removes or turns off a second factor refuses the last one of required 2FA.

The user's own routes answer alike (403, reason last_second_factor); an
administrator's answer is 409 with the same reason, as it can be confirmed.
"""
import pyotp
import pytest

from models import User, db
from models.webauthn import WebAuthnCredential
from tests.conftest import get_json
from tests.test_2fa_security_key_enforcement import _key_ids, _key_session
from tests.test_webauthn_second_factor import (  # noqa: F401 (fixtures)
    PASSWORD, enforce_2fa, make_user, _password, _post,
)


def _set_choice(app, username, on=True):
    with app.app_context():
        user = User.query.filter_by(username=username).first()
        user.webauthn_2fa = on
        db.session.commit()


def _state(app, username):
    with app.app_context():
        user = User.query.filter_by(username=username).first()
        keys = WebAuthnCredential.query.filter_by(user_id=user.id, enabled=True).count()
        return bool(user.totp_confirmed), bool(user.webauthn_2fa), keys


def _totp_session(app, username, secret):
    c = app.test_client()
    _password(c, username)
    assert _post(c, '/api/v2/auth/login/2fa', {'code': pyotp.TOTP(secret).now()}).status_code == 200
    return c


def _key_only(app, make_user):
    username, key, _ = make_user(totp=False)
    _set_choice(app, username)
    return username, _key_session(app, username, key), _key_ids(app, username)[0]


def _disable_totp(app, make_user):
    username, _none, secret = make_user(key=False)
    c = _totp_session(app, username, secret)
    return username, lambda: _post(c, '/api/v2/account/2fa/disable', {'code': pyotp.TOTP(secret).now()})


def _delete_key(app, make_user):
    username, c, key_id = _key_only(app, make_user)
    return username, lambda: c.delete(f'/api/v2/webauthn/credentials/{key_id}')


def _toggle_key_off(app, make_user):
    username, c, key_id = _key_only(app, make_user)
    return username, lambda: _post(c, f'/api/v2/webauthn/credentials/{key_id}/toggle', {'enabled': False})


def _key_choice_off(app, make_user):
    username, c, _key_id = _key_only(app, make_user)
    return username, lambda: c.put('/api/v2/account/2fa/webauthn',
                                   json={'enabled': False, 'password': PASSWORD})


OWN_ROUTES = {
    'disable-totp': _disable_totp,
    'delete-key': _delete_key,
    'toggle-key-off': _toggle_key_off,
    'key-second-factor-off': _key_choice_off,
}


@pytest.mark.parametrize('route', sorted(OWN_ROUTES))
def test_own_routes_refuse_the_last_factor_alike(app, make_user, enforce_2fa, route):
    username, call = OWN_ROUTES[route](app, make_user)
    before = _state(app, username)
    r = call()
    assert r.status_code == 403, r.data
    assert get_json(r)['details'] == {'reason': 'last_second_factor'}
    assert _state(app, username) == before


@pytest.mark.parametrize('method', ['delete', 'patch'])
def test_admin_routes_refuse_the_last_factor_with_the_same_reason(
        app, make_user, enforce_2fa, auth_client, method):
    username, _key, _ = make_user(totp=False)
    key_id, = _key_ids(app, username)
    with app.app_context():
        uid = User.query.filter_by(username=username).first().id
    url = f'/api/v2/users/{uid}/webauthn/{key_id}'
    r = auth_client.delete(url) if method == 'delete' else auth_client.patch(url, json={'enabled': False})
    assert r.status_code == 409, r.data
    assert get_json(r)['details'] == {'reason': 'last_second_factor'}


def test_the_key_choice_goes_when_totp_remains(app, make_user, enforce_2fa):
    username, key, _ = make_user()
    _set_choice(app, username)
    c = _key_session(app, username, key)
    r = c.put('/api/v2/account/2fa/webauthn', json={'enabled': False, 'password': PASSWORD})
    assert r.status_code == 200, r.data
    assert _state(app, username) == (True, False, 1)


def test_the_key_choice_is_the_users_own_without_enforcement(app, make_user):
    username, c, _key_id = _key_only(app, make_user)
    r = c.put('/api/v2/account/2fa/webauthn', json={'enabled': False, 'password': PASSWORD})
    assert r.status_code == 200, r.data
    assert _state(app, username) == (False, False, 1)


def test_a_refused_key_choice_does_not_use_up_a_password_attempt(app, make_user, enforce_2fa):
    from models.second_factor_failure import SecondFactorFailure
    username, c, _key_id = _key_only(app, make_user)
    r = c.put('/api/v2/account/2fa/webauthn', json={'enabled': False, 'password': 'Wrong-Pass-1!'})
    assert r.status_code == 403 and get_json(r)['details'] == {'reason': 'last_second_factor'}
    with app.app_context():
        uid = User.query.filter_by(username=username).first().id
        assert db.session.get(SecondFactorFailure, ('session_pw', str(uid))) is None


def test_the_key_choice_is_checked_again_under_the_lock(app, make_user, enforce_2fa, monkeypatch):
    """TOTP disabled while the password was being checked: the re-check refuses."""
    import api.v2.account.twofa as twofa
    username, key, _ = make_user()
    _set_choice(app, username)
    c = _key_session(app, username, key)
    real = twofa.check_session_password

    def totp_goes_meanwhile(user, password, wrong):
        answer = real(user, password, wrong)
        db.session.execute(db.update(User).where(User.id == user.id)
                           .values(totp_confirmed=False, totp_secret=None))
        db.session.commit()
        return answer

    monkeypatch.setattr(twofa, 'check_session_password', totp_goes_meanwhile)
    r = c.put('/api/v2/account/2fa/webauthn', json={'enabled': False, 'password': PASSWORD})
    assert r.status_code == 403 and get_json(r)['details'] == {'reason': 'last_second_factor'}
    assert _state(app, username) == (False, True, 1)
