"""WK-4 tests — webhook auth integration and E2E coverage.

~18 tests covering areas NOT already tested in WK-1/WK-2/WK-3:

  Group 1 (5): Round-trip GET readback for all 5 auth_types
               (WK-3 only tested the CREATE response body for bearer;
               none / basic / api_key / custom GET readback not covered)

  Group 2 (5): Delivery integration — mock safe_request_post and assert the
               actual outgoing request carries the correct auth header.
               Not covered by any earlier WK.

  Group 3 (2): Test-endpoint (/test) sends same auth headers as real delivery.

  Group 4 (2): Encryption at rest — DB _auth_token column is NOT plaintext
               after a full API round-trip (model-level covered in WK-2;
               here we verify the DB row after persist + reload).

  Group 5 (1): No plaintext token in log output during create + delivery.

  Group 6 (2): PUT none→bearer emits webhook.auth_configured;
               GET readback shows auth_token_set=false after switch to none.

  Group 7 (1): 8192-byte token: GET readback shows auth_token_set=true
               (WK-3 only checked the 201 status, not the readback).
"""

import base64
import json
import logging
from unittest.mock import MagicMock, patch

import pytest
from tests.conftest import assert_error, assert_success

CONTENT_JSON = 'application/json'
WH = '/api/v2/webhooks'


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _post(client, payload):
    return client.post(WH, data=json.dumps(payload), content_type=CONTENT_JSON)


def _put(client, wh_id, payload):
    return client.put(f'{WH}/{wh_id}', data=json.dumps(payload),
                      content_type=CONTENT_JSON)


def _get(client, wh_id):
    return client.get(f'{WH}/{wh_id}')


def _base(**kwargs):
    """Minimal payload; callers add name + auth fields."""
    p = {'url': 'https://example.com/wh-integration'}
    p.update(kwargs)
    return p


def _mock_ok():
    """Fake HTTP 200 response."""
    resp = MagicMock()
    resp.ok = True
    resp.status_code = 200
    resp.text = ''
    return resp


def _audit_rows(app, action, resource_id):
    from models.audit_log import AuditLog
    with app.app_context():
        return AuditLog.query.filter_by(
            action=action, resource_id=str(resource_id)
        ).all()


# ===========================================================================
# Group 1 — Round-trip GET readback per auth_type
# ===========================================================================

class TestRoundTripNone:
    def test_none_readback(self, auth_client):
        r = _post(auth_client, _base(name='RT-None-1', auth_type='none'))
        data = assert_success(r, 201)
        wh_id = data['id']

        r2 = _get(auth_client, wh_id)
        data2 = assert_success(r2)

        assert data2['auth_type'] == 'none'
        assert data2['auth_token_set'] is False
        assert 'auth_token' not in data2


class TestRoundTripBearer:
    def test_bearer_get_readback(self, auth_client):
        """Separate GET (not just the POST body) hides plaintext, shows flag."""
        secret = 'rt-bearer-get-secret'
        r = _post(auth_client, _base(name='RT-Bearer-1', auth_type='bearer',
                                     auth_token=secret))
        wh_id = assert_success(r, 201)['id']

        r2 = _get(auth_client, wh_id)
        data2 = assert_success(r2)

        assert data2['auth_type'] == 'bearer'
        assert data2['auth_token_set'] is True
        assert 'auth_token' not in data2
        for val in data2.values():
            assert secret not in str(val), \
                f"Plaintext token leaked in field value: {val!r}"


class TestRoundTripBasic:
    def test_basic_readback_preserves_username(self, auth_client):
        r = _post(auth_client, _base(name='RT-Basic-1', auth_type='basic',
                                     auth_username='alice', auth_token='pass-alice'))
        wh_id = assert_success(r, 201)['id']

        r2 = _get(auth_client, wh_id)
        data2 = assert_success(r2)

        assert data2['auth_type'] == 'basic'
        assert data2['auth_token_set'] is True
        assert data2['auth_username'] == 'alice'
        assert 'auth_token' not in data2
        for val in data2.values():
            assert 'pass-alice' not in str(val)


class TestRoundTripApiKey:
    def test_api_key_readback_preserves_header_name(self, auth_client):
        r = _post(auth_client, _base(name='RT-ApiKey-1', auth_type='api_key',
                                     auth_header_name='X-Svc-Token',
                                     auth_token='svc-token-val'))
        wh_id = assert_success(r, 201)['id']

        r2 = _get(auth_client, wh_id)
        data2 = assert_success(r2)

        assert data2['auth_type'] == 'api_key'
        assert data2['auth_token_set'] is True
        assert data2['auth_header_name'] == 'X-Svc-Token'
        assert data2['auth_username'] is None
        assert 'auth_token' not in data2


