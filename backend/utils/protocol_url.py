"""
Protocol URL helper
Provides the base URL for PKI protocol endpoints (CDP, OCSP, EST, SCEP, AIA).
Users can configure a separate base URL (e.g. http://) to avoid TLS
verification loops when clients fetch CRLs or OCSP responses.

Per-CA flexibility (#207):
  protocol_mode: inherit | http_protocol | https_admin | custom
  protocol_base_url_override: used when mode=custom
  cdp_base_url / ocsp_base_url / aia_base_url: optional per-endpoint bases
  protocol_http: legacy bool (synced from mode)
"""
import logging
import re
from urllib.parse import urlparse

from flask import request as flask_request, current_app
from models import SystemConfig

logger = logging.getLogger(__name__)

# Hostnames that must never appear in protocol URLs
_LOCALHOST_NAMES = {'localhost', '127.0.0.1', '::1', 'localhost.localdomain'}

PROTOCOL_MODES = frozenset({
    'inherit',
    'http_protocol',
    'https_admin',
    'custom',
})

_MAX_BASE_URL_LEN = 512
_SCHEME_RE = re.compile(r'^https?://', re.I)


def _get_fqdn():
    """Get the configured FQDN, preferring settings over request host."""
    # 1. Admin base URL (Settings → General) or env FQDN
    try:
        from utils.public_endpoints import get_admin_public_host
        admin_host = get_admin_public_host()
        if admin_host and admin_host.lower() not in _LOCALHOST_NAMES:
            return admin_host
    except Exception:
        pass

    # 2. App-level FQDN config (from settings.py / env)
    try:
        fqdn = current_app.config.get('FQDN')
        if fqdn and fqdn.lower() not in _LOCALHOST_NAMES:
            return fqdn
    except Exception:
        pass

    # 3. Request hostname (what the browser used)
    try:
        hostname = flask_request.host.split(':')[0]
        if hostname.lower() not in _LOCALHOST_NAMES:
            return hostname
    except Exception:
        pass

    return None


def get_https_admin_base_url():
    """Admin HTTPS origin for embedding CDP/OCSP/AIA when a CA prefers HTTPS."""
    try:
        from utils.public_endpoints import get_admin_canonical_origin, get_admin_base_url
        for getter in (get_admin_canonical_origin, get_admin_base_url):
            url = getter()
            if url and url.startswith('https://'):
                return url.rstrip('/')
        host = _get_fqdn()
        if not host or host.lower() in _LOCALHOST_NAMES:
            return None
        from utils.public_endpoints import _https_port, _format_public_origin
        return _format_public_origin('https', host, _https_port())
    except Exception as e:
        logger.debug("HTTPS admin base URL unavailable: %s", e)
        return None


def get_protocol_base_url(prefer_http: bool = True):
    """
    Get the base URL for protocol endpoints.
    Priority when prefer_http is True (default):
      1. Effective protocol_base_url (DB URL + HTTP_PROTOCOL_PORT / http_protocol_port)
      2. Auto-generate from HTTP protocol port + FQDN
      3. Current request's host URL (HTTPS fallback, only if not localhost)
    When prefer_http is False, return the admin HTTPS base URL instead.
    Returns None if hostname resolves to localhost and no URL is configured.
    """
    if not prefer_http:
        return get_https_admin_base_url()

    try:
        from utils.public_endpoints import get_protocol_effective_url
        effective = get_protocol_effective_url()
        if effective:
            return effective.rstrip('/')

        from protocol_http_server import get_http_protocol_port
        http_port = get_http_protocol_port()
        if http_port > 0:
            hostname = _get_fqdn()
            if hostname:
                suffix = '' if http_port == 80 else f':{http_port}'
                return f'http://{hostname}{suffix}'
            return None
    except Exception as e:
        logger.debug("Protocol URL fallback to request host: %s", e)

    # 3. Fallback to current request URL (only if not localhost)
    try:
        hostname = flask_request.host.split(':')[0]
        if hostname.lower() not in _LOCALHOST_NAMES:
            return flask_request.host_url.rstrip('/')
    except Exception:
        pass

    return None


