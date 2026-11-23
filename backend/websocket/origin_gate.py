"""Origin check of the Socket.IO channel, answered before Engine.IO and before any upgrade (#453).

A browser always sends Origin on a cross-site WebSocket: a request whose Origin is not in the
live list (utils.public_endpoints.get_cors_origins) gets 403. A request without Origin comes
from a client that is not a browser and is left to Engine.IO, as before.
"""
import logging
import time

logger = logging.getLogger(__name__)

# Set by the gunicorn worker's handler when it declined to upgrade a refused origin
REFUSED_KEY = 'ucm.websocket_origin_refused'
# The Origin this gate accepted: Engine.IO's own check reuses the answer
ACCEPTED_KEY = 'ucm.websocket_origin_accepted'

_REJECTION_LOG_INTERVAL = 300
_MAX_TRACKED_REJECTIONS = 1024
_rejections = {}
_flask_app = None


def origin_accepted(origin) -> bool:
    """True when ``origin`` is in the live list; needs an application context."""
    from utils.public_endpoints import get_cors_origins, normalize_origin
    normalized = normalize_origin(origin)
    return normalized is not None and normalized in get_cors_origins()


def _socketio_origin(environ):
    if not environ.get('PATH_INFO', '').startswith('/socket.io/'):
        return None
    return environ.get('HTTP_ORIGIN') or None


def refused(environ, flask_app=None) -> bool:
    """True for a /socket.io/ request carrying an Origin that is not accepted."""
    origin = _socketio_origin(environ)
    app = flask_app or _flask_app
    if origin is None or app is None:
        return False
    with app.app_context():
        return not origin_accepted(origin)


def log_rejection(origin: str, path: str) -> None:
    """Warn once per origin every few minutes: a misconfigured proxy retries without end."""
    shown = (origin or '')[:200]
    now = time.monotonic()
    last = _rejections.get(shown)
    if last is not None and now - last < _REJECTION_LOG_INTERVAL:
        return
    if last is None and len(_rejections) >= _MAX_TRACKED_REJECTIONS:
        _rejections.clear()
    _rejections[shown] = now
    logger.warning('Rejected WebSocket origin %r on %s: not the admin base URL, the protocol '
                   'base URL, this host or CORS_EXTRA_ORIGINS', shown, path)


class SocketIOOriginGate:
    """WSGI gate in front of Flask-SocketIO, which answers /socket.io/ before any Flask hook."""

    def __init__(self, app, flask_app):
        global _flask_app
        self.app = app
        self.flask_app = flask_app
        _flask_app = flask_app

    def __call__(self, environ, start_response):
        origin = _socketio_origin(environ)
        if origin is not None:
            if environ.get(REFUSED_KEY) or refused(environ, self.flask_app):
                log_rejection(origin, environ.get('PATH_INFO', ''))
                body = b'Origin not allowed'
                start_response('403 Forbidden', [
                    ('Content-Type', 'text/plain; charset=utf-8'),
                    ('Content-Length', str(len(body))),
                ])
                return [body]
            environ[ACCEPTED_KEY] = origin
        return self.app(environ, start_response)