class TestRoundTripCustom:
    def test_custom_readback_preserves_header_name(self, auth_client):
        """custom type: scheme embedded in token, Authorization allowed as header."""
        r = _post(auth_client, _base(name='RT-Custom-1', auth_type='custom',
                                     auth_header_name='Authorization',
                                     auth_token='auth-key EMBED-SCHEME'))
        wh_id = assert_success(r, 201)['id']

        r2 = _get(auth_client, wh_id)
        data2 = assert_success(r2)

        assert data2['auth_type'] == 'custom'
        assert data2['auth_token_set'] is True
        assert data2['auth_header_name'] == 'Authorization'
        assert data2['auth_username'] is None
        assert 'auth_token' not in data2
        for val in data2.values():
            assert 'EMBED-SCHEME' not in str(val)


# ===========================================================================
# Group 2 — Delivery integration (safe_request_post mocked)
# ===========================================================================

class TestDeliveryBearer:
    def test_bearer_outgoing_header(self, app, auth_client):
        """_perform_delivery for bearer adds Authorization: Bearer <plaintext>."""
        r = _post(auth_client, _base(name='Del-Bearer-1', auth_type='bearer',
                                     auth_token='del-bearer-secret'))
        wh_id = assert_success(r, 201)['id']

        captured = {}

        def _fake_post(url, **kwargs):
            captured['headers'] = kwargs.get('headers', {})
            return _mock_ok()

        with app.app_context():
            from services.webhook_service import WebhookEndpoint, WebhookService
            ep = WebhookEndpoint.query.get(wh_id)
            with patch('utils.ssrf_protection.safe_request_post',
                       side_effect=_fake_post):
                WebhookService._perform_delivery(
                    ep, 'certificate.issued',
                    WebhookService._build_body_json('certificate.issued', {}, 'ts'))

        assert captured['headers'].get('Authorization') == \
            'Bearer del-bearer-secret'


class TestDeliveryBasic:
    def test_basic_outgoing_header(self, app, auth_client):
        """_perform_delivery for basic adds Authorization: Basic base64(user:pass)."""
        r = _post(auth_client, _base(name='Del-Basic-1', auth_type='basic',
                                     auth_username='bob', auth_token='bobpass'))
        wh_id = assert_success(r, 201)['id']

        captured = {}

        def _fake_post(url, **kwargs):
            captured['headers'] = kwargs.get('headers', {})
            return _mock_ok()

        with app.app_context():
            from services.webhook_service import WebhookEndpoint, WebhookService
            ep = WebhookEndpoint.query.get(wh_id)
            with patch('utils.ssrf_protection.safe_request_post',
                       side_effect=_fake_post):
                WebhookService._perform_delivery(
                    ep, 'certificate.issued',
                    WebhookService._build_body_json('certificate.issued', {}, 'ts'))

        auth_val = captured['headers'].get('Authorization', '')
        assert auth_val.startswith('Basic '), \
            f"Expected Basic auth header, got: {auth_val!r}"
        decoded = base64.b64decode(auth_val[6:]).decode('utf-8')
        assert decoded == 'bob:bobpass'


class TestDeliveryApiKey:
    def test_api_key_outgoing_header(self, app, auth_client):
        """_perform_delivery for api_key adds the custom header, NOT Authorization."""
        r = _post(auth_client, _base(name='Del-ApiKey-1', auth_type='api_key',
                                     auth_header_name='X-Api-Secret',
                                     auth_token='apikey-val-123'))
        wh_id = assert_success(r, 201)['id']

        captured = {}

        def _fake_post(url, **kwargs):
            captured['headers'] = kwargs.get('headers', {})
            return _mock_ok()

        with app.app_context():
            from services.webhook_service import WebhookEndpoint, WebhookService
            ep = WebhookEndpoint.query.get(wh_id)
            with patch('utils.ssrf_protection.safe_request_post',
                       side_effect=_fake_post):
                WebhookService._perform_delivery(
                    ep, 'certificate.issued',
                    WebhookService._build_body_json('certificate.issued', {}, 'ts'))

        headers = captured.get('headers', {})
        assert headers.get('X-Api-Secret') == 'apikey-val-123'
        assert 'Authorization' not in headers, \
            "api_key type must not add an Authorization header"


