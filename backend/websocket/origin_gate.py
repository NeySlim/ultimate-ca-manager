"""Origin check of the Socket.IO channel, answered before Engine.IO and before any upgrade (#453).

A browser always sends Origin on a cross-site WebSocket: a request whose Origin is not in the
live list (utils.public_endpoints.get_websocket_origins) gets 403. A request without Origin
comes from a client that is not a browser and is left to Engine.IO, as before.
"""
import logging
import threading
import time

logger = logging.getLogger(__name__)

# The decision, set in the environ by whoever takes it first (the gunicorn worker's handler
# before an upgrade, else this gate): HTTP headers cannot set these keys.
REFUSED_KEY = 'ucm.websocket_origin_refused'
ACCEPTED_KEY = 'ucm.websocket_origin_accepted'

_REJECTION_LOG_INTERVAL = 300
_MAX_TRACKED_REJECTIONS = 1024
# Distinct origins warned about per window, every origin together: Origin is unauthenticated
_MAX_WARNINGS_PER_WINDOW = 10
_rejections = {}
_window = {}
_log_lock = threading.Lock()
_flask_app = None


def origin_accepted(origin) -> bool:
    """True when ``origin`` is in the live list; needs an application context."""
    from utils.public_endpoints import get_websocket_origins, normalize_origin
    normalized = normalize_origin(origin)
    return normalized is not None and normalized in get_websocket_origins()


def _socketio_origin(environ):
    if not environ.get('PATH_INFO', '').startswith('/socket.io/'):
        return None
    return environ.get('HTTP_ORIGIN') or None


def refused(environ, flask_app=None) -> bool:
    """True for a /socket.io/ request carrying an Origin that is not accepted.

    The list is read once per request: the answer is kept in the environ for the next caller.
    """
    origin = _socketio_origin(environ)
    if origin is None:
        return False
    if environ.get(REFUSED_KEY):
        return True
    if environ.get(ACCEPTED_KEY) == origin:
        return False
    app = flask_app or _flask_app
    if app is None:
        return False
    with app.app_context():
        accepted = origin_accepted(origin)
    if accepted:
        environ[ACCEPTED_KEY] = origin
    else:
        environ[REFUSED_KEY] = True
    return not accepted


def log_rejection(origin: str, path: str) -> None:
    """Warn once per origin every few minutes, and about at most a few origins per window."""
    shown = (origin or '')[:200]
    with _log_lock:
        now = time.monotonic()
        last = _rejections.get(shown)
        if last is not None and now - last < _REJECTION_LOG_INTERVAL:
            return
        if 'start' not in _window or now - _window['start'] >= _REJECTION_LOG_INTERVAL:
            if _window.get('suppressed'):
                logger.warning('%d more WebSocket origins refused in an earlier %d s window, '
                               'not logged one by one', _window['suppressed'],
                               _REJECTION_LOG_INTERVAL)
            _window.update(start=now, warned=0, suppressed=0)
        if last is None and len(_rejections) >= _MAX_TRACKED_REJECTIONS:
            _rejections.clear()
        _rejections[shown] = now
        if _window['warned'] >= _MAX_WARNINGS_PER_WINDOW:
            _window['suppressed'] += 1
            return
        _window['warned'] += 1
    logger.warning('Rejected WebSocket origin %r on %s: not the admin base URL, this host or '
                   'CORS_EXTRA_ORIGINS', shown, path)


class SocketIOOriginGate:
    """WSGI gate in front of Flask-SocketIO, which answers /socket.io/ before any Flask hook."""

    def __init__(self, app, flask_app):
        global _flask_app
        self.app = app
        self.flask_app = flask_app
        _flask_app = flask_app

    def __call__(self, environ, start_response):
        if refused(environ, self.flask_app):
            log_rejection(_socketio_origin(environ), environ.get('PATH_INFO', ''))
            body = b'Origin not allowed'
            start_response('403 Forbidden', [
                ('Content-Type', 'text/plain; charset=utf-8'),
                ('Content-Length', str(len(body))),
            ])
            return [body]
        return self.app(environ, start_response)
