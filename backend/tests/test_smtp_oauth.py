"""
Tests for services/smtp_oauth.py

Covers build_xoauth2_string, build_authorize_url, exchange_code_for_tokens,
refresh_access_token, get_access_token, invalidate_cache, and SSRF protection.
"""
from __future__ import annotations

import base64
import logging
import types
from types import SimpleNamespace
from typing import Any, Dict
from unittest.mock import MagicMock, Mock, patch
from urllib.parse import parse_qs, urlparse

import pytest

# ---------------------------------------------------------------------------
# Module under test (path resolved via conftest sys.path insertion)
# ---------------------------------------------------------------------------
import services.smtp_oauth as smtp_oauth

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Config factory
# ---------------------------------------------------------------------------

def _make_config(**overrides: Any) -> SimpleNamespace:
    """Return a minimal SMTPConfig-like namespace with sensible defaults."""
    defaults: Dict[str, Any] = {
        "id": 1,
        "smtp_oauth_provider": "google",
        "smtp_oauth_client_id": "cid",
        "smtp_oauth_client_secret": "secret",
        "smtp_oauth_refresh_token": "refresh-xyz",
        "smtp_oauth_tenant_id": None,
        "smtp_oauth_authorize_url": None,
        "smtp_oauth_token_url": None,
        "smtp_oauth_scope": None,
    }
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


# ---------------------------------------------------------------------------
# Helpers for building mock HTTP responses
# ---------------------------------------------------------------------------

def _mock_token_response(
    status: int = 200,
    access_token: str = "access-tok",
    refresh_token: str = "new-refresh",
    expires_in: int = 3600,
    body: dict | None = None,
) -> Mock:
    resp = Mock()
    resp.status_code = status
    payload = body if body is not None else {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "expires_in": expires_in,
    }
    resp.json.return_value = payload
    resp.text = "sensitive response body with client_secret=s3cr3t"
    return resp


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def clear_token_cache():
    """Wipe the in-process token cache before and after every test."""
    smtp_oauth._token_cache.clear()
    yield
    smtp_oauth._token_cache.clear()


# ---------------------------------------------------------------------------
# build_xoauth2_string
# ---------------------------------------------------------------------------

def test_build_xoauth2_string_format() -> None:
    expected_raw = b"user=lio@ucm.tools\x01auth=Bearer TOKEN\x01\x01"
    expected_b64 = base64.b64encode(expected_raw).decode("ascii")

    result = smtp_oauth.build_xoauth2_string("lio@ucm.tools", "TOKEN")

    assert result == expected_b64
    decoded = base64.b64decode(result)
    assert decoded == expected_raw


def test_build_xoauth2_string_rejects_empty_user() -> None:
    with pytest.raises(ValueError, match="user"):
        smtp_oauth.build_xoauth2_string("", "some-token")


def test_build_xoauth2_string_rejects_empty_token() -> None:
    with pytest.raises(ValueError, match="access_token"):
        smtp_oauth.build_xoauth2_string("user@example.com", "")


# ---------------------------------------------------------------------------
# build_authorize_url — Google
# ---------------------------------------------------------------------------

def test_build_authorize_url_google() -> None:
    config = _make_config(smtp_oauth_provider="google")
    redirect = "https://ucm.tools/oauth/callback"

    url, state = smtp_oauth.build_authorize_url(config, redirect)

    assert url.startswith("https://accounts.google.com/o/oauth2/v2/auth?")
    parsed = urlparse(url)
    params = parse_qs(parsed.query)

    assert params["client_id"] == ["cid"]
    assert params["redirect_uri"] == [redirect]
    assert params["response_type"] == ["code"]
    assert params["scope"] == ["https://mail.google.com/"]
    assert params["access_type"] == ["offline"]
    assert params["prompt"] == ["consent"]
    assert state  # non-empty
    assert params["state"] == [state]


# ---------------------------------------------------------------------------
# build_authorize_url — Microsoft
# ---------------------------------------------------------------------------

def test_build_authorize_url_microsoft_consumer() -> None:
    config = _make_config(smtp_oauth_provider="microsoft", smtp_oauth_tenant_id=None)

    url, state = smtp_oauth.build_authorize_url(config, "https://ucm.tools/callback")

    assert "/consumers/oauth2/v2.0/authorize" in url
    # offline_access required for refresh tokens
    assert "offline_access" in url