def normalize_protocol_mode(ca) -> str:
    """Resolve effective protocol_mode, honouring legacy protocol_http."""
    if ca is None:
        return 'inherit'
    mode = (getattr(ca, 'protocol_mode', None) or '').strip().lower()
    if mode in PROTOCOL_MODES:
        return mode
    # Legacy bool: False → https_admin, else inherit
    val = getattr(ca, 'protocol_http', None)
    if val is False:
        return 'https_admin'
    return 'inherit'


def ca_prefers_protocol_http(ca) -> bool:
    """Whether this CA should embed HTTP CDP/OCSP/AIA URLs (protocol port)."""
    return normalize_protocol_mode(ca) != 'https_admin'


def sync_protocol_http_from_mode(ca) -> None:
    """Keep legacy protocol_http in sync with protocol_mode."""
    if ca is None:
        return
    ca.protocol_http = normalize_protocol_mode(ca) != 'https_admin'


def validate_protocol_base_override(url: str, field: str = 'protocol_base_url'):
    """Validate a CA-level protocol base URL override.

    Returns (cleaned_or_none, error_or_none).
    Empty / None clears the override.
    """
    if url is None or (isinstance(url, str) and not url.strip()):
        return None, None
    if not isinstance(url, str):
        return None, f'{field} must be a string'
    cleaned = url.strip().rstrip('/')
    if len(cleaned) > _MAX_BASE_URL_LEN:
        return None, f'{field} too long (max {_MAX_BASE_URL_LEN})'
    if not _SCHEME_RE.match(cleaned):
        return None, f'{field} must use http:// or https://'
    try:
        parsed = urlparse(cleaned)
    except Exception:
        return None, f'{field} is not a valid URL'
    host = (parsed.hostname or '').lower()
    if not host:
        return None, f'{field} must include a hostname'
    if host in _LOCALHOST_NAMES:
        return None, f'{field} must not use localhost'
    if parsed.path and parsed.path not in ('', '/'):
        return None, f'{field} must be an origin only (no path)'
    if parsed.query or parsed.fragment:
        return None, f'{field} must be an origin only (no query/fragment)'
    # Reconstruct normalized origin
    netloc = parsed.netloc
    scheme = parsed.scheme.lower()
    return f'{scheme}://{netloc}', None


def resolve_endpoint_base(ca, endpoint: str = 'default'):
    """Resolve base URL for CDP/OCSP/AIA for a CA.

    endpoint: 'cdp' | 'ocsp' | 'aia' | 'default'
    Per-endpoint override wins; otherwise protocol_mode resolution.
    """
    if ca is not None and endpoint in ('cdp', 'ocsp', 'aia'):
        col = f'{endpoint}_base_url'
        raw = getattr(ca, col, None)
        if raw and str(raw).strip():
            return str(raw).strip().rstrip('/')

    mode = normalize_protocol_mode(ca)
    if mode == 'https_admin':
        return get_https_admin_base_url()
    if mode == 'custom':
        override = getattr(ca, 'protocol_base_url_override', None) if ca else None
        if override and str(override).strip():
            return str(override).strip().rstrip('/')
        # custom without override → inherit Settings HTTP
    if mode == 'http_protocol':
        return get_protocol_base_url(prefer_http=True)
    # inherit (and custom fallback)
    return get_protocol_base_url(prefer_http=True)


def get_protocol_base_url_for_ca(ca=None):
    """Per-CA default protocol base URL (without per-endpoint override)."""
    return resolve_endpoint_base(ca, 'default')


def apply_protocol_urls_for_ca(ca) -> None:
    """Rewrite enabled CDP/OCSP/AIA URLs from resolved bases."""
    if not ca or not getattr(ca, 'refid', None):
        return

    if getattr(ca, 'cdp_enabled', False):
        base = resolve_endpoint_base(ca, 'cdp')
        if base:
            ca.set_cdp_urls([f"{base}/cdp/{ca.refid}.crl"])
    if getattr(ca, 'ocsp_enabled', False):
        base = resolve_endpoint_base(ca, 'ocsp')
        if base:
            ca.set_ocsp_urls([f"{base}/ocsp"])
    if getattr(ca, 'aia_ca_issuers_enabled', False):
        base = resolve_endpoint_base(ca, 'aia')
        if base:
            ca.set_aia_urls([f"{base}/ca/{ca.refid}.cer"])
