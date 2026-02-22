"""
Custom Gunicorn workers for UCM

Extends GeventWebSocketWorker to inject SSL client certificate (peercert)
into the WSGI environ, enabling native mTLS authentication without a
reverse proxy.
"""
from geventwebsocket.handler import WebSocketHandler
from geventwebsocket.gunicorn.workers import GeventWebSocketWorker
import ssl
import logging

logger = logging.getLogger(__name__)


class MTLSWebSocketHandler(WebSocketHandler):
    """WebSocket handler that extracts client certificate from SSL socket."""

    def get_environ(self):
        env = super().get_environ()
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