def test_build_authorize_url_microsoft_business_tenant() -> None:
    config = _make_config(
        smtp_oauth_provider="microsoft",
        smtp_oauth_tenant_id="abc-tenant-guid",
    )

    url, _state = smtp_oauth.build_authorize_url(config, "https://ucm.tools/callback")

    assert "/abc-tenant-guid/" in url


# ---------------------------------------------------------------------------
# build_authorize_url — edge cases
# ---------------------------------------------------------------------------

def test_build_authorize_url_custom_requires_urls() -> None:
    config = _make_config(
        smtp_oauth_provider="custom",
        smtp_oauth_authorize_url=None,
        smtp_oauth_token_url=None,
    )
    with pytest.raises(ValueError, match="authorize_url"):
        smtp_oauth.build_authorize_url(config, "https://ucm.tools/callback")


def test_build_authorize_url_unknown_provider_raises() -> None:
    config = _make_config(smtp_oauth_provider="yahoo")
    with pytest.raises(ValueError, match="yahoo"):
        smtp_oauth.build_authorize_url(config, "https://ucm.tools/callback")


def test_build_authorize_url_state_passed_through() -> None:
    config = _make_config(smtp_oauth_provider="google")
    url, returned_state = smtp_oauth.build_authorize_url(
        config, "https://ucm.tools/callback", state="xyz"
    )
    assert returned_state == "xyz"
    assert "state=xyz" in url


def test_build_authorize_url_requires_client_id() -> None:
    config = _make_config(smtp_oauth_client_id="")
    with pytest.raises(ValueError, match="client_id"):
        smtp_oauth.build_authorize_url(config, "https://ucm.tools/callback")


# ---------------------------------------------------------------------------
# exchange_code_for_tokens
# ---------------------------------------------------------------------------

def test_exchange_code_for_tokens_success() -> None:
    config = _make_config()
    mock_resp = _mock_token_response()

    with patch("services.smtp_oauth.requests.post", return_value=mock_resp) as mock_post:
        result = smtp_oauth.exchange_code_for_tokens(
            config, code="auth-code-123", redirect_uri="https://ucm.tools/callback"
        )

    assert result["access_token"] == "access-tok"

    _, kwargs = mock_post.call_args
    posted = kwargs["data"]
    assert posted["code"] == "auth-code-123"
    assert posted["grant_type"] == "authorization_code"
    assert posted["client_id"] == "cid"
    assert posted["client_secret"] == "secret"
    assert posted["redirect_uri"] == "https://ucm.tools/callback"


def test_exchange_code_for_tokens_http_error_raises() -> None:
    config = _make_config()
    mock_resp = _mock_token_response(status=400)

    with patch("services.smtp_oauth.requests.post", return_value=mock_resp):
        with pytest.raises(RuntimeError) as exc_info:
            smtp_oauth.exchange_code_for_tokens(
                config, code="bad-code", redirect_uri="https://ucm.tools/callback"
            )

    error_msg = str(exc_info.value)
    assert "400" in error_msg
    # Must NOT echo the response body — providers may include credentials there
    assert "sensitive" not in error_msg
    assert "client_secret" not in error_msg


def test_exchange_code_for_tokens_no_access_token_raises() -> None:
    config = _make_config()
    mock_resp = _mock_token_response(status=200, body={})

    with patch("services.smtp_oauth.requests.post", return_value=mock_resp):
        with pytest.raises(RuntimeError, match="access_token"):
            smtp_oauth.exchange_code_for_tokens(
                config, code="code", redirect_uri="https://ucm.tools/callback"
            )


# ---------------------------------------------------------------------------
# refresh_access_token
# ---------------------------------------------------------------------------

def test_refresh_access_token_success() -> None:
    config = _make_config()
    mock_resp = _mock_token_response()

    with patch("services.smtp_oauth.requests.post", return_value=mock_resp) as mock_post:
        result = smtp_oauth.refresh_access_token(config)

    assert result["access_token"] == "access-tok"

    _, kwargs = mock_post.call_args
    posted = kwargs["data"]
    assert posted["refresh_token"] == "refresh-xyz"
    assert posted["grant_type"] == "refresh_token"


def test_refresh_access_token_microsoft_includes_scope() -> None:
    config = _make_config(smtp_oauth_provider="microsoft", smtp_oauth_tenant_id=None)
    mock_resp = _mock_token_response()

    with patch("services.smtp_oauth.requests.post", return_value=mock_resp) as mock_post:
        smtp_oauth.refresh_access_token(config)

    _, kwargs = mock_post.call_args
    posted = kwargs["data"]
    assert "scope" in posted
    assert "offline_access" in posted["scope"]


