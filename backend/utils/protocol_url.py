"""
Protocol URL helper
Provides the base URL for PKI protocol endpoints (CDP, OCSP, EST, SCEP, AIA).
Users can configure a separate base URL (e.g. http://) to avoid TLS
verification loops when clients fetch CRLs or OCSP responses.
"""
import logging
from flask import request as flask_request, current_app
from models import SystemConfig

logger = logging.getLogger(__name__)

# Hostnames that must never appear in protocol URLs
_LOCALHOST_NAMES = {'localhost', '127.0.0.1', '::1', 'localhost.localdomain'}


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


def ca_prefers_protocol_http(ca) -> bool:
    """Whether this CA should embed HTTP CDP/OCSP/AIA URLs (protocol port)."""
    if ca is None:
        return True
    val = getattr(ca, 'protocol_http', None)
    if val is None:
        return True
    return bool(val)


def get_protocol_base_url_for_ca(ca=None):
    """Per-CA protocol base URL (HTTP :8080 vs HTTPS admin)."""
    return get_protocol_base_url(prefer_http=ca_prefers_protocol_http(ca))


def apply_protocol_urls_for_ca(ca) -> None:
    """Rewrite enabled CDP/OCSP/AIA URLs for the CA's protocol_http preference."""
    base = get_protocol_base_url_for_ca(ca)
    if not base or not ca or not getattr(ca, 'refid', None):
        return
    if getattr(ca, 'cdp_enabled', False):
        ca.set_cdp_urls([f"{base}/cdp/{ca.refid}.crl"])
    if getattr(ca, 'ocsp_enabled', False):
        ca.set_ocsp_urls([f"{base}/ocsp"])
    if getattr(ca, 'aia_ca_issuers_enabled', False):
        ca.set_aia_urls([f"{base}/ca/{ca.refid}.cer"])
