"""
Protocol HTTP Server
Lightweight HTTP-only server for CDP/OCSP/AIA endpoints and HTTP-01 tokens.
Avoids TLS certificate verification loops when clients fetch CRLs.

Started automatically when http_protocol_port > 0 (default: 8080).
Only serves /cdp/, /ca/, /ocsp, /.well-known/acme-challenge/ and /health — all other paths return 404.
"""
import logging

logger = logging.getLogger(__name__)


class ProtocolOnlyMiddleware:
    """WSGI middleware that restricts HTTP server to protocol endpoints only."""

    def __init__(self, app):
        self.app = app

    def __call__(self, environ, start_response):
        path = environ.get('PATH_INFO', '')

        # Health check handled directly (no Flask/Talisman overhead)
        if path == '/health':
            start_response('200 OK', [('Content-Type', 'text/plain')])
            return [b'OK']

        if path.startswith(('/cdp/', '/ca/', '/ocsp', '/.well-known/acme-challenge/')):
            # Disable Talisman HTTPS redirect for protocol requests
            environ['wsgi.url_scheme'] = 'https'
            return self.app(environ, start_response)

        start_response('404 Not Found', [('Content-Type', 'text/plain')])
        return [b'Only CDP/OCSP/AIA and ACME HTTP-01 endpoints are available on this port']


def get_http_protocol_port():
    """Resolve the HTTP protocol port from env var or DB setting.
    Returns 0 if disabled.
    """
    import os
    env_val = os.getenv('HTTP_PROTOCOL_PORT')
    if env_val is not None:
        try:
            return int(env_val)
        except (ValueError, TypeError):
            logger.warning("Invalid HTTP_PROTOCOL_PORT env var: %s", env_val)
            return 0

    # Fallback to DB setting
    try:
        from models import SystemConfig
        cfg = SystemConfig.query.filter_by(key='http_protocol_port').first()
        if cfg and cfg.value:
            port = int(cfg.value)
            return port if 0 <= port <= 65535 else 0
    except Exception:
        pass
    return 8080  # Default


def start_http_protocol_server(flask_app, port=None):
    """Start the HTTP protocol server. Returns the server or None on failure."""
    if port is None:
        port = get_http_protocol_port()
    if port <= 0:
        return None

    try:
        from gevent.pywsgi import WSGIServer
        from listen_address import get_bind_host
        host = get_bind_host()
        server = WSGIServer(
            (host, port),
            ProtocolOnlyMiddleware(flask_app),
            log=None,
        )
        server.start()
        logger.info("HTTP protocol server (CDP/OCSP) started on %s port %d", host, port)
        return server
    except OSError as e:
        logger.error("Cannot start HTTP protocol server on port %d: %s", port, e)
        return None
    except Exception as e:
        logger.warning("HTTP protocol server startup failed: %s", e)
        return None
