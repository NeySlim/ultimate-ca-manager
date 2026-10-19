"""A security key as the second factor after a password.

A real ES256 software authenticator signs the assertions, so the library's
verification runs for real: only the challenge handling is under test.
"""
import base64
import hashlib
import json
import uuid

import pyotp
import pytest
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec

import cbor2

from models import User, SystemConfig, db
from models.webauthn import WebAuthnChallenge, WebAuthnCredential
from tests.conftest import get_json

PASSWORD = 'Sec0nd-Factor-Pass!'
ORIGIN = 'https://localhost'


def _b64url(raw):
    return base64.urlsafe_b64encode(raw).rstrip(b'=').decode()


class SoftKey:
    """Minimal FIDO2 authenticator: ES256, counter always 0."""

    def __init__(self):
        self.key = ec.generate_private_key(ec.SECP256R1())
        self.credential_id = uuid.uuid4().bytes
        nums = self.key.public_key().public_numbers()
        self.cose = cbor2.dumps({1: 2, 3: -7, -1: 1,
                                 -2: nums.x.to_bytes(32, 'big'),
                                 -3: nums.y.to_bytes(32, 'big')})

    def attest(self, challenge, origin=ORIGIN, rp_id='localhost'):
        """Registration response, 'none' attestation."""
        auth_data = (hashlib.sha256(rp_id.encode()).digest() + bytes([0x45]) + (0).to_bytes(4, 'big')
                     + bytes(16) + len(self.credential_id).to_bytes(2, 'big')
                     + self.credential_id + self.cose)
        client_data = json.dumps({'type': 'webauthn.create', 'challenge': challenge,
                                  'origin': origin, 'crossOrigin': False}).encode()
        attestation = cbor2.dumps({'fmt': 'none', 'attStmt': {}, 'authData': auth_data})
        return {
            'id': _b64url(self.credential_id), 'rawId': _b64url(self.credential_id),
            'type': 'public-key',
            'response': {'clientDataJSON': _b64url(client_data),
                         'attestationObject': _b64url(attestation)},
        }

    def assert_(self, challenge, origin=ORIGIN, rp_id='localhost'):
        auth_data = hashlib.sha256(rp_id.encode()).digest() + bytes([0x05]) + (0).to_bytes(4, 'big')
        client_data = json.dumps({'type': 'webauthn.get', 'challenge': challenge,
                                  'origin': origin, 'crossOrigin': False}).encode()
        sig = self.key.sign(auth_data + hashlib.sha256(client_data).digest(), ec.ECDSA(hashes.SHA256()))
        return {
            'id': _b64url(self.credential_id), 'rawId': _b64url(self.credential_id),
            'type': 'public-key',
            'response': {'authenticatorData': _b64url(auth_data),
                         'clientDataJSON': _b64url(client_data),
                         'signature': _b64url(sig), 'userHandle': None},
        }


@pytest.fixture
def make_user(app):
    created = []

    def _make(totp=True, key=True):
        with app.app_context():
            user = User(username=f'wa2fa-{uuid.uuid4().hex[:8]}',
                        email=f'{uuid.uuid4().hex[:8]}@example.test', role='operator')
            user.set_password(PASSWORD)
            if totp:
                user.totp_secret = pyotp.random_base32()
                user.totp_confirmed = True
            db.session.add(user)
            db.session.flush()
            soft = SoftKey() if key else None
            if soft:
                db.session.add(WebAuthnCredential(user_id=user.id, credential_id=soft.credential_id,
                                                  public_key=soft.cose, sign_count=0, name='soft'))
            db.session.commit()
            created.append(user.id)
            return user.username, soft, user.totp_secret

    yield _make

    from api.v2.auth_methods import _2fa_failed_attempts
    _2fa_failed_attempts.clear()
    with app.app_context():
        for uid in created:
            WebAuthnChallenge.query.filter_by(user_id=uid).delete()
            WebAuthnCredential.query.filter_by(user_id=uid).delete()
            db.session.delete(db.session.get(User, uid))
        db.session.commit()


def _post(c, url, body):
    return c.post(url, data=json.dumps(body), content_type='application/json')


def _password(c, username):
    return _post(c, '/api/v2/auth/login/password', {'username': username, 'password': PASSWORD})


def _options(c):
    return _post(c, '/api/v2/auth/login/2fa/webauthn/options', {})


def _challenge(c):
    r = _options(c)
    assert r.status_code == 200, r.data
    return get_json(r)['data']['options']['challenge']


def _verify(c, assertion):
    return _post(c, '/api/v2/auth/login/2fa/webauthn/verify', {'response': assertion})


def _logged_in(c):
    return c.get('/api/v2/account/profile').status_code == 200


