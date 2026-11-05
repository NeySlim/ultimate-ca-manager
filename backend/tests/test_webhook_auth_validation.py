"""
WK-3 tests — webhook auth validation, PUT semantics, and audit events.

10 cases covering:
  1. POST bearer + token → 201, auth_token_set=true, no auth_token key
  2. POST api_key + Authorization header → 400 specific message
  3. POST basic missing auth_username → 400
  4. POST token > 8192 bytes → 400
  5. PUT auth_token absent → token preserved
  6. PUT auth_token="" → 400
  7. PUT auth_token=null + auth_type=none → cleared
  8. PUT bearer→basic without auth_username → 400
  9. Audit events: configure / disable / rotate / invalid
 10. Bad header name characters → 400
"""

import json
import uuid

import pytest
from tests.conftest import assert_error, assert_success
from models import db

CONTENT_JSON = 'application/json'
WH = '/api/v2/webhooks'


def _post(client, payload):
    return client.post(WH, data=json.dumps(payload), content_type=CONTENT_JSON)


def _put(client, wh_id, payload):
    return client.put(f'{WH}/{wh_id}', data=json.dumps(payload), content_type=CONTENT_JSON)


def _base_payload(**kwargs):
    p = {'name': f'Test Hook {uuid.uuid4().hex[:8]}', 'url': 'https://example.com/hook'}
    p.update(kwargs)
    return p


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _create_bearer(auth_client, token='secret-token'):
    r = _post(auth_client, _base_payload(auth_type='bearer', auth_token=token))
    data = assert_success(r, 201)
    return data['id']


def _audit_rows(app, action, resource_id=None):
    """Return audit log rows matching action (and optionally resource_id)."""
    from models.audit_log import AuditLog
    with app.app_context():
        q = AuditLog.query.filter_by(action=action)
        if resource_id is not None:
            q = q.filter_by(resource_id=str(resource_id))
        return q.all()


# ─────────────────────────────────────────────────────────────────────────────
# Test 1 — POST bearer token → 201, auth_token_set=true, no auth_token key
# ─────────────────────────────────────────────────────────────────────────────

class TestBearerCreate:
    def test_bearer_create_201(self, auth_client):
        r = _post(auth_client, _base_payload(auth_type='bearer', auth_token='tok123'))
        assert r.status_code == 201

    def test_bearer_readback_no_token(self, auth_client):
        r = _post(auth_client, _base_payload(name='BearerReadback',
                                             auth_type='bearer', auth_token='tok123'))
        data = assert_success(r, 201)
        assert 'auth_token' not in data, "auth_token must never be in response"
        assert data['auth_token_set'] is True
        assert data['auth_type'] == 'bearer'


# ─────────────────────────────────────────────────────────────────────────────
# Test 2 — POST api_key + Authorization header → 400 specific message
# ─────────────────────────────────────────────────────────────────────────────

class TestApiKeyAuthorizationBlocked:
    def test_api_key_authorization_rejected(self, auth_client):
        r = _post(auth_client, _base_payload(
            auth_type='api_key',
            auth_header_name='Authorization',
            auth_token='mykey',
        ))
        assert_error(r, 400)
        body = json.loads(r.data)
        msg = body.get('message', '')
        assert 'custom' in msg.lower(), f"Expected hint about custom type; got: {msg}"

    def test_api_key_authorization_case_insensitive(self, auth_client):
        r = _post(auth_client, _base_payload(
            auth_type='api_key',
            auth_header_name='AUTHORIZATION',
            auth_token='mykey',
        ))
        assert_error(r, 400)


# ─────────────────────────────────────────────────────────────────────────────
# Test 3 — POST basic missing auth_username → 400
# ─────────────────────────────────────────────────────────────────────────────

class TestBasicMissingUsername:
    def test_basic_no_username_400(self, auth_client):
        r = _post(auth_client, _base_payload(auth_type='basic', auth_token='pass123'))
        assert_error(r, 400)
        body = json.loads(r.data)
        msg = body.get('message', '')
        assert 'auth_username' in msg.lower() or 'username' in msg.lower(), msg

    def test_basic_with_username_ok(self, auth_client):
        r = _post(auth_client, _base_payload(
            name='BasicOK',
            auth_type='basic',
            auth_username='alice',
            auth_token='pass123',
        ))
        assert r.status_code == 201


# ─────────────────────────────────────────────────────────────────────────────
# Test 4 — POST token > 8192 bytes → 400
# ─────────────────────────────────────────────────────────────────────────────

class TestTokenSizeCap:
    def test_oversized_token_rejected(self, auth_client):
        big_token = 'x' * 8193
        r = _post(auth_client, _base_payload(auth_type='bearer', auth_token=big_token))
        assert_error(r, 400)
        body = json.loads(r.data)
        msg = body.get('message', '')
        assert '8192' in msg, f"Error should mention byte cap; got: {msg}"

    def test_exactly_8192_bytes_accepted(self, auth_client):
        # 8192 ASCII chars = 8192 UTF-8 bytes
        token_8192 = 'a' * 8192
        r = _post(auth_client, _base_payload(
            name='SizeEdge',
            auth_type='bearer',
            auth_token=token_8192,
        ))
        assert r.status_code == 201


# ─────────────────────────────────────────────────────────────────────────────
# Test 5 — PUT auth_token absent → existing token preserved
# ─────────────────────────────────────────────────────────────────────────────

class TestPutTokenAbsent:
    def test_token_preserved_when_absent(self, app, auth_client):
        wh_id = _create_bearer(auth_client, token='original-secret')

        # PUT without auth_token
        r = _put(auth_client, wh_id, {'name': 'Renamed'})
        data = assert_success(r)
        assert data['auth_token_set'] is True, "Token should still be set"

        # Verify plaintext unchanged via direct model read
        from services.webhook_service import WebhookEndpoint
        with app.app_context():
            ep = db.session.get(WebhookEndpoint, wh_id)
            assert ep.auth_token == 'original-secret', \
                "Stored token must be unchanged when absent from PUT"


