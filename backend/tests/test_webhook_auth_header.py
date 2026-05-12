"""
Unit tests for WK-2: webhook auth model + _build_auth_header helper.

Tests:
- _build_auth_header() for all auth_type values and edge cases
- WebhookEndpoint.auth_token property (encrypt/decrypt round-trip, clear)
- WebhookEndpoint.to_dict() does not leak plaintext token
"""
import base64
import json
import pytest
import sys
import os

# Ensure backend is on path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# ---------------------------------------------------------------------------
# Stub webhook object — no DB needed for header-builder tests
# ---------------------------------------------------------------------------

class _Stub:
    """Minimal webhook stub for _build_auth_header tests."""
    def __init__(self, auth_type='none', auth_token=None, auth_username=None,
                 auth_header_name=None):
        self.id = 0
        self.auth_type = auth_type
        self.auth_token = auth_token
        self.auth_username = auth_username
        self.auth_header_name = auth_header_name


# Import the function under test (import after path setup)
from services.webhook_service import _build_auth_header


# ===========================================================================
# _build_auth_header unit tests
# ===========================================================================

class TestBuildAuthHeaderNone:
    def test_none_returns_empty(self):
        assert _build_auth_header(_Stub(auth_type='none')) == {}

    def test_none_is_default(self):
        # auth_type=None should be treated as 'none'
        s = _Stub()
        s.auth_type = None
        assert _build_auth_header(s) == {}


class TestBuildAuthHeaderBearer:
    def test_bearer_returns_authorization(self):
        result = _build_auth_header(_Stub(auth_type='bearer', auth_token='mytoken'))
        assert result == {'Authorization': 'Bearer mytoken'}

    def test_bearer_empty_token_returns_empty(self):
        assert _build_auth_header(_Stub(auth_type='bearer', auth_token=None)) == {}

    def test_bearer_blank_token_returns_empty(self):
        assert _build_auth_header(_Stub(auth_type='bearer', auth_token='')) == {}


class TestBuildAuthHeaderBasic:
    def test_basic_returns_authorization(self):
        result = _build_auth_header(_Stub(
            auth_type='basic', auth_token='secret', auth_username='user'))
        assert 'Authorization' in result
        value = result['Authorization']
        assert value.startswith('Basic ')
        decoded = base64.b64decode(value[6:]).decode('utf-8')
        assert decoded == 'user:secret'

    def test_basic_missing_username_returns_empty(self):
        assert _build_auth_header(_Stub(
            auth_type='basic', auth_token='secret', auth_username=None)) == {}

    def test_basic_empty_username_returns_empty(self):
        assert _build_auth_header(_Stub(
            auth_type='basic', auth_token='secret', auth_username='')) == {}

    def test_basic_username_with_colon_returns_empty(self):
        assert _build_auth_header(_Stub(
            auth_type='basic', auth_token='secret', auth_username='us:er')) == {}

    def test_basic_missing_token_returns_empty(self):
        assert _build_auth_header(_Stub(
            auth_type='basic', auth_token=None, auth_username='user')) == {}


class TestBuildAuthHeaderApiKey:
    def test_api_key_custom_name(self):
        result = _build_auth_header(_Stub(
            auth_type='api_key', auth_token='keyval', auth_header_name='X-API-Key'))
        assert result == {'X-API-Key': 'keyval'}

    def test_api_key_rejects_authorization(self):
        assert _build_auth_header(_Stub(
            auth_type='api_key', auth_token='keyval',
            auth_header_name='Authorization')) == {}

    def test_api_key_rejects_authorization_lowercase(self):
        assert _build_auth_header(_Stub(
            auth_type='api_key', auth_token='keyval',
            auth_header_name='authorization')) == {}

    def test_api_key_missing_header_name_returns_empty(self):
        assert _build_auth_header(_Stub(
            auth_type='api_key', auth_token='keyval', auth_header_name=None)) == {}

    def test_api_key_missing_token_returns_empty(self):
        assert _build_auth_header(_Stub(
            auth_type='api_key', auth_token=None, auth_header_name='X-API-Key')) == {}


class TestBuildAuthHeaderCustom:
    def test_custom_allows_authorization(self):
        # custom type: header_name can be 'Authorization', value is the full token
        result = _build_auth_header(_Stub(
            auth_type='custom', auth_token='auth-key VALUE',
            auth_header_name='Authorization'))
        assert result == {'Authorization': 'auth-key VALUE'}

    def test_custom_non_authorization_header(self):
        result = _build_auth_header(_Stub(
            auth_type='custom', auth_token='mytoken',
            auth_header_name='X-Custom-Auth'))
        assert result == {'X-Custom-Auth': 'mytoken'}

    def test_custom_missing_header_name_returns_empty(self):
        assert _build_auth_header(_Stub(
            auth_type='custom', auth_token='tok', auth_header_name=None)) == {}

    def test_custom_missing_token_returns_empty(self):
        assert _build_auth_header(_Stub(
            auth_type='custom', auth_token=None, auth_header_name='Authorization')) == {}


class TestBuildAuthHeaderUnknown:
    def test_unknown_type_returns_empty(self):
        assert _build_auth_header(_Stub(auth_type='oauth2', auth_token='tok')) == {}

    def test_unknown_empty_string_type_returns_empty(self):
        # Empty string is not a valid auth_type — treated as 'none' due to strip
        assert _build_auth_header(_Stub(auth_type='', auth_token='tok')) == {}


