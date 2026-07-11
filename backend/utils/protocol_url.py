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


def get_protocol_base_url():
    """
    Get the base URL for protocol endpoints.
    Priority:
      1. Effective protocol_base_url (DB URL + HTTP_PROTOCOL_PORT / http_protocol_port)
      2. Auto-generate from HTTP protocol port + FQDN
      3. Current request's host URL (HTTPS fallback, only if not localhost)
    Returns None if hostname resolves to localhost and no URL is configured.
    """
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
