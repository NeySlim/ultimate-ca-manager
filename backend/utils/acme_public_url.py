"""Helpers for public ACME endpoint URLs exposed to clients.

Companion to :mod:`utils.protocol_url` (same job for the CDP/OCSP/AIA HTTP
endpoints): a SystemConfig-backed public origin override with a request-host
fallback. ACME keeps host and port as separate settings because the directory
must advertise a concrete https origin (RFC 8555 requires HTTPS URLs).

The origin is memoized per request/app context on ``flask.g``: a single ACME
order flow hits ``/acme/*`` many times and several helpers need the origin
within one request — without the memo each call would cost a SystemConfig
round-trip on an unauthenticated hot path.
"""

import re
from urllib.parse import urlsplit

from flask import g

from models import SystemConfig

_CONFIG_KEYS = ('acme_public_vhost', 'acme_public_port')

# Concrete FQDN: 1-63 char labels (alnum, inner hyphens), >= 2 labels, alpha
# TLD — same label rules as the ACME domain-mapping validator. No wildcard,
# scheme, port or path: the value is embedded verbatim in advertised URLs.
_FQDN_RE = re.compile(
    r'^([a-zA-Z0-9]([a-zA-Z0-9\-]{0,61}[a-zA-Z0-9])?\.)+[a-zA-Z]{2,}$'
)


def is_valid_public_vhost(host: str) -> bool:
    """True when *host* is a concrete FQDN usable in advertised ACME URLs."""
    return bool(_FQDN_RE.match(host or ''))


def _configured_acme_host_port():
    try:
        rows = SystemConfig.query.filter(
            SystemConfig.key.in_(_CONFIG_KEYS)
        ).all()
        values = {row.key: (row.value or '').strip() for row in rows}
    except Exception:
        # DB unavailable (boot, safe mode): behave as unconfigured so the
        # public /acme/directory endpoints keep working.
        values = {}
    host = values.get('acme_public_vhost', '')
    port_raw = values.get('acme_public_port', '')
    try:
        port = int(port_raw) if port_raw else _default_acme_https_port()
    except (TypeError, ValueError):
        port = _default_acme_https_port()
    return host, port


def _default_acme_https_port() -> int:
    """Match deployment HTTPS_PORT when acme_public_port is unset in DB."""
    import os
    env = os.getenv('HTTPS_PORT')
    if env is not None:
        try:
            return int(env)
        except (TypeError, ValueError):
            pass
    try:
        from flask import current_app
        return int(current_app.config.get('HTTPS_PORT', 8443))
    except Exception:
        return 8443


def get_acme_public_origin(flask_request) -> str:
    """Public origin for ACME endpoints (configured vhost/port or request host)."""
    cached = getattr(g, '_acme_public_origin', None)
    if cached is not None:
        return cached
    host, port = _configured_acme_host_port()
    if host:
        host_part = host if port == 443 else f'{host}:{port}'
        origin = f'https://{host_part}'
    else:
        origin = f'{flask_request.scheme}://{flask_request.host}'
    try:
        g._acme_public_origin = origin
    except RuntimeError:
        pass  # outside app context (direct unit-test calls)
    return origin


def get_acme_public_host(flask_request) -> str:
    """Public hostname (no port) — the identity ACME advertises (e.g. CAA)."""
    hostname = urlsplit(get_acme_public_origin(flask_request)).hostname
    return hostname or flask_request.host.split(':')[0]


def get_acme_public_base(flask_request) -> str:
    """Public base URL of the local ACME server (``…/acme``)."""
    return f'{get_acme_public_origin(flask_request)}/acme'


def get_acme_proxy_public_base(flask_request) -> str:
    """Public base URL of the ACME proxy (``…/acme/proxy``)."""
    return f'{get_acme_public_origin(flask_request)}/acme/proxy'


def get_acme_expected_urls(flask_request, expected_url: str) -> list:
    """URLs accepted for the RFC 8555 §6.4 JWS ``url`` header.

    The canonical URL is built from the configured public origin; the same
    path on the inbound request origin is also accepted so in-flight clients
    keep working when ``acme_public_vhost`` is (re)configured: orders and
    accounts minted under the previous origin, or clients reaching UCM on the
    internal hostname, sign the URL they actually used.
    """
    urls = [expected_url]
    public_origin = get_acme_public_origin(flask_request)
    if expected_url.startswith(public_origin):
        path = expected_url[len(public_origin):]
        inbound = f'{flask_request.scheme}://{flask_request.host}{path}'
        if inbound not in urls:
            urls.append(inbound)
    return urls
