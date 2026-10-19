"""A security key turned on as second factor without enforced 2FA.

The user's own switch: once on, a password login asks for the key, removing
the last factor is refused, and lifting enforcement later keeps a key that
became the account's second factor. Passwordless-only users are unaffected.
"""
import pyotp
import pytest
from models import User, db
from tests.conftest import get_json
from tests.test_2fa_security_key_enforcement import _key_ids, _key_session, _register
from tests.test_webauthn_second_factor import (  # noqa: F401 (fixtures)
    PASSWORD, SoftKey, enforce_2fa, make_user, _password, _post,
)


def _put(c, body):
    return c.put('/api/v2/account/2fa/webauthn', json=body)


def _password_session(app, username):
    c = app.test_client()
    data = get_json(_password(c, username))['data']
    assert not data.get('requires_2fa')
    return c


def _flag(app, username):
    with app.app_context():
        return User.query.filter_by(username=username).first().webauthn_2fa


def _requires(app, username):
    return get_json(_password(app.test_client(), username))['data'].get('methods')


def test_turning_the_key_on_makes_it_the_second_factor(app, make_user):
    username, key, _ = make_user(totp=False)
    c = _password_session(app, username)
    assert _put(c, {'enabled': True}).status_code == 200
    assert _requires(app, username) == ['webauthn']
    assert get_json(c.get('/api/v2/account/profile'))['data']['two_factor_methods'] == ['webauthn']
    _key_session(app, username, key)


def test_no_key_no_switch(app, make_user):
    username, _none, _ = make_user(totp=False, key=False)
    c = _password_session(app, username)
    assert _put(c, {'enabled': True}).status_code == 400
    assert _flag(app, username) is False


def test_turning_it_off_needs_the_password(app, make_user):
    username, key, _ = make_user(totp=False)
    c = _password_session(app, username)
    _put(c, {'enabled': True})
    c = _key_session(app, username, key)
    assert _put(c, {'enabled': False, 'password': 'wrong'}).status_code == 403
    assert _put(c, {'enabled': False}).status_code == 403
    assert _put(c, {'enabled': False, 'password': PASSWORD}).status_code == 200
    assert not _requires(app, username)


def test_switch_value_must_be_boolean(app, make_user):
    username, _key, _ = make_user(totp=False)
    c = _password_session(app, username)
    assert _put(c, {'enabled': 'yes'}).status_code == 400


def test_last_key_of_a_switched_on_account_stays(app, make_user):
    username, key, _ = make_user(totp=False)
    _put(_password_session(app, username), {'enabled': True})
    c = _key_session(app, username, key)
    key_id, = _key_ids(app, username)
    assert c.delete(f'/api/v2/webauthn/credentials/{key_id}').status_code == 403
    assert _post(c, f'/api/v2/webauthn/credentials/{key_id}/toggle', {'enabled': False}).status_code == 403
    assert _put(c, {'enabled': False, 'password': PASSWORD}).status_code == 200
    assert c.delete(f'/api/v2/webauthn/credentials/{key_id}').status_code == 200


def test_key_enrolled_under_enforcement_survives_its_lifting(app, make_user, enforce_2fa):
    username, _none, _ = make_user(totp=False, key=False)
    c = app.test_client()
    _password(c, username)
    assert _register(c, SoftKey()).status_code == 200
    assert _flag(app, username) is True
    with app.app_context():
        from models import SystemConfig
        SystemConfig.query.filter_by(key='enforce_2fa').delete()
        db.session.commit()
    assert _requires(app, username) == ['webauthn']


def test_totp_dropped_under_enforcement_keeps_the_key(app, make_user, enforce_2fa):
    username, key, secret = make_user()
    c = _key_session(app, username, key)
    assert _post(c, '/api/v2/account/2fa/disable', {'code': pyotp.TOTP(secret).now()}).status_code == 200
    assert _flag(app, username) is True


def test_passwordless_only_user_is_unchanged_when_enforcement_lifts(app, make_user, enforce_2fa):
    username, key, _ = make_user(totp=False)
    assert _requires(app, username) == ['webauthn']
    _key_session(app, username, key)
    with app.app_context():
        from models import SystemConfig
        SystemConfig.query.filter_by(key='enforce_2fa').delete()
        db.session.commit()
    assert not _requires(app, username)
    assert _flag(app, username) is False


def test_admin_reset_clears_the_switch(app, auth_client, make_user):
    username, _key, _ = make_user(totp=False)
    _put(_password_session(app, username), {'enabled': True})
    with app.app_context():
        uid = User.query.filter_by(username=username).first().id
    assert auth_client.post(f'/api/v2/users/{uid}/reset-2fa').status_code == 200
    assert _flag(app, username) is False


def _switched_on(app, make_user, keys=1):
    username, key, _ = make_user(totp=False)
    c = _password_session(app, username)
    for _ in range(keys - 1):
        assert _register(c, SoftKey()).status_code == 200
    assert _put(c, {'enabled': True}).status_code == 200
    return username


@pytest.mark.parametrize('how', ['delete', 'disable'])
def test_admin_removing_the_last_key_turns_the_switch_off(app, auth_client, make_user, how):
    username = _switched_on(app, make_user)
    key_id, = _key_ids(app, username)
    r = (auth_client.delete(f'/api/v2/webauthn/credentials/{key_id}') if how == 'delete' else
         _post(auth_client, f'/api/v2/webauthn/credentials/{key_id}/toggle', {'enabled': False}))
    assert r.status_code == 200
    assert _flag(app, username) is False


def test_admin_removing_one_of_two_keys_keeps_the_switch(app, auth_client, make_user):
    username = _switched_on(app, make_user, keys=2)
    first, _second = _key_ids(app, username)
    assert auth_client.delete(f'/api/v2/webauthn/credentials/{first}').status_code == 200
    assert _flag(app, username) is True