def test_refresh_access_token_no_refresh_token_raises() -> None:
    config = _make_config(smtp_oauth_refresh_token=None)
    with pytest.raises(RuntimeError, match="refresh_token"):
        smtp_oauth.refresh_access_token(config)


# ---------------------------------------------------------------------------
# get_access_token — caching behaviour
# ---------------------------------------------------------------------------

def test_get_access_token_caches_within_ttl(monkeypatch) -> None:
    config = _make_config()

    # Pin time so both calls see T=0
    monkeypatch.setattr(smtp_oauth, "time", types.SimpleNamespace(time=lambda: 0.0))

    mock_resp = _mock_token_response(expires_in=3600)

    with patch("services.smtp_oauth.requests.post", return_value=mock_resp) as mock_post:
        result1 = smtp_oauth.get_access_token(config)
        result2 = smtp_oauth.get_access_token(config)

    assert result1 == "access-tok"
    assert result2 == "access-tok"
    # Only one real HTTP call — second hit was served from cache
    assert mock_post.call_count == 1


def test_get_access_token_refreshes_after_expiry(monkeypatch) -> None:
    config = _make_config()

    # First call at T=0, second call at T=3001 (past the 3000s effective TTL)
    times = iter([0.0, 3001.0])
    monkeypatch.setattr(smtp_oauth, "time", types.SimpleNamespace(time=lambda: next(times)))

    resp1 = _mock_token_response(access_token="tok-first", expires_in=3600)
    resp2 = _mock_token_response(access_token="tok-second", expires_in=3600)

    with patch("services.smtp_oauth.requests.post", side_effect=[resp1, resp2]) as mock_post:
        result1 = smtp_oauth.get_access_token(config)
        result2 = smtp_oauth.get_access_token(config)

    assert result1 == "tok-first"
    assert result2 == "tok-second"
    assert mock_post.call_count == 2


def test_get_access_token_honors_short_expires_in(monkeypatch) -> None:
    """expires_in=120 → effective TTL ~60s; a second call at T=70 must refresh."""
    config = _make_config()

    # First call T=0 stores expires_at=60; second call at T=70 misses (60 <= 130)
    times = iter([0.0, 70.0])
    monkeypatch.setattr(smtp_oauth, "time", types.SimpleNamespace(time=lambda: next(times)))

    resp1 = _mock_token_response(access_token="tok-short", expires_in=120)
    resp2 = _mock_token_response(access_token="tok-refreshed", expires_in=120)

    with patch("services.smtp_oauth.requests.post", side_effect=[resp1, resp2]) as mock_post:
        r1 = smtp_oauth.get_access_token(config)
        r2 = smtp_oauth.get_access_token(config)

    assert r1 == "tok-short"
    assert r2 == "tok-refreshed"
    # Two HTTP calls prove the short TTL caused a cache miss at T=70
    assert mock_post.call_count == 2


# ---------------------------------------------------------------------------
# invalidate_cache
# ---------------------------------------------------------------------------

def test_invalidate_cache_drops_token(monkeypatch) -> None:
    config = _make_config()

    monkeypatch.setattr(smtp_oauth, "time", types.SimpleNamespace(time=lambda: 0.0))

    resp1 = _mock_token_response(access_token="tok-a", expires_in=3600)
    resp2 = _mock_token_response(access_token="tok-b", expires_in=3600)

    with patch("services.smtp_oauth.requests.post", side_effect=[resp1, resp2]) as mock_post:
        # Populate cache
        smtp_oauth.get_access_token(config)
        assert 1 in smtp_oauth._token_cache

        smtp_oauth.invalidate_cache(config.id)
        assert config.id not in smtp_oauth._token_cache

        # Next call must go to the network
        smtp_oauth.get_access_token(config)

    assert mock_post.call_count == 2


# ---------------------------------------------------------------------------
# SSRF protection — custom provider
# ---------------------------------------------------------------------------

def test_custom_provider_blocks_cloud_metadata_url() -> None:
    config = _make_config(
        smtp_oauth_provider="custom",
        smtp_oauth_authorize_url="http://169.254.169.254/latest/meta-data",
        smtp_oauth_token_url="https://legit-token-endpoint.example.com/token",
        smtp_oauth_scope="email",
    )
    with pytest.raises((ValueError, Exception)):
        smtp_oauth.build_authorize_url(config, "https://ucm.tools/callback")
