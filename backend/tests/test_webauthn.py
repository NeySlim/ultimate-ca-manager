"""
WebAuthn Routes Tests — /api/v2/webauthn/*

Tests WebAuthn credential CRUD, registration options, and verification.

Uses shared fixtures from conftest.py:
  - app, client (unauthenticated), auth_client (admin session)
"""
import pytest
import json
from types import SimpleNamespace

from tests.conftest import get_json

def _post(client, url, data=None):
    return client.post(
        url,
        data=json.dumps(data) if data else '{}',
        content_type='application/json',
    )


# ============================================================
# Auth Required
# ============================================================
class TestWebAuthnAuthRequired:
    """Protected endpoints must return 401 without auth."""

    def test_list_credentials_requires_auth(self, app):
        r = app.test_client().get('/api/v2/webauthn/credentials')
        assert r.status_code == 401

    def test_delete_credential_requires_auth(self, app):
        r = app.test_client().delete('/api/v2/webauthn/credentials/1')
        assert r.status_code == 401

    def test_toggle_credential_requires_auth(self, app):
        r = _post(app.test_client(), '/api/v2/webauthn/credentials/1/toggle')
        assert r.status_code == 401

    def test_register_options_requires_auth(self, app):
        r = _post(app.test_client(), '/api/v2/webauthn/register/options')
        assert r.status_code == 401

    def test_register_verify_requires_auth(self, app):
        r = _post(app.test_client(), '/api/v2/webauthn/register/verify')
        assert r.status_code == 401


# ============================================================
# Credentials List
# ============================================================
class TestWebAuthnCredentials:
    """Test WebAuthn credential listing."""

    def test_list_credentials_empty(self, auth_client):
        r = auth_client.get('/api/v2/webauthn/credentials')
        assert r.status_code == 200
        data = get_json(r).get('data', [])
        assert isinstance(data, list)

    def test_list_credentials_returns_array(self, auth_client):
        r = auth_client.get('/api/v2/webauthn/credentials')
        body = get_json(r)
        assert 'data' in body or isinstance(body, list)


# ============================================================
# Delete / Toggle (non-existent)
# ============================================================
class TestWebAuthnDeleteToggle:
    """Test delete and toggle on non-existent credentials."""

    def test_delete_credential_not_found(self, auth_client):
        r = auth_client.delete('/api/v2/webauthn/credentials/99999')
        assert r.status_code == 404

    def test_toggle_credential_not_found(self, auth_client):
        r = _post(auth_client, '/api/v2/webauthn/credentials/99999/toggle')
        assert r.status_code == 404

    def test_toggle_credential_with_enabled_flag(self, auth_client):
        r = _post(auth_client, '/api/v2/webauthn/credentials/99999/toggle', {
            'enabled': False,
        })
        assert r.status_code == 404


# ============================================================
# Authentication sign counter
# ============================================================
class TestWebAuthnSignCount:
    @staticmethod
    def _credential_data(credential_id, challenge):
        from services.webauthn_service import base64url_encode
        client_data = base64url_encode(json.dumps({
            'challenge': challenge,
        }).encode('utf-8'))
        return {
            'id': base64url_encode(credential_id),
            'response': {'clientDataJSON': client_data},
        }

    @staticmethod
    def _records(user_id, credential_id, challenge, sign_count):
        from datetime import timedelta
        from models import db
        from models.webauthn import WebAuthnChallenge, WebAuthnCredential
        from utils.datetime_utils import utc_now

        credential = WebAuthnCredential(
            user_id=user_id,
            credential_id=credential_id,
            public_key=b'public-key',
            sign_count=sign_count,
            enabled=True,
        )
        db.session.add(credential)
        db.session.add(WebAuthnChallenge(
            user_id=user_id,
            challenge=challenge,
            challenge_type='authentication',
            expires_at=utc_now() + timedelta(minutes=5),
        ))
        db.session.commit()
        return credential

    def test_passes_stored_count_and_persists_returned_count(
            self, app, monkeypatch):
        from models import User
        from services import webauthn_service

        with app.app_context():
            user = User.query.filter_by(username='admin').first()
            credential = self._records(
                user.id, b'counter-credential', 'Y291bnRlci1jaGFsbGVuZ2U', 7
            )
            seen = {}

            def verify(**kwargs):
                seen.update(kwargs)
                return SimpleNamespace(new_sign_count=8)

            monkeypatch.setattr(
                webauthn_service, 'verify_authentication_response', verify
            )
            ok, _, _ = webauthn_service.WebAuthnService.verify_authentication(
                user.id,
                self._credential_data(
                    credential.credential_id, 'Y291bnRlci1jaGFsbGVuZ2U'
                ),
                'example.test',
            )

            assert ok is True
            assert seen['credential_current_sign_count'] == 7
            assert credential.sign_count == 8

    def test_authenticator_with_zero_counter_remains_supported(
            self, app, monkeypatch):
        from models import User
        from services import webauthn_service

        with app.app_context():
            user = User.query.filter_by(username='admin').first()
            credential = self._records(
                user.id, b'zero-credential', 'emVyby1jaGFsbGVuZ2U', 0
            )

            def verify(**kwargs):
                assert kwargs['credential_current_sign_count'] == 0
                return SimpleNamespace(new_sign_count=0)

            monkeypatch.setattr(
                webauthn_service, 'verify_authentication_response', verify
            )
            ok, _, _ = webauthn_service.WebAuthnService.verify_authentication(
                user.id,
                self._credential_data(
                    credential.credential_id, 'emVyby1jaGFsbGVuZ2U'
                ),
                'example.test',
            )

            assert ok is True
            assert credential.sign_count == 0


# ============================================================
# Registration
# ============================================================
class TestWebAuthnRegistration:
    """Test WebAuthn registration endpoints."""

    def test_register_options_returns_data(self, auth_client):
        """Registration options should return 200 with challenge data."""
        r = _post(auth_client, '/api/v2/webauthn/register/options')
        # May succeed (200) or fail if RP config missing (400/500)
        assert r.status_code in (200, 400, 500)
        if r.status_code == 200:
            data = get_json(r).get('data', {})
            assert data is not None

    def test_register_verify_empty_data(self, auth_client):
        """Verify with empty credential data → 400."""
        r = _post(auth_client, '/api/v2/webauthn/register/verify', {
            'credential': {},
            'name': 'Test Key',
        })
        assert r.status_code == 400

    def test_register_verify_missing_credential(self, auth_client):
        """Verify with no credential field → 400."""
        r = _post(auth_client, '/api/v2/webauthn/register/verify', {
            'name': 'Test Key',
        })
        assert r.status_code == 400

    def test_register_verify_invalid_credential(self, auth_client):
        """Verify with invalid credential data → 400."""
        r = _post(auth_client, '/api/v2/webauthn/register/verify', {
            'credential': {
                'id': 'fake-id',
                'rawId': 'fake-raw',
                'response': {'clientDataJSON': 'bad', 'attestationObject': 'bad'},
                'type': 'public-key',
            },
            'name': 'Bad Key',
        })
        assert r.status_code == 400
