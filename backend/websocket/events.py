"""
WebSocket events handler and emitter.
Provides real-time event broadcasting to connected clients.
"""

import importlib.util
import logging
import socket
from typing import Any, Dict, Optional
from urllib.parse import parse_qs, urlparse

import socketio as socketio_pkg

from flask import request
from flask_socketio import SocketIO

from config.settings import redis_url as config_redis_url
from .event_types import EventType
from utils.datetime_utils import utc_now

logger = logging.getLogger(__name__)

# SocketIO instance - initialized in init_websocket()
socketio = SocketIO()

# Worker-local socket state; counts and rooms are per worker by design.
connected_clients: Dict[str, Dict[str, Any]] = {}

_QUEUE_SCHEMES = ("redis", "rediss", "unix")
_KEEPALIVE_OPTIONS = {
    opt: value
    for name, value in (("TCP_KEEPIDLE", 10), ("TCP_KEEPINTVL", 5), ("TCP_KEEPCNT", 3))
    if (opt := getattr(socket, name, None)) is not None
}


def _queue_channel(url: str, key_prefix: str) -> str:
    """Pub/sub ignores the Redis database number: scope the channel like the session keys."""
    parsed = urlparse(url)
    db = (parse_qs(parsed.query).get("db") or [None])[0]
    if db is None:
        parts = [part for part in parsed.path.split("/") if part]
        if parsed.scheme in ("redis", "rediss") and parts:
            db = parts[0]
    return f"{key_prefix}socketio:{db or 0}"


def _message_queue(app) -> Optional[socketio_pkg.RedisManager]:
    """A Redis manager on the session store's URL, or None to stay on this instance."""
    url = config_redis_url()
    if not url:
        return None
    if importlib.util.find_spec("redis") is None:
        logger.warning("redis library not installed, WebSocket events stay on this instance")
        return None
    if urlparse(url).scheme not in _QUEUE_SCHEMES:
        logger.warning("Unsupported Redis URL scheme, WebSocket events stay on this instance")
        return None
    # Bound each emit on an unreachable or silently dead Redis; a read timeout
    # would also hit the idle pub/sub listener, so keepalive detects dead peers.
    return socketio_pkg.RedisManager(
        url,
        channel=_queue_channel(url, app.config.get("SESSION_KEY_PREFIX", "ucm:session:")),
        redis_options={
            "socket_connect_timeout": 2,
            "socket_keepalive": True,
            "socket_keepalive_options": _KEEPALIVE_OPTIONS,
        },
    )
# ================== Initialization ==================
def init_websocket(app):
    """Initialize WebSocket with Flask app."""
    # PLANB-A.1: à implémenter selon SPEC (contrôle de CORS_ORIGINS, réglages optionnels)
    message_queue = _message_queue(app)
    socketio.init_app(
        app,
        cors_allowed_origins=app.config.get('CORS_ORIGINS'),
        async_mode='gevent',
        client_manager=message_queue,
        manage_session=False,
        ping_timeout=60,
        ping_interval=25)
    logger.info("WebSocket initialized (message queue: %s)", bool(message_queue))
    return socketio


# ================== Socket Event Handlers ==================
# PLANB-A.1: handshake par session et rooms gérées par le serveur, à implémenter selon SPEC
@socketio.on('connect')
def handle_connect(auth=None):
    return False  # fail closed until implemented
# PLANB-A.1: nettoyage local à la déconnexion, à compléter selon SPEC
@socketio.on('disconnect')
def handle_disconnect():
    connected_clients.pop(request.sid, None)
# PLANB-A.1: subscribe (revalidation, autorisation, plafonds, débit), à implémenter selon SPEC
@socketio.on('subscribe')
def handle_subscribe(data=None):
    raise NotImplementedError('PLANB-A.1')
# PLANB-A.1: unsubscribe, à implémenter selon SPEC
@socketio.on('unsubscribe')
def handle_unsubscribe(data=None):
    raise NotImplementedError('PLANB-A.1')
# PLANB-A.1: ping (revalidation puis pong), à implémenter selon SPEC
@socketio.on('ping')
def handle_ping():
    raise NotImplementedError('PLANB-A.1')
# ================== Event Emitter Functions ==================
# PLANB-A.1: émission de base (validation du payload et de la room), à implémenter selon SPEC
def emit_event(event_type, data, room=None, include_self=True):
    raise NotImplementedError('PLANB-A.1')
# PLANB-A.1: émissions ciblées, à implémenter selon SPEC
def emit_to_user(user_id, event_type, data):
    raise NotImplementedError('PLANB-A.1')
def emit_certificate_event(event_type, cert_data):
    raise NotImplementedError('PLANB-A.1')
def emit_ca_event(event_type, ca_data):
    raise NotImplementedError('PLANB-A.1')
def emit_system_alert(alert_type: str, message: str, severity: str = 'info', details: Optional[Dict] = None):
    raise NotImplementedError('PLANB-A.1')
def emit_audit_critical(action, user, resource, details=None):
    raise NotImplementedError('PLANB-A.1')
# PLANB-A.1: diffusion sur une room de scope, à implémenter et exporter selon SPEC (nom libre)
# ================== Stats & Management ==================
def get_connected_clients_count() -> int:
    """Return the connected client count of this worker."""
    return len(connected_clients)
# PLANB-A.1: statut sans identifiant, à implémenter selon SPEC
def get_connected_clients_info() -> Dict[str, Any]:
    raise NotImplementedError('PLANB-A.1')