# ─────────────────────────────────────────────────────────────────────────────
# Test 6 — PUT auth_token="" → 400
# ─────────────────────────────────────────────────────────────────────────────

class TestPutTokenEmptyString:
    def test_empty_string_token_400(self, auth_client):
        wh_id = _create_bearer(auth_client)
        r = _put(auth_client, wh_id, {'auth_token': ''})
        assert_error(r, 400)
        body = json.loads(r.data)
        msg = body.get('message', '')
        assert 'null' in msg.lower() or 'empty' in msg.lower(), msg


# ─────────────────────────────────────────────────────────────────────────────
# Test 7 — PUT auth_token=null + auth_type=none → cleared
# ─────────────────────────────────────────────────────────────────────────────

class TestPutClearToken:
    def test_null_token_with_none_type_clears(self, app, auth_client):
        wh_id = _create_bearer(auth_client, token='will-be-cleared')

        r = _put(auth_client, wh_id, {'auth_type': 'none', 'auth_token': None})
        data = assert_success(r)
        assert data['auth_token_set'] is False, "Token should be cleared"
        assert data['auth_type'] == 'none'

        from services.webhook_service import WebhookEndpoint
        with app.app_context():
            ep = db.session.get(WebhookEndpoint, wh_id)
            assert ep._auth_token is None
            assert ep.auth_token is None


# ─────────────────────────────────────────────────────────────────────────────
# Test 8 — PUT bearer→basic without auth_username → 400
# ─────────────────────────────────────────────────────────────────────────────

class TestPutTypeChangeRequiresFields:
    def test_bearer_to_basic_no_username_400(self, auth_client):
        wh_id = _create_bearer(auth_client)
        # Change type to basic but no auth_username in payload OR stored
        r = _put(auth_client, wh_id, {'auth_type': 'basic'})
        assert_error(r, 400)
        body = json.loads(r.data)
        msg = body.get('message', '')
        assert 'auth_username' in msg.lower() or 'username' in msg.lower(), msg

    def test_bearer_to_basic_with_username_ok(self, auth_client):
        wh_id = _create_bearer(auth_client)
        r = _put(auth_client, wh_id, {'auth_type': 'basic', 'auth_username': 'bob'})
        data = assert_success(r)
        assert data['auth_type'] == 'basic'
        assert data['auth_username'] == 'bob'
        assert data['auth_token_set'] is True  # original token preserved


# ─────────────────────────────────────────────────────────────────────────────
# Test 9 — Audit events
# ─────────────────────────────────────────────────────────────────────────────

class TestAuditEvents:
    def test_auth_configured_on_create(self, app, auth_client):
        r = _post(auth_client, _base_payload(
            name='AuditConfigured',
            auth_type='bearer',
            auth_token='tok-audit',
        ))
        data = assert_success(r, 201)
        wh_id = data['id']
        rows = _audit_rows(app, 'webhook.auth_configured', wh_id)
        assert len(rows) >= 1, "Expected webhook.auth_configured audit row"
        assert 'bearer' in rows[-1].details

    def test_auth_disabled_on_put(self, app, auth_client):
        wh_id = _create_bearer(auth_client, token='tok-disable')
        _put(auth_client, wh_id, {'auth_type': 'none', 'auth_token': None})
        rows = _audit_rows(app, 'webhook.auth_disabled', wh_id)
        assert len(rows) >= 1, "Expected webhook.auth_disabled audit row"

    def test_auth_token_rotated_on_put(self, app, auth_client):
        wh_id = _create_bearer(auth_client, token='old-token')
        _put(auth_client, wh_id, {'auth_token': 'new-token'})
        rows = _audit_rows(app, 'webhook.auth_token_rotated', wh_id)
        assert len(rows) >= 1, "Expected webhook.auth_token_rotated audit row"
        # Verify token value never appears in audit details
        for row in rows:
            assert 'old-token' not in (row.details or '')
            assert 'new-token' not in (row.details or '')

    def test_auth_token_invalid_on_bad_validation(self, app, auth_client):
        wh_id = _create_bearer(auth_client, token='existing')
        # Trigger validation error: empty string token
        _put(auth_client, wh_id, {'auth_token': ''})
        rows = _audit_rows(app, 'webhook.auth_token_invalid', wh_id)
        assert len(rows) >= 1, "Expected webhook.auth_token_invalid audit row"
        # Verify the reason is in details, not the token
        assert 'existing' not in (rows[-1].details or '')


# ─────────────────────────────────────────────────────────────────────────────
# Test 10 — Bad header name characters → 400
# ─────────────────────────────────────────────────────────────────────────────

class TestBadHeaderName:
    @pytest.mark.parametrize('bad_name', [
        'X-Bad Header',    # space
        'X-Bad\tHeader',   # tab
        'X-Bad\x00',       # null byte
        'Héader',          # non-ASCII
        '',                # empty (different error path)
    ])
    def test_invalid_header_name_rejected(self, auth_client, bad_name):
        r = _post(auth_client, _base_payload(
            auth_type='api_key',
            auth_header_name=bad_name,
            auth_token='mykey',
        ))
        assert_error(r, 400)

    def test_valid_rfc7230_header_accepted(self, auth_client):
        r = _post(auth_client, _base_payload(
            name='RFC7230OK',
            auth_type='api_key',
            auth_header_name='X-Api-Key',
            auth_token='mykey',
        ))
        assert r.status_code == 201
