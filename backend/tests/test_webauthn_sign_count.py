"""WebAuthn signature-counter (clone detection) semantics.

Regression cover for the v2.200 lockout: enforcement was delegated to the
library, which refuses whenever either side is non-zero and the response does
not increase. Authenticators that always report 0 (Apple passkeys, Windows
Hello, many FIDO2 keys) could therefore never beat a stored value that earlier
releases had inflated by one per login — locking users out of their own key.
"""
import base64
import json
from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from models import User, db
from utils.datetime_utils import utc_now
from models.webauthn import WebAuthnCredential, WebAuthnChallenge
from services.webauthn_service import WebAuthnService

CRED_ID = b'\x01\x02\x03\x04credential-id'
CHALLENGE = 'Y2hhbGxlbmdlLXZhbHVl'


def _b64url(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b'=').decode()


@pytest.fixture
def credential(app):
    with app.app_context():
        user = User(username='wa-count', email='wa-count@example.test', role='viewer')
        user.set_password('Str0ng-Passw0rd!')
        db.session.add(user)
        db.session.flush()
        cred = WebAuthnCredential(
            user_id=user.id,
            credential_id=CRED_ID,
            public_key=b'\x00' * 32,
            sign_count=85,           # inflated by the pre-2.200 write path
        )
        db.session.add(cred)
        db.session.commit()
        ids = {'user_id': user.id, 'cred_id': cred.id}
        yield ids

        WebAuthnChallenge.query.filter_by(user_id=ids['user_id']).delete()
        WebAuthnCredential.query.filter_by(user_id=ids['user_id']).delete()
        db.session.delete(db.session.get(User, ids['user_id']))
        db.session.commit()


def _run_verify(app, credential, reported_count):
    """Drive verify_authentication with a stubbed library verification."""
    with app.app_context():
        db.session.add(WebAuthnChallenge(
            user_id=credential['user_id'],
            challenge=CHALLENGE,
            challenge_type='authentication',
            used=False,
            expires_at=utc_now() + timedelta(minutes=5),
        ))
        db.session.commit()

        client_data = _b64url(json.dumps({
            'type': 'webauthn.get',
            'challenge': CHALLENGE,
            'origin': 'https://example.test',
        }).encode())

        payload = {
            'id': _b64url(CRED_ID),
            'rawId': _b64url(CRED_ID),
            'type': 'public-key',
            'response': {'clientDataJSON': client_data},
        }

        captured = {}

        def fake_verify(**kwargs):
            captured.update(kwargs)
            return SimpleNamespace(new_sign_count=reported_count)

        with patch('services.webauthn_service.verify_authentication_response', fake_verify):
            ok, message, _user = WebAuthnService.verify_authentication(
                credential['user_id'], payload, 'example.test',
            )

        stored = db.session.get(WebAuthnCredential, credential['cred_id']).sign_count
        return ok, message, stored, captured


class TestZeroCounterAuthenticators:

    def test_zero_reporting_key_is_not_locked_out(self, app, credential):
        """The bug: stored 85, authenticator reports 0 → must still authenticate."""
        ok, message, stored, _cap = _run_verify(app, credential, reported_count=0)
        assert ok is True, message
        # the inflated value is replaced by the authenticator's real one
        assert stored == 0

    def test_library_is_not_asked_to_enforce(self, app, credential):
        """Enforcement happens in UCM, so the library must receive 0."""
        _ok, _msg, _stored, captured = _run_verify(app, credential, reported_count=0)
        assert captured['credential_current_sign_count'] == 0


class TestCloneDetectionStillWorks:

    def test_non_increasing_real_counter_is_refused(self, app, credential):
        """A key that does keep a counter must still be caught going backwards."""
        ok, message, stored, _cap = _run_verify(app, credential, reported_count=40)
        assert ok is False
        assert message == 'Authentication failed'   # no internals leaked
        assert stored == 85                         # unchanged on refusal

    def test_increasing_counter_is_accepted_and_stored(self, app, credential):
        ok, message, stored, _cap = _run_verify(app, credential, reported_count=86)
        assert ok is True, message
        assert stored == 86
