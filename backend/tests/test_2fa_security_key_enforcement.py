"""Enforced 2FA is met by TOTP or a security key, and never left without either.

Forced enrolment accepts a key registration; TOTP may be disabled while a key
remains; a user cannot remove (or disable) the last key when TOTP is absent.
"""
import pyotp

from models import User
from models.webauthn import WebAuthnCredential
from tests.conftest import get_json
from tests.test_webauthn_second_factor import (  # noqa: F401 (fixtures)
    SoftKey, enforce_2fa, make_user, _challenge, _logged_in, _password, _post, _verify,
)


def _key_session(app, username, key):
    c = app.test_client()
    _password(c, username)
    assert _verify(c, key.assert_(_challenge(c))).status_code == 200
    return c


def _register(c, key):
    r = _post(c, '/api/v2/webauthn/register/options', {})
    assert r.status_code == 200, r.data
    challenge = get_json(r)['data']['challenge']
    return _post(c, '/api/v2/webauthn/register/verify',
                 {'credential': key.attest(challenge), 'name': 'enrolled'})


def _key_ids(app, username):
    with app.app_context():
        uid = User.query.filter_by(username=username).first().id
        return [k.id for k in WebAuthnCredential.query.filter_by(user_id=uid).order_by(WebAuthnCredential.id)]


def test_forced_enrolment_accepts_a_security_key(app, make_user, enforce_2fa):
    username, _none, _ = make_user(totp=False, key=False)
    c = app.test_client()
    assert get_json(_password(c, username))['data'].get('requires_2fa_enrollment') is True
    assert c.get('/api/v2/account/profile').status_code == 403

    key = SoftKey()
    r = _register(c, key)
    assert r.status_code == 200, r.data
    assert _logged_in(c)

    data = get_json(_password(app.test_client(), username))['data']
    assert data.get('requires_2fa') is True and data['methods'] == ['webauthn']


def test_totp_can_be_disabled_while_a_key_remains(app, make_user, enforce_2fa):
    username, key, secret = make_user()
    c = _key_session(app, username, key)
    r = _post(c, '/api/v2/account/2fa/disable', {'code': pyotp.TOTP(secret).now()})
    assert r.status_code == 200, r.data


def test_totp_stays_when_it_is_the_only_factor(app, make_user, enforce_2fa):
    username, _none, secret = make_user(key=False)
    c = app.test_client()
    _password(c, username)
    assert _post(c, '/api/v2/auth/login/2fa', {'code': pyotp.TOTP(secret).now()}).status_code == 200
    r = _post(c, '/api/v2/account/2fa/disable', {'code': pyotp.TOTP(secret).now()})
    assert r.status_code == 403


def test_last_key_cannot_go_without_totp(app, make_user, enforce_2fa):
    username, key, _ = make_user(totp=False)
    c = _key_session(app, username, key)
    key_id, = _key_ids(app, username)
    assert c.delete(f'/api/v2/webauthn/credentials/{key_id}').status_code == 403
    assert _post(c, f'/api/v2/webauthn/credentials/{key_id}/toggle', {'enabled': False}).status_code == 403
    assert len(_key_ids(app, username)) == 1


def test_a_second_key_can_go(app, make_user, enforce_2fa):
    username, key, _ = make_user(totp=False)
    c = _key_session(app, username, key)
    assert _register(c, SoftKey()).status_code == 200
    first, second = _key_ids(app, username)
    assert c.delete(f'/api/v2/webauthn/credentials/{second}').status_code == 200
    assert c.delete(f'/api/v2/webauthn/credentials/{first}').status_code == 403


def test_last_key_can_go_when_totp_remains(app, make_user, enforce_2fa):
    username, key, _ = make_user()
    c = _key_session(app, username, key)
    key_id, = _key_ids(app, username)
    assert c.delete(f'/api/v2/webauthn/credentials/{key_id}').status_code == 200


def test_last_key_can_go_without_enforcement(app, make_user):
    username, key, _ = make_user(totp=False)
    c = app.test_client()
    _password(c, username)
    assert _logged_in(c)
    key_id, = _key_ids(app, username)
    assert c.delete(f'/api/v2/webauthn/credentials/{key_id}').status_code == 200


def test_admin_can_remove_a_lost_key(app, auth_client, make_user, enforce_2fa):
    username, _key, _ = make_user(totp=False)
    key_id, = _key_ids(app, username)
    with app.app_context():
        uid = User.query.filter_by(username=username).first().id
    url = f'/api/v2/users/{uid}/webauthn/{key_id}?confirm=last_factor'
    assert auth_client.delete(url).status_code == 200


def test_a_key_counts_as_enrolled_for_every_login_door(app, make_user, enforce_2fa):
    from auth.twofa_enforcement import must_enroll_2fa
    with_key, _k, _ = make_user(totp=False)
    without, _n, _ = make_user(totp=False, key=False)
    with app.app_context():
        for method in ('password', 'sso'):
            assert must_enroll_2fa(User.query.filter_by(username=with_key).first(), auth_method=method) is False
            assert must_enroll_2fa(User.query.filter_by(username=without).first(), auth_method=method) is True