class TestBuildAuthHeaderTokenCap:
    def test_token_too_large_returns_empty(self):
        big_token = 'x' * 8193
        assert _build_auth_header(_Stub(auth_type='bearer', auth_token=big_token)) == {}

    def test_token_at_limit_is_allowed(self):
        token = 'x' * 8192
        result = _build_auth_header(_Stub(auth_type='bearer', auth_token=token))
        assert result == {'Authorization': f'Bearer {token}'}


# ===========================================================================
# Model property and to_dict tests — require Flask app context
# ===========================================================================

@pytest.fixture(scope='module')
def _app():
    """Minimal app context for model tests."""
    from tests.conftest import app as app_fixture
    # Re-use session-scoped app if available, else bootstrap a minimal one
    import os, tempfile
    os.environ.setdefault('SECRET_KEY', 'test-secret-key-for-testing')
    os.environ.setdefault('JWT_SECRET_KEY', 'test-jwt-secret-key-for-testing')
    os.environ.setdefault('UCM_ENV', 'test')
    os.environ.setdefault('HTTP_REDIRECT', 'false')
    os.environ.setdefault('INITIAL_ADMIN_PASSWORD', 'changeme123')
    os.environ.setdefault('CSRF_DISABLED', 'true')
    os.environ.setdefault('UCM_DEV_MODE', 'true')
    with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as f:
        db_path = f.name
    os.environ['UCM_DATABASE_PATH'] = db_path
    from app import create_app
    application = create_app('testing')
    yield application
    if os.path.exists(db_path):
        os.unlink(db_path)


class TestWebhookAuthTokenProperty:
    """Tests for encrypted property pair on WebhookEndpoint."""

    def test_auth_token_property_encrypts(self, app):
        """Setting auth_token stores an encrypted blob, not plaintext."""
        from services.webhook_service import WebhookEndpoint
        with app.app_context():
            ep = WebhookEndpoint(name='enc-test', url='https://example.com/wh',
                                 events='[]')
            ep.auth_token = 'mysecret'
            # The raw column value must differ from plaintext
            assert ep._auth_token is not None
            assert ep._auth_token != 'mysecret'

    def test_auth_token_property_decrypts(self, app):
        """Reading auth_token decrypts back to plaintext."""
        from services.webhook_service import WebhookEndpoint
        with app.app_context():
            ep = WebhookEndpoint(name='dec-test', url='https://example.com/wh',
                                 events='[]')
            ep.auth_token = 'roundtrip-value'
            assert ep.auth_token == 'roundtrip-value'

    def test_auth_token_clear_none(self, app):
        """Setting auth_token=None clears _auth_token."""
        from services.webhook_service import WebhookEndpoint
        with app.app_context():
            ep = WebhookEndpoint(name='clr-test', url='https://example.com/wh',
                                 events='[]')
            ep.auth_token = 'will-be-cleared'
            assert ep._auth_token is not None
            ep.auth_token = None
            assert ep._auth_token is None

    def test_auth_token_clear_empty_string(self, app):
        """Setting auth_token='' also clears _auth_token."""
        from services.webhook_service import WebhookEndpoint
        with app.app_context():
            ep = WebhookEndpoint(name='clr2-test', url='https://example.com/wh',
                                 events='[]')
            ep.auth_token = 'will-be-cleared'
            ep.auth_token = ''
            assert ep._auth_token is None


class TestWebhookToDict:
    """to_dict() must expose auth_token_set but never the plaintext token."""

    def test_to_dict_does_not_leak_token(self, app):
        """No field in to_dict() should contain the plaintext token."""
        from services.webhook_service import WebhookEndpoint
        with app.app_context():
            ep = WebhookEndpoint(
                name='leak-test', url='https://example.com/wh',
                events='[]', auth_type='bearer',
            )
            secret = 'super-secret-bearer-token'
            ep.auth_token = secret
            d = ep.to_dict()
            # Verify no field value contains the plaintext secret
            for key, val in d.items():
                assert secret not in str(val), \
                    f"Field '{key}' leaks plaintext token"

    def test_to_dict_auth_token_set_true(self, app):
        """auth_token_set is True when a token is stored."""
        from services.webhook_service import WebhookEndpoint
        with app.app_context():
            ep = WebhookEndpoint(
                name='set-true', url='https://example.com/wh',
                events='[]', auth_type='bearer',
            )
            ep.auth_token = 'some-token'
            assert ep.to_dict()['auth_token_set'] is True

    def test_to_dict_auth_token_set_false_when_no_token(self, app):
        """auth_token_set is False when no token is stored."""
        from services.webhook_service import WebhookEndpoint
        with app.app_context():
            ep = WebhookEndpoint(
                name='set-false', url='https://example.com/wh',
                events='[]', auth_type='none',
            )
            assert ep.to_dict()['auth_token_set'] is False

    def test_to_dict_includes_auth_fields(self, app):
        """to_dict() includes all auth metadata fields."""
        from services.webhook_service import WebhookEndpoint
        with app.app_context():
            ep = WebhookEndpoint(
                name='fields-test', url='https://example.com/wh',
                events='[]', auth_type='api_key',
                auth_username=None, auth_header_name='X-API-Key',
            )
            ep.auth_token = 'apikey123'
            d = ep.to_dict()
            assert d['auth_type'] == 'api_key'
            assert d['auth_header_name'] == 'X-API-Key'
            assert d['auth_username'] is None
            assert 'auth_token' not in d