class TestDeliveryCustom:
    def test_custom_outgoing_header(self, app, auth_client):
        """_perform_delivery for custom places raw token (scheme embedded) in header."""
        r = _post(auth_client, _base(name='Del-Custom-1', auth_type='custom',
                                     auth_header_name='Authorization',
                                     auth_token='auth-key CUSTOM-VAL'))
        wh_id = assert_success(r, 201)['id']

        captured = {}

        def _fake_post(url, **kwargs):
            captured['headers'] = kwargs.get('headers', {})
            return _mock_ok()

        with app.app_context():
            from services.webhook_service import WebhookEndpoint, WebhookService
            ep = WebhookEndpoint.query.get(wh_id)
            with patch('utils.ssrf_protection.safe_request_post',
                       side_effect=_fake_post):
                WebhookService._perform_delivery(
                    ep, 'certificate.issued',
                    WebhookService._build_body_json('certificate.issued', {}, 'ts'))

        # Full raw token is placed verbatim in the configured header
        assert captured['headers'].get('Authorization') == 'auth-key CUSTOM-VAL'


class TestDeliveryNone:
    def test_none_no_auth_header_added(self, app, auth_client):
        """_perform_delivery for none adds no Authorization header."""
        r = _post(auth_client, _base(name='Del-None-1', auth_type='none'))
        wh_id = assert_success(r, 201)['id']

        captured = {}

        def _fake_post(url, **kwargs):
            captured['headers'] = kwargs.get('headers', {})
            return _mock_ok()

        with app.app_context():
            from services.webhook_service import WebhookEndpoint, WebhookService
            ep = WebhookEndpoint.query.get(wh_id)
            with patch('utils.ssrf_protection.safe_request_post',
                       side_effect=_fake_post):
                WebhookService._perform_delivery(
                    ep, 'certificate.issued',
                    WebhookService._build_body_json('certificate.issued', {}, 'ts'))

        assert 'Authorization' not in captured.get('headers', {}), \
            "none auth_type must not add any Authorization header"


# ===========================================================================
# Group 3 — Test endpoint (/test) sends same auth headers as real delivery
# ===========================================================================

class TestTestEndpointAuth:
    def test_bearer_test_endpoint_sends_auth(self, auth_client):
        """POST /test on bearer webhook sends Authorization: Bearer."""
        r = _post(auth_client, _base(name='TEP-Bearer-1', auth_type='bearer',
                                     auth_token='tep-secret-bearer'))
        wh_id = assert_success(r, 201)['id']

        captured = {}

        def _fake_post(url, **kwargs):
            captured['headers'] = kwargs.get('headers', {})
            return _mock_ok()

        with patch('utils.ssrf_protection.safe_request_post',
                   side_effect=_fake_post):
            r2 = auth_client.post(f'{WH}/{wh_id}/test',
                                  data=json.dumps({}),
                                  content_type=CONTENT_JSON)

        assert r2.status_code == 200
        assert captured.get('headers', {}).get('Authorization') == \
            'Bearer tep-secret-bearer'

    def test_none_test_endpoint_no_auth(self, auth_client):
        """POST /test on none-type webhook adds no Authorization."""
        r = _post(auth_client, _base(name='TEP-None-1', auth_type='none'))
        wh_id = assert_success(r, 201)['id']

        captured = {}

        def _fake_post(url, **kwargs):
            captured['headers'] = kwargs.get('headers', {})
            return _mock_ok()

        with patch('utils.ssrf_protection.safe_request_post',
                   side_effect=_fake_post):
            r2 = auth_client.post(f'{WH}/{wh_id}/test',
                                  data=json.dumps({}),
                                  content_type=CONTENT_JSON)

        assert r2.status_code == 200
        assert 'Authorization' not in captured.get('headers', {}), \
            "none type must not add Authorization on /test either"


# ===========================================================================
# Group 4 — Encryption at rest (DB column _auth_token != plaintext)
# ===========================================================================

