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
    # 1. App-level FQDN config (from settings.py / env)
    try:
        fqdn = current_app.config.get('FQDN')
        if fqdn and fqdn.lower() not in _LOCALHOST_NAMES:
            return fqdn
    except Exception:
        pass

    # 2. Request hostname (what the browser used)
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
      1. protocol_base_url setting (user-configured explicit URL)
      2. http_protocol_port setting > 0 → http://{fqdn}:{port}
      3. Current request's host URL (HTTPS fallback, only if not localhost)
    Returns None if hostname resolves to localhost and no URL is configured.
    """
    try:
        # 1. Explicit user-configured URL takes priority
        config = SystemConfig.query.filter_by(key='protocol_base_url').first()
        if config and config.value and config.value.strip():
            return config.value.strip().rstrip('/')

        # 2. Auto-generate from HTTP protocol port + FQDN
        from protocol_http_server import get_http_protocol_port
        http_port = get_http_protocol_port()
        if http_port > 0:
            hostname = _get_fqdn()
            if hostname:
                suffix = '' if http_port == 80 else f':{http_port}'
                return f'http://{hostname}{suffix}'
            return None  # Cannot generate URL — no valid hostname
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
