"""
SMTP OAuth2 (XOAUTH2) authentication helper.

Supports the Authorization Code + Refresh Token flow for Gmail and Microsoft
(consumer outlook.com / personal accounts as well as M365 Business tenants).
The admin runs an interactive consent once via the UI; the resulting
refresh_token is persisted (encrypted) on ``SMTPConfig`` and used to mint
short-lived access tokens at send time.

Public entry points:
    PROVIDERS                    — provider preset registry
    build_authorize_url(...)     — assemble OAuth consent URL + state
    exchange_code_for_tokens(...)— first-time code → tokens
    refresh_access_token(...)    — refresh_token → new access_token
    get_access_token(config)     — cached wrapper used by email_service
    build_xoauth2_string(...)    — base64 SASL XOAUTH2 payload
"""
from __future__ import annotations

import base64
import logging
import secrets
import threading
import time
from dataclasses import dataclass
from typing import Optional, Tuple
from urllib.parse import urlencode

import requests

from utils.ssrf_protection import validate_url_not_cloud_metadata

logger = logging.getLogger(__name__)

# Cache TTL for minted access tokens (seconds). Independent of token lifetime —
# we always honor the provider's ``expires_in`` when shorter.
_ACCESS_TOKEN_CACHE_TTL = 50 * 60  # 50 min

# token_endpoint POST timeout (seconds)
_TOKEN_REQUEST_TIMEOUT = 15


@dataclass(frozen=True)
class ProviderPreset:
    """Static OAuth2 + SMTP defaults for a known provider."""
    name: str
    authorize_url_template: str   # may contain {tenant} for microsoft
    token_url_template: str       # may contain {tenant} for microsoft
    scope: str
    smtp_host: str
    smtp_port: int
    smtp_use_tls: bool            # STARTTLS
    smtp_use_ssl: bool            # implicit TLS
    needs_tenant: bool = False


PROVIDERS: dict[str, ProviderPreset] = {
    "google": ProviderPreset(
        name="google",
        authorize_url_template="https://accounts.google.com/o/oauth2/v2/auth",
        token_url_template="https://oauth2.googleapis.com/token",
        scope="https://mail.google.com/",
        smtp_host="smtp.gmail.com",
        smtp_port=587,
        smtp_use_tls=True,
        smtp_use_ssl=False,
    ),
    "microsoft": ProviderPreset(
        name="microsoft",
        # Personal Microsoft accounts (outlook.com, outlook.fr, hotmail.*,
        # live.*, M365 Family). Tenant is fixed to ``consumers``.
        authorize_url_template="https://login.microsoftonline.com/{tenant}/oauth2/v2.0/authorize",
        token_url_template="https://login.microsoftonline.com/{tenant}/oauth2/v2.0/token",
        # offline_access is required to receive a refresh_token.
        scope="https://outlook.office.com/SMTP.Send offline_access",
        # Consumer accounts MUST use this host (smtp.office365.com refuses them).
        smtp_host="smtp-mail.outlook.com",
        smtp_port=587,
        smtp_use_tls=True,
        smtp_use_ssl=False,
        needs_tenant=True,  # default 'consumers', editable for advanced
    ),
    "microsoft365": ProviderPreset(
        name="microsoft365",
        # Microsoft 365 Business / work-school accounts. Tenant accepts
        # 'common', 'organizations', or a tenant GUID.
        authorize_url_template="https://login.microsoftonline.com/{tenant}/oauth2/v2.0/authorize",
        token_url_template="https://login.microsoftonline.com/{tenant}/oauth2/v2.0/token",
        scope="https://outlook.office.com/SMTP.Send offline_access",
        smtp_host="smtp.office365.com",
        smtp_port=587,
        smtp_use_tls=True,
        smtp_use_ssl=False,
        needs_tenant=True,
    ),
}


# In-memory access_token cache. Keyed by SMTPConfig.id.
# {config_id: (access_token, expires_at_unix)}
_token_cache: dict[int, Tuple[str, float]] = {}
_cache_lock = threading.Lock()


def _resolve_endpoints(config) -> Tuple[str, str, str]:
    """Return ``(authorize_url, token_url, scope)`` for ``config``.

    For known providers, expands ``{tenant}`` and applies the preset scope.
    For ``custom``, requires the admin-supplied URLs and scope.
    """
    provider = (config.smtp_oauth_provider or "").lower()

    if provider == "custom":
        if not (config.smtp_oauth_authorize_url and config.smtp_oauth_token_url):
            raise ValueError("Custom OAuth provider requires authorize_url and token_url")
        # Defense in depth: block cloud-metadata IPs even for custom URLs.
        validate_url_not_cloud_metadata(config.smtp_oauth_authorize_url)
        validate_url_not_cloud_metadata(config.smtp_oauth_token_url)
        return (
            config.smtp_oauth_authorize_url,
            config.smtp_oauth_token_url,
            config.smtp_oauth_scope or "",
        )

    preset = PROVIDERS.get(provider)
    if not preset:
        raise ValueError(f"Unknown OAuth provider: {provider!r}")

    # Per-provider default tenant when admin didn't supply one.
    default_tenant = "common" if provider == "microsoft365" else "consumers"
    tenant = config.smtp_oauth_tenant_id or default_tenant
    authorize_url = preset.authorize_url_template.format(tenant=tenant)
    token_url = preset.token_url_template.format(tenant=tenant)
    return authorize_url, token_url, preset.scope