class TestEncryptionAtRest:
    def test_bearer_token_encrypted_in_db(self, app, auth_client):
        """After full API create, raw DB column must be Fernet-encrypted."""
        plaintext = 'enc-at-rest-bearer-canary'
        r = _post(auth_client, _base(name='Enc-Bearer-1', auth_type='bearer',
                                     auth_token=plaintext))
        wh_id = assert_success(r, 201)['id']

        with app.app_context():
            from services.webhook_service import WebhookEndpoint
            ep = WebhookEndpoint.query.get(wh_id)

            assert ep._auth_token is not None, "Token should be persisted"
            assert ep._auth_token != plaintext, \
                "_auth_token column must not store plaintext"
            # Fernet tokens start with 'gAAAAA' (base64url of version byte 0x80)
            assert ep._auth_token.startswith('gAAAAA'), \
                f"Expected Fernet token, got: {ep._auth_token[:20]!r}"
            # Round-trip: decrypt back to original
            assert ep.auth_token == plaintext, \
                "Decrypted value must equal the original plaintext"

    def test_basic_password_encrypted_in_db(self, app, auth_client):
        """basic auth password (the token) is also stored encrypted."""
        plaintext = 'enc-at-rest-basic-pass'
        r = _post(auth_client, _base(name='Enc-Basic-1', auth_type='basic',
                                     auth_username='dave', auth_token=plaintext))
        wh_id = assert_success(r, 201)['id']

        with app.app_context():
            from services.webhook_service import WebhookEndpoint
            ep = WebhookEndpoint.query.get(wh_id)

            assert ep._auth_token != plaintext
            assert ep._auth_token.startswith('gAAAAA')
            assert ep.auth_token == plaintext


# ===========================================================================
# Group 5 — No plaintext token in log output
# ===========================================================================

class TestNoPlaintextInLogs:
    def test_token_never_appears_in_logs(self, app, auth_client, caplog):
        """Canary token must not appear in any log record during create + delivery."""
        canary = 'CANARY-TOKEN-NOLOG-99zxq'

        with caplog.at_level(logging.DEBUG):
            r = _post(auth_client, _base(name='Log-1', auth_type='bearer',
                                         auth_token=canary))
            wh_id = assert_success(r, 201)['id']

            def _fake_post(url, **kwargs):
                return _mock_ok()

            with app.app_context():
                from services.webhook_service import WebhookEndpoint, WebhookService
                ep = WebhookEndpoint.query.get(wh_id)
                with patch('utils.ssrf_protection.safe_request_post',
                           side_effect=_fake_post):
                    WebhookService._perform_delivery(
                    ep, 'certificate.issued',
                    WebhookService._build_body_json('certificate.issued', {}, 'ts'))

        for record in caplog.records:
            msg = record.getMessage()
            assert canary not in msg, \
                f"Plaintext canary token leaked in log: {msg!r}"


# ===========================================================================
# Group 6 — PUT semantics: none→bearer transition + clear readback
# ===========================================================================

class TestPutAuthTransitions:
    def test_none_to_bearer_emits_auth_configured(self, app, auth_client):
        """PUT that changes auth_type from none→bearer emits webhook.auth_configured."""
        r = _post(auth_client, _base(name='Trans-NtoB-1', auth_type='none'))
        wh_id = assert_success(r, 201)['id']

        r2 = _put(auth_client, wh_id,
                  {'auth_type': 'bearer', 'auth_token': 'transition-token'})
        assert_success(r2)

        rows = _audit_rows(app, 'webhook.auth_configured', wh_id)
        assert len(rows) >= 1, \
            "Expected webhook.auth_configured audit event when transitioning none→bearer"
        assert 'bearer' in rows[-1].details

    def test_switch_to_none_clears_token_set_flag(self, auth_client):
        """After PUT auth_type=none + auth_token=null, GET shows auth_token_set=false."""
        r = _post(auth_client, _base(name='Trans-Clear-1', auth_type='bearer',
                                     auth_token='will-be-cleared'))
        wh_id = assert_success(r, 201)['id']

        r2 = _put(auth_client, wh_id,
                  {'auth_type': 'none', 'auth_token': None})
        data2 = assert_success(r2)
        assert data2['auth_token_set'] is False

        r3 = _get(auth_client, wh_id)
        data3 = assert_success(r3)
        assert data3['auth_token_set'] is False
        assert data3['auth_type'] == 'none'


# ===========================================================================
# Group 7 — Token boundary round-trip (GET readback, not just 201)
# ===========================================================================

class TestTokenBoundaryRoundTrip:
    def test_8192_byte_token_readback_shows_set(self, auth_client):
        """8192-byte token: GET readback returns auth_token_set=true."""
        token_8192 = 'a' * 8192
        r = _post(auth_client, _base(name='TokCap-RT-1', auth_type='bearer',
                                     auth_token=token_8192))
        wh_id = assert_success(r, 201)['id']

        r2 = _get(auth_client, wh_id)
        data2 = assert_success(r2)

        assert data2['auth_token_set'] is True
        assert data2['auth_type'] == 'bearer'
        # Plaintext must not appear in any field
        for val in data2.values():
            assert token_8192 not in str(val), \
                "8192-byte token leaked in GET response"
