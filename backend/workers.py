"""
Custom Gunicorn workers for UCM

Extends GeventWebSocketWorker to inject SSL client certificate (peercert)
into the WSGI environ, enabling native mTLS authentication without a
reverse proxy.
"""
from geventwebsocket.handler import WebSocketHandler
from geventwebsocket.gunicorn.workers import GeventWebSocketWorker
from gunicorn.workers.ggevent import PyWSGIHandler
import ssl
import logging

logger = logging.getLogger(__name__)


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
        return env


class MTLSGeventWebSocketWorker(GeventWebSocketWorker):
    """Gunicorn worker that uses MTLSWebSocketHandler for peercert injection."""
    wsgi_handler = MTLSWebSocketHandler

    def handle_exit(self, sig, frame):
        super().handle_exit(sig, frame)
        # The replacement worker takes the scheduler over without waiting for
        # this one's connections to drain; out of the signal handler, like handle_quit
        import gevent
        from services.scheduler_service import get_scheduler
        gevent.spawn(get_scheduler().relinquish)