def test_key_completes_a_password_login(app, make_user):
    username, key, _ = make_user()
    c = app.test_client()
    data = get_json(_password(c, username))['data']
    assert data['requires_2fa'] is True
    assert data['methods'] == ['totp', 'webauthn']
    assert not _logged_in(c)

    r = _verify(c, key.assert_(_challenge(c)))
    assert r.status_code == 200, r.data
    assert get_json(r)['data']['auth_method'] == 'password'
    assert _logged_in(c)


def test_used_challenge_is_deleted(app, make_user):
    username, key, _ = make_user()
    c = app.test_client()
    _password(c, username)
    assert _verify(c, key.assert_(_challenge(c))).status_code == 200
    with app.app_context():
        uid = User.query.filter_by(username=username).first().id
        assert WebAuthnChallenge.query.filter_by(user_id=uid, challenge_type='2fa').count() == 0


def test_wrong_challenge_is_refused_and_burns_the_issued_one(app, make_user):
    username, key, _ = make_user()
    c = app.test_client()
    _password(c, username)
    issued = _challenge(c)

    assert _verify(c, key.assert_(_b64url(b'x' * 32))).status_code == 401
    assert _verify(c, key.assert_(issued)).status_code == 401
    assert not _logged_in(c)


def test_replayed_assertion_is_refused(app, make_user):
    username, key, _ = make_user()
    first = app.test_client()
    _password(first, username)
    assertion = key.assert_(_challenge(first))
    assert _verify(first, assertion).status_code == 200

    again = app.test_client()
    _password(again, username)
    _challenge(again)
    assert _verify(again, assertion).status_code == 401
    assert not _logged_in(again)


def test_challenge_is_bound_to_the_login_session(app, make_user):
    username, key, _ = make_user()
    victim, other = app.test_client(), app.test_client()
    _password(victim, username)
    victims_challenge = _challenge(victim)
    _password(other, username)
    _challenge(other)

    assert _verify(other, key.assert_(victims_challenge)).status_code == 401
    assert not _logged_in(other)


def test_second_factor_challenge_does_not_open_passwordless_login(app, make_user):
    username, key, _ = make_user()
    c = app.test_client()
    _password(c, username)
    assertion = key.assert_(_challenge(c))

    r = _post(app.test_client(), '/api/v2/auth/login/webauthn/verify',
              {'username': username, 'response': assertion})
    assert r.status_code == 401


def test_user_without_a_key_is_offered_totp_only(app, make_user):
    username, _key, secret = make_user(key=False)
    c = app.test_client()
    assert get_json(_password(c, username))['data']['methods'] == ['totp']
    assert _options(c).status_code == 400
    assert _verify(c, SoftKey().assert_(_b64url(b'y' * 32))).status_code == 401

    r = _post(c, '/api/v2/auth/login/2fa', {'code': pyotp.TOTP(secret).now()})
    assert r.status_code == 200, r.data


def test_no_pending_login_no_challenge(app, make_user):
    make_user()
    assert _options(app.test_client()).status_code == 401


def test_failures_count_toward_the_2fa_lockout(app, make_user):
    from api.v2.auth_methods import _get_2fa_lockout_settings
    username, key, _ = make_user()
    c = app.test_client()
    _password(c, username)
    with app.app_context():
        max_attempts, _ = _get_2fa_lockout_settings()
    for _ in range(max_attempts):
        _challenge(c)
        assert _verify(c, key.assert_(_b64url(b'z' * 32))).status_code == 401
    assert _options(c).status_code == 429
    assert _post(c, '/api/v2/auth/login/2fa', {'code': '000000'}).status_code == 429


@pytest.fixture
def enforce_2fa(app):
    def _set(value):
        with app.app_context():
            SystemConfig.query.filter_by(key='enforce_2fa').delete()
            if value:
                db.session.add(SystemConfig(key='enforce_2fa', value='true'))
            db.session.commit()
    _set(True)
    yield
    _set(False)


def test_enforced_2fa_is_satisfied_by_a_key(app, make_user, enforce_2fa):
    username, key, _ = make_user(totp=False)
    c = app.test_client()
    data = get_json(_password(c, username))['data']
    assert data.get('requires_2fa') is True
    assert data['methods'] == ['webauthn']
    assert not data.get('requires_2fa_enrollment')

    # No TOTP secret to check: a code is refused, not a crash.
    assert _post(c, '/api/v2/auth/login/2fa', {'code': '123456'}).status_code == 401

    assert _verify(c, key.assert_(_challenge(c))).status_code == 200
    assert _logged_in(c)


def test_enforced_2fa_without_a_key_still_enrols_totp(app, make_user, enforce_2fa):
    username, _key, _ = make_user(totp=False, key=False)
    data = get_json(_password(app.test_client(), username))['data']
    assert data.get('requires_2fa_enrollment') is True


def test_key_alone_does_not_add_a_step_without_2fa(app, make_user):
    username, _key, _ = make_user(totp=False)
    c = app.test_client()
    data = get_json(_password(c, username))['data']
    assert not data.get('requires_2fa')
    assert _logged_in(c)
