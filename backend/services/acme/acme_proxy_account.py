"""Resolve the external ACME CA account used as the proxy upstream.

The proxy reuses ``AcmeClientAccount`` rows (same registry as the ACME client)
instead of maintaining a parallel set of SystemConfig credentials.
"""
from __future__ import annotations

import logging
from typing import Optional

from models import db, SystemConfig
from models.acme_client_account import AcmeClientAccount

logger = logging.getLogger(__name__)

PROXY_ACCOUNT_ID_KEY = 'acme.proxy.acme_account_id'

PROXY_RESERVED_SLUGS = frozenset({
    'directory', 'new-nonce', 'new-account', 'new-order',
    'acct', 'authz', 'challenge', 'order', 'cert',
    'revoke-cert', 'key-change',
})

MODE_URLS = {
    'production': AcmeClientAccount.LE_PRODUCTION_URL,
    'staging': AcmeClientAccount.LE_STAGING_URL,
}


def _get_config(key: str) -> Optional[str]:
    row = SystemConfig.query.filter_by(key=key).first()
    if not row or row.value is None:
        return None
    val = str(row.value).strip()
    return val or None


def legacy_upstream_directory_url() -> str:
    """Derive upstream directory URL from legacy proxy SystemConfig keys."""
    custom = _get_config('acme.proxy.upstream_url')
    if custom:
        return custom
    mode = _get_config('acme.proxy.upstream_mode') or 'staging'
    return MODE_URLS.get(mode, AcmeClientAccount.LE_STAGING_URL)


def normalize_proxy_slug(raw: str) -> str:
    """Validate and normalize a proxy path slug."""
    import re
    slug = (raw or '').strip().lower()
    if not slug:
        raise ValueError('proxy_slug is required')
    if not re.fullmatch(r'[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?', slug):
        raise ValueError(
            'proxy_slug must be 1-63 lowercase letters, digits, or hyphens '
            '(not starting/ending with a hyphen)'
        )
    if slug in PROXY_RESERVED_SLUGS:
        raise ValueError(f'proxy_slug {slug!r} is reserved')
    return slug


def slugify_proxy_label(label: str) -> str:
    """Derive a default slug from a CA account label."""
    import re
    slug = re.sub(r'[^a-z0-9]+', '-', (label or 'ca').lower()).strip('-')
    slug = slug[:63] or 'ca'
    if slug in PROXY_RESERVED_SLUGS:
        slug = f'{slug}-ca'[:63]
    return slug


class ProxyEndpointNotConfiguredError(RuntimeError):
    """Raised when a proxy URL slug matches no enabled endpoint.

    Distinct from generic RuntimeError so API handlers can echo this
    client-actionable message while still hiding upstream failure details.
    """


def resolve_proxy_by_slug(slug: str) -> AcmeClientAccount:
    """Resolve an enabled proxy endpoint by URL path slug."""
    slug = normalize_proxy_slug(slug)
    acct = AcmeClientAccount.query.filter_by(proxy_slug=slug, proxy_enabled=True).first()
    if not acct:
        raise ProxyEndpointNotConfiguredError(
            f'ACME proxy endpoint {slug!r} is not configured or not enabled'
        )
    return acct


def resolve_proxy_account(explicit_id: Optional[int] = None) -> AcmeClientAccount:
    """Return the ``AcmeClientAccount`` row the proxy should use upstream.

    Priority:
      1. ``explicit_id`` argument (API override)
      2. ``acme.proxy.acme_account_id`` SystemConfig
      3. Account matching legacy ``acme.proxy.upstream_url`` / mode
      4. Row marked ``is_default=True``
      5. Let's Encrypt staging (creates a placeholder if missing)
    """
    account_id = explicit_id
    if account_id is None:
        raw = _get_config(PROXY_ACCOUNT_ID_KEY)
        if raw:
            try:
                account_id = int(raw)
            except ValueError:
                logger.warning("Invalid %s value: %r", PROXY_ACCOUNT_ID_KEY, raw)

    if account_id is not None:
        acct = db.session.get(AcmeClientAccount, account_id)
        if not acct:
            raise RuntimeError(f"Configured proxy CA account id={account_id} was not found")
        return acct

    legacy_url = legacy_upstream_directory_url()
    acct = AcmeClientAccount.query.filter_by(directory_url=legacy_url).first()
    if acct:
        return acct

    default = AcmeClientAccount.query.filter_by(is_default=True).first()
    if default:
        return default

    acct = AcmeClientAccount.query.filter_by(
        directory_url=AcmeClientAccount.LE_STAGING_URL
    ).first()
    if acct:
        return acct

    raise RuntimeError(
        "No external ACME CA account configured for the proxy. "
        "Add a CA account under ACME → External CA Accounts and select it for the proxy."
    )
