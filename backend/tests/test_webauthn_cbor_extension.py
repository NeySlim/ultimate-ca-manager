"""A passkey sign-in whose extension data is a cyclic CBOR tag is refused: the decoder
used to crash the worker on it, before any signature was checked."""
import base64
import json
import subprocess
import sys

import pytest

from models import User, db
from models.webauthn import WebAuthnChallenge, WebAuthnCredential

CRED_ID = b'\x0c\x0b\x0f\x02cyclic-tag-credential'
# rpIdHash, flags (user present, extension data), counter, then the extensions
AUTHENTICATOR_DATA = bytes(32) + bytes([0x81]) + bytes(4) + bytes.fromhex('a1d81cd903e8d81d0000')

PROBE = '''
from webauthn.helpers import parse_authenticator_data
from webauthn.helpers.exceptions import InvalidCBORData
try:
    parse_authenticator_data(bytes.fromhex(%r))
except InvalidCBORData:
    print("refused")
''' % AUTHENTICATOR_DATA.hex()


def _b64url(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b'=').decode()


def _decoder_refuses():
    """Asked in another process: a decoder that crashes must not take the test run with it."""
    done = subprocess.run([sys.executable, '-c', PROBE], capture_output=True, text=True, timeout=120)
    return done.returncode, done.stdout.strip()


def test_the_decoder_refuses_a_cyclic_tag_instead_of_crashing():
    assert _decoder_refuses() == (0, 'refused')


@pytest.fixture
def key_holder(app):
    with app.app_context():
        user = User(username='wa-cyclic', email='wa-cyclic@example.test', role='viewer')
        user.set_password('Str0ng-Passw0rd!')
        db.session.add(user)
        db.session.flush()
        db.session.add(WebAuthnCredential(user_id=user.id, credential_id=CRED_ID,
                                          public_key=b'\x00' * 32, sign_count=0))
        db.session.commit()
        user_id = user.id
    yield 'wa-cyclic'
    with app.app_context():
        WebAuthnChallenge.query.filter_by(user_id=user_id).delete()
        WebAuthnCredential.query.filter_by(user_id=user_id).delete()
        db.session.delete(db.session.get(User, user_id))
        db.session.commit()


def test_a_sign_in_carrying_it_is_refused_without_a_session(app, client, key_holder, monkeypatch):
    if _decoder_refuses() != (0, 'refused'):
        pytest.fail('the CBOR decoder crashes on a cyclic tag: not sent through this process')
    import webauthn.authentication.verify_authentication_response as library
    from webauthn.helpers.exceptions import InvalidCBORData
    decoded = []

    def parse(data):
        try:
            return real_parse(data)
        except Exception as error:
            decoded.append(type(error))
            raise

    real_parse = library.parse_authenticator_data
    monkeypatch.setattr(library, 'parse_authenticator_data', parse)
    started = client.post('/api/v2/auth/login/webauthn/start', json={'username': key_holder})
    assert started.status_code == 200, started.get_json()
    options = started.get_json()['data']['options']
    assert options['allowCredentials'][0]['id'] == _b64url(CRED_ID)
    client_data = json.dumps({'type': 'webauthn.get', 'challenge': options['challenge'],
                              'origin': 'https://localhost'}).encode()
    answer = client.post('/api/v2/auth/login/webauthn/verify', json={
        'username': key_holder,
        'response': {'id': _b64url(CRED_ID), 'rawId': _b64url(CRED_ID), 'type': 'public-key',
                     'response': {'clientDataJSON': _b64url(client_data),
                                  'authenticatorData': _b64url(AUTHENTICATOR_DATA),
                                  'signature': _b64url(b'\x30\x00')}}})
    assert answer.status_code == 401, answer.get_json()
    assert decoded == [InvalidCBORData]  # the request went as far as the decoder
    assert client.get('/api/v2/auth/verify').get_json()['data']['authenticated'] is False
