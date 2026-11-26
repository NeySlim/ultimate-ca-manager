"""A key that opens a session alone (passwordless login, passkey unlock) must verify its user.

WebAuthn Level 2 section 7.2 step 17: when the Relying Party requires user verification,
the UV flag of the assertion must be set. A key used after the password stays 'preferred'.
"""
import hashlib
import json

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec

from tests.conftest import get_json
from tests.test_webauthn_second_factor import (  # noqa: F401 (fixture)
    ORIGIN, SoftKey, _b64url, _challenge, _password, _post, _verify, _logged_in, make_user)

UP, UV = 0x01, 0x04


def _assertion(key, challenge, flags):
    auth_data = hashlib.sha256(b'localhost').digest() + bytes([flags]) + (0).to_bytes(4, 'big')
    client_data = json.dumps({'type': 'webauthn.get', 'challenge': challenge,
                              'origin': ORIGIN, 'crossOrigin': False}).encode()
    sig = key.key.sign(auth_data + hashlib.sha256(client_data).digest(), ec.ECDSA(hashes.SHA256()))
    return {
        'id': _b64url(key.credential_id), 'rawId': _b64url(key.credential_id),
        'type': 'public-key',
        'response': {'authenticatorData': _b64url(auth_data),
                     'clientDataJSON': _b64url(client_data),
                     'signature': _b64url(sig), 'userHandle': None},
    }


def _passwordless_options(c, username):
    r = _post(c, '/api/v2/auth/login/webauthn/start', {'username': username})
    assert r.status_code == 200, r.data
    return get_json(r)['data']['options']


def _passwordless(c, username, key, flags):
    options = _passwordless_options(c, username)
    return _post(c, '/api/v2/auth/login/webauthn/verify',
                 {'username': username, 'response': _assertion(key, options['challenge'], flags)})


def test_passwordless_login_asks_for_user_verification(app, make_user):
    username, _key, _ = make_user(totp=False)
    assert _passwordless_options(app.test_client(), username)['userVerification'] == 'required'


def test_an_unknown_user_gets_the_same_requirement(app):
    options = _passwordless_options(app.test_client(), 'nobody-r31a-uv')
    assert options['userVerification'] == 'required'


def test_passwordless_login_without_user_verification_is_refused(app, make_user):
    username, key, _ = make_user(totp=False)
    c = app.test_client()
    assert _passwordless(c, username, key, UP).status_code == 401
    assert not _logged_in(c)


def test_passwordless_login_with_user_verification_opens_the_session(app, make_user):
    username, key, _ = make_user(totp=False)
    c = app.test_client()
    r = _passwordless(c, username, key, UP | UV)
    assert r.status_code == 200, r.data
    assert _logged_in(c)


def test_a_key_after_the_password_may_skip_user_verification(app, make_user):
    username, key, _ = make_user()
    c = app.test_client()
    assert get_json(_password(c, username))['data']['requires_2fa'] is True
    r = _post(c, '/api/v2/auth/login/2fa/webauthn/options', {})
    options = get_json(r)['data']['options']
    assert options['userVerification'] == 'preferred'
    assert _verify(c, _assertion(key, options['challenge'], UP)).status_code == 200
    assert _logged_in(c)


def _locked_session(app, username):
    c = app.test_client()
    assert get_json(_password(c, username))['data'].get('requires_2fa') in (None, False)
    assert _post(c, '/api/v2/auth/lock', {'reason': 'manual'}).status_code == 200
    return c


def _unlock_options(c):
    r = _post(c, '/api/v2/auth/unlock/webauthn/options', {})
    assert r.status_code == 200, r.data
    return get_json(r)['data']['options']


def test_passkey_unlock_without_user_verification_is_refused(app, make_user):
    username, key, _ = make_user(totp=False)
    c = _locked_session(app, username)
    options = _unlock_options(c)
    assert options['userVerification'] == 'required'
    r = _post(c, '/api/v2/auth/unlock/webauthn/verify',
              {'response': _assertion(key, options['challenge'], UP)})
    assert r.status_code == 401, r.data
    assert c.get('/api/v2/account/profile').status_code == 401


def test_passkey_unlock_with_user_verification_reopens_the_session(app, make_user):
    username, key, _ = make_user(totp=False)
    c = _locked_session(app, username)
    options = _unlock_options(c)
    r = _post(c, '/api/v2/auth/unlock/webauthn/verify',
              {'response': _assertion(key, options['challenge'], UP | UV)})
    assert r.status_code == 200, r.data
    assert c.get('/api/v2/account/profile').status_code == 200