def build_authorize_url(config, redirect_uri: str, state: Optional[str] = None) -> Tuple[str, str]:
    """Assemble the provider authorization URL.

    Returns ``(url, state)``. ``state`` is generated if not supplied; the
    caller MUST persist it (e.g. in the Flask session) and verify it matches
    on callback to prevent CSRF on the OAuth flow.
    """
    if not config.smtp_oauth_client_id:
        raise ValueError("smtp_oauth_client_id is required")

    authorize_url, _, scope = _resolve_endpoints(config)
    state = state or secrets.token_urlsafe(32)

    params = {
        "client_id": config.smtp_oauth_client_id,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": scope,
        "state": state,
        # Google: required to get a refresh_token reliably.
        "access_type": "offline",
        "prompt": "consent",
    }
    return f"{authorize_url}?{urlencode(params)}", state


def exchange_code_for_tokens(config, code: str, redirect_uri: str) -> dict:
    """Exchange an authorization ``code`` for ``{access_token, refresh_token, expires_in}``."""
    if not (config.smtp_oauth_client_id and config.smtp_oauth_client_secret):
        raise ValueError("client_id and client_secret are required")

    _, token_url, _ = _resolve_endpoints(config)

    data = {
        "code": code,
        "client_id": config.smtp_oauth_client_id,
        "client_secret": config.smtp_oauth_client_secret,
        "redirect_uri": redirect_uri,
        "grant_type": "authorization_code",
    }
    resp = requests.post(token_url, data=data, timeout=_TOKEN_REQUEST_TIMEOUT)
    if resp.status_code >= 400:
        # Never echo full body — providers sometimes include client_secret hints
        logger.error(f"OAuth token exchange failed: HTTP {resp.status_code}")
        raise RuntimeError(f"Token exchange failed (HTTP {resp.status_code})")

    payload = resp.json()
    if "access_token" not in payload:
        raise RuntimeError("Token endpoint did not return access_token")
    return payload


def refresh_access_token(config) -> dict:
    """Use the stored refresh_token to mint a new access_token."""
    if not config.smtp_oauth_refresh_token:
        raise RuntimeError("No refresh_token stored — admin must Authorize first")
    if not (config.smtp_oauth_client_id and config.smtp_oauth_client_secret):
        raise ValueError("client_id and client_secret are required")

    _, token_url, scope = _resolve_endpoints(config)

    data = {
        "client_id": config.smtp_oauth_client_id,
        "client_secret": config.smtp_oauth_client_secret,
        "refresh_token": config.smtp_oauth_refresh_token,
        "grant_type": "refresh_token",
    }
    # Microsoft requires scope on refresh; Google ignores it but accepts it.
    if scope:
        data["scope"] = scope

    resp = requests.post(token_url, data=data, timeout=_TOKEN_REQUEST_TIMEOUT)
    if resp.status_code >= 400:
        logger.error(f"OAuth token refresh failed: HTTP {resp.status_code}")
        raise RuntimeError(f"Token refresh failed (HTTP {resp.status_code})")

    payload = resp.json()
    if "access_token" not in payload:
        raise RuntimeError("Token endpoint did not return access_token")
    return payload


def get_access_token(config) -> str:
    """Return a valid access_token for ``config``, refreshing if needed.

    Cached in-process for up to 50 minutes (or the provider's
    ``expires_in`` minus a 60-second safety margin, whichever is shorter).
    """
    now = time.time()
    with _cache_lock:
        cached = _token_cache.get(config.id)
        # ``expires_at`` already bakes in a 60s safety margin (see below),
        # so a simple ``>`` here is sufficient — no double margin.
        if cached and cached[1] > now:
            return cached[0]

    payload = refresh_access_token(config)
    access_token = payload["access_token"]
    expires_in = int(payload.get("expires_in", _ACCESS_TOKEN_CACHE_TTL))
    # Refresh 60s before the provider's stated expiry, capped at our own TTL.
    ttl = min(expires_in - 60, _ACCESS_TOKEN_CACHE_TTL)
    expires_at = now + max(ttl, 60)

    with _cache_lock:
        _token_cache[config.id] = (access_token, expires_at)
    return access_token


def invalidate_cache(config_id: int) -> None:
    """Drop a cached access_token (called on revoke / config change)."""
    with _cache_lock:
        _token_cache.pop(config_id, None)


def build_xoauth2_string(user: str, access_token: str) -> str:
    """Build the SASL XOAUTH2 payload (base64-encoded).

    Format per RFC: ``base64("user=" {user} "^Aauth=Bearer " {token} "^A^A")``
    where ``^A`` is the literal byte ``0x01``.
    """
    if not user:
        raise ValueError("user is required for XOAUTH2")
    if not access_token:
        raise ValueError("access_token is required for XOAUTH2")
    raw = f"user={user}\x01auth=Bearer {access_token}\x01\x01".encode("utf-8")
    return base64.b64encode(raw).decode("ascii")
