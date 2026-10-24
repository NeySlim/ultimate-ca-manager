"""
Protocol HTTP Server
Lightweight HTTP-only server for CDP/OCSP/AIA endpoints and HTTP-01 tokens.
Avoids TLS certificate verification loops when clients fetch CRLs.

Started automatically when http_protocol_port > 0 (default: 8080).
Only serves /cdp/, /ca/, /ocsp, /.well-known/acme-challenge/ and /health — all other paths return 404.
"""
import errno
import logging
import time

logger = logging.getLogger(__name__)

_server = None  # the running server, kept referenced

# Bind retry after a reload: the old worker holds the port until it exits (seconds).
RETRY_FIRST_DELAY = 0.25
RETRY_MAX_DELAY = 4.0


def _sleep(seconds):
    import gevent
    gevent.sleep(seconds)


def _spawn(fn, *args):
    import gevent
    return gevent.spawn(fn, *args)


_clock = time.monotonic  # tests replace _sleep, _spawn and _clock


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


def _bind(flask_app, host, port):
    from gevent.pywsgi import WSGIServer
    server = WSGIServer((host, port), ProtocolOnlyMiddleware(flask_app), log=None)
    server.start()
    return server


def _started(server, host, port):
    global _server
    _server = server
    logger.info("HTTP protocol server (CDP/OCSP) started on %s port %d", host, port)
    return server


def _retry_bind(flask_app, host, port, retry_for):
    """Greenlet body: bind again with a growing delay while the port is busy,
    until the deadline. Never raises."""
    try:
        deadline = _clock() + retry_for
        delay = RETRY_FIRST_DELAY
        while True:
            _sleep(delay)
            try:
                return _started(_bind(flask_app, host, port), host, port)
            except OSError as e:
                if e.errno != errno.EADDRINUSE or _clock() >= deadline:
                    logger.error("Cannot start HTTP protocol server on port %d: %s", port, e)
                    return None
            delay = min(delay * 2, RETRY_MAX_DELAY, max(deadline - _clock(), 0))
    except Exception as e:
        logger.warning("HTTP protocol server startup failed: %s", e)
        return None


def start_http_protocol_server(flask_app, port=None, retry_for=0):
    """Start the HTTP protocol server. Returns the server or None on failure.

    With ``retry_for`` > 0, a busy port is retried in a greenlet for that many
    seconds: after a reload the old worker still holds it.
    """
    if port is None:
        port = get_http_protocol_port()
    if port <= 0:
        return None

    host = None
    try:
        from listen_address import get_bind_host
        host = get_bind_host()
        return _started(_bind(flask_app, host, port), host, port)
    except OSError as e:
        if e.errno == errno.EADDRINUSE and retry_for > 0:
            logger.warning("HTTP protocol port %d is busy, retrying for %gs", port, retry_for)
            _spawn(_retry_bind, flask_app, host, port, retry_for)
            return None
        logger.error("Cannot start HTTP protocol server on port %d: %s", port, e)
        return None
    except Exception as e:
        logger.warning("HTTP protocol server startup failed: %s", e)
        return None
