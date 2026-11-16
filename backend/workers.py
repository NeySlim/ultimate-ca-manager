"""
Custom Gunicorn workers for UCM

Extends GeventWebSocketWorker to inject SSL client certificate (peercert)
into the WSGI environ, enabling native mTLS authentication without a
reverse proxy.
"""
from geventwebsocket.handler import WebSocketHandler
from geventwebsocket.gunicorn.workers import GeventWebSocketWorker
from gunicorn.workers.ggevent import PyWSGIHandler
import ctypes
import functools
import ssl
import logging

import gevent.ssl

logger = logging.getLogger(__name__)


def _openssl_clear_error():
    """ERR_clear_error of the libcrypto the ssl module is linked to, or None."""
    try:
        import _ssl
        clear = ctypes.CDLL(_ssl.__file__).ERR_clear_error
    except (ImportError, OSError, AttributeError):
        return None
    clear.argtypes, clear.restype = [], None
    return clear


def clear_tls_errors_before_io(cls=gevent.ssl.SSLSocket):
    """Empties the thread's OpenSSL error queue before each TLS call of ``cls``, as SSL_get_error
    requires: CPython leaves there the system errors it raises as OSError, and every greenlet of
    the worker shares the thread, so one dropped connection made another's wait look like a failure."""
    if cls.__dict__.get('_ucm_clears_tls_errors'):
        return True
    clear = _openssl_clear_error()
    if clear is None:
        logger.warning("OpenSSL error queue not reachable: TLS errors may spread between connections")
        return False

    def before(method):
        @functools.wraps(method)
        def call(self, *args, **kwargs):
            clear()
            return method(self, *args, **kwargs)
        return call

    def after(method):
        @functools.wraps(method)
        def call(self, *args, **kwargs):
            try:
                return method(self, *args, **kwargs)
            finally:
                clear()  # other greenlets ran during the wait; the TLS call is retried next
        return call

    for name in ('read', 'write', 'send', 'do_handshake', 'unwrap'):
        setattr(cls, name, before(getattr(cls, name)))
    cls._wait = after(cls._wait)
    cls._ucm_clears_tls_errors = True
    return True


# Gunicorn imports the worker class in the master before forking: every worker is covered
clear_tls_errors_before_io()


class MTLSWebSocketHandler(WebSocketHandler, PyWSGIHandler):
    """WebSocket handler that extracts client certificate from SSL socket.

    Also inherits Gunicorn's ``log_request`` (via PyWSGIHandler): geventwebsocket's
    handler derives straight from ``pywsgi.WSGIHandler``, which does NOT emit
    Gunicorn's access log — so with this worker ``access.log`` stayed empty no
    matter how many requests were served, and there was no way to tell whether a
    protocol client (SCEP/EST/ACME) had even reached the server. Listing
    PyWSGIHandler second keeps the WebSocket behaviour and only picks up the
    access-logging override.
    """

    def log_request(self):
        """Emit Gunicorn's access-log line for every served request.

        geventwebsocket's own ``log_request`` writes to its private logger via
        ``format_request()``, so nothing ever reached ``access.log``. Delegating
        to Gunicorn's implementation restores it. Access logging must never be
        able to fail a request, hence the guard: a WebSocket upgrade can reach
        here without the timing attributes Gunicorn expects.
        """
        try:
            PyWSGIHandler.log_request(self)
        except Exception:  # noqa: BLE001 — logging must not break serving
            try:
                super().log_request()
            except Exception:
                pass

    def get_environ(self):
        env = super().get_environ()
        # gevent hands the raw socket to any request with "Connection: upgrade"; outside a
        # real WebSocket handshake, a body read then waits for the proxy to close the connection
        if env.get('HTTP_UPGRADE', '').lower() != 'websocket':
            env['wsgi.input'] = self.wsgi_input
            env['wsgi.input_terminated'] = True
        # Extract client certificate from SSL socket (mTLS)
        sock = self.socket
        if isinstance(sock, ssl.SSLSocket):
            try:
                peercert_der = sock.getpeercert(binary_form=True)
                if peercert_der:
                    env['peercert'] = peercert_der
            except (ssl.SSLError, OSError, ValueError):
                pass
        binding = _tls_unique(sock)
        if binding:
            env['ucm.tls_unique'] = binding
        return env


def _tls_unique(sock):
    """The RFC 5929 tls-unique binding of a native TLS 1.2 or older connection,
    else None: RFC 9266 leaves it undefined in TLS 1.3."""
    try:
        if sock.version() not in ('TLSv1', 'TLSv1.1', 'TLSv1.2'):
            return None
        return sock.get_channel_binding('tls-unique')
    except (AttributeError, ssl.SSLError, OSError, ValueError):
        return None


class MTLSGeventWebSocketWorker(GeventWebSocketWorker):
    """Gunicorn worker that uses MTLSWebSocketHandler for peercert injection."""
    wsgi_handler = MTLSWebSocketHandler
