"""
WebSocket events handler and emitter.
Provides real-time event broadcasting to connected clients.
"""

import importlib.util
import json
import logging
import os
import re
import socket
import time
from collections import deque
from enum import Enum
from typing import Any, Dict, Optional
from urllib.parse import parse_qs, urlparse

import socketio as socketio_pkg

from flask import current_app, has_request_context, request, session
from flask_socketio import SocketIO, disconnect, emit, join_room, leave_room

from auth.password_change_gate import password_change_pending
from auth.twofa_enforcement import ENROLL_SESSION_KEY
from auth.unified import AuthManager, has_permission
from config.settings import redis_url as config_redis_url
from .emitters import ROOM_AUDIT, ROOM_CAS, ROOM_CERTIFICATES, ROOM_SYSTEM_ALERTS
from .event_types import EventType
from utils.datetime_utils import utc_isoformat, utc_now

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


# ================== Policy ==================
# Every socket needs this permission; each scope permission maps to a server-managed room.
MIN_PERMISSION = 'read:certificates'
SCOPE_ROOMS = {
    'read:certificates': ROOM_CERTIFICATES,
    'read:cas': ROOM_CAS,
    'read:system': ROOM_SYSTEM_ALERTS,
    'read:audit': ROOM_AUDIT,
}
SCOPE_ROOM_NAMES = frozenset(SCOPE_ROOMS.values())
# Resource rooms other than one's own user room require both of these.
PRIVILEGED_PERMISSIONS = ('read:certificates', 'read:cas')

ROOM_NAME_MAX_LENGTH = 128
_RESOURCE_ROOM_RE = re.compile(r'(?:ca|cert|user|group):[A-Za-z0-9][A-Za-z0-9_.:-]*')
MAX_ROOMS_PER_SOCKET = 100
MAX_ROOMS_PER_REQUEST = 25
SUBSCRIPTION_OPS_LIMIT = 30
SUBSCRIPTION_WINDOW_SECONDS = 60.0
DEFAULT_REVALIDATE_SECONDS = 60.0
ALERT_SEVERITIES = frozenset({'info', 'warning', 'error', 'critical'})

# Detail keys and values never forwarded with a critical audit event.
_SECRET_KEY_RE = re.compile(
    r'pass(?:word|wd|phrase)?|pwd|secret|token|credential|private|api[-_]?key|session|^sid$'
    r'|cookie|auth|bearer|jwt|csrf|body|payload|trace|stack|exception|otp|^pin$|^key$',
    re.IGNORECASE)
_SECRET_VALUE_MARKERS = ('PRIVATE KEY-----', 'Traceback (most recent call last)')
_DETAILS_MAX_DEPTH = 8

# Injectable clock for revalidation and rate limiting.
_monotonic = time.monotonic


class WebSocketValidationError(ValueError):
    """An outgoing event, its room or its arguments failed validation; nothing was sent."""


def _setting(app, name, default):
    """app.config first, then the environment, then the default."""
    value = app.config.get(name)
    if value is None or value == '':
        value = os.environ.get(name)
    return default if value is None or value == '' else value


def _flag(value) -> bool:
    if isinstance(value, str):
        return value.strip().lower() in ('1', 'true', 'yes', 'on')
    return bool(value)


def _timestamp() -> str:
    return utc_isoformat(utc_now())


def _is_explicit_origin(origin) -> bool:
    """scheme://host[:port] over http(s), with no wildcard, path, query or credentials."""
    if not isinstance(origin, str) or '*' in origin:
        return False
    parsed = urlparse(origin)
    try:
        parsed.port
    except ValueError:
        return False
    return (parsed.scheme in ('http', 'https') and bool(parsed.hostname)
            and parsed.username is None and parsed.password is None
            and not (parsed.path or parsed.params or parsed.query or parsed.fragment))


def _checked_origins(app) -> list:
    """Normalized explicit origins; invalid entries are skipped, `*` or nothing usable refuses."""
    origins = app.config.get('CORS_ORIGINS')
    if not isinstance(origins, (list, tuple)) or not origins:
        raise RuntimeError('CORS_ORIGINS must be a non-empty list of explicit http(s) origins')
    kept = []
    for origin in origins:
        normalized = origin.strip().rstrip('/') if isinstance(origin, str) else origin
        if normalized == '*':
            raise RuntimeError('CORS_ORIGINS must not allow every origin for the WebSocket')
        if not _is_explicit_origin(normalized):
            logger.warning("Ignoring invalid WebSocket origin in CORS_ORIGINS: %r", origin)
        elif normalized not in kept:
            kept.append(normalized)
    if not kept:
        raise RuntimeError('CORS_ORIGINS holds no explicit http(s) origin')
    return kept


# ================== Initialization ==================
def init_websocket(app):
    """Initialize WebSocket with Flask app; refuses to start without explicit origins."""
    origins = _checked_origins(app)
    message_queue = _message_queue(app)
    socketio.init_app(
        app,
        cors_allowed_origins=origins,
        async_mode=_setting(app, 'WEBSOCKET_ASYNC_MODE', 'gevent'),
        client_manager=message_queue,
        manage_session=False,
        ping_timeout=int(_setting(app, 'WEBSOCKET_PING_TIMEOUT', 60)),
        ping_interval=int(_setting(app, 'WEBSOCKET_PING_INTERVAL', 25)),
        logger=_flag(_setting(app, 'WEBSOCKET_LOGGER', False)),
        engineio_logger=_flag(_setting(app, 'WEBSOCKET_ENGINEIO_LOGGER', False)))
    logger.info("WebSocket initialized (message queue: %s)", bool(message_queue))
    return socketio


# ================== Identity and rooms ==================
def _user_room(user_id) -> str:
    return f'user:{user_id}'


def _enrollment_pending() -> bool:
    # Invariant 27 (pending maintainer review): a session limited to 2FA enrollment gets no socket.
    return bool(session.get(ENROLL_SESSION_KEY))


def _session_identity():
    """(user_id, permissions) for a full, valid session cookie holding the minimum permission."""
    try:
        info = AuthManager().verify_session()
    except Exception as exc:  # noqa: BLE001: an unverifiable session is no session
        logger.warning("WebSocket session check failed, treated as no session: %s", exc)
        return None
    if not info:
        return None
    if _enrollment_pending() or password_change_pending(info):
        return None
    permissions = frozenset(p for p in (info.get('permissions') or []) if isinstance(p, str))
    if not has_permission(MIN_PERMISSION, permissions):
        return None
    return info['user_id'], permissions


def _scope_rooms(permissions) -> set:
    return {room for perm, room in SCOPE_ROOMS.items() if has_permission(perm, permissions)}


def _is_privileged(permissions) -> bool:
    return all(has_permission(perm, permissions) for perm in PRIVILEGED_PERMISSIONS)


def _valid_room_name(room) -> bool:
    return (isinstance(room, str) and len(room) <= ROOM_NAME_MAX_LENGTH
            and _RESOURCE_ROOM_RE.fullmatch(room) is not None)


def _revalidate_after() -> float:
    try:
        return max(0.0, float(_setting(current_app, 'WEBSOCKET_REVALIDATE_SECONDS',
                                       DEFAULT_REVALIDATE_SECONDS)))
    except (TypeError, ValueError):
        return DEFAULT_REVALIDATE_SECONDS


def _revalidation_failure(state, identity) -> Optional[str]:
    if identity is None:
        return 'session no longer valid'
    user_id, permissions = identity
    if user_id != state['user_id']:
        return 'session identity changed'
    # Literal set difference: losing any permission, related to rooms or not, ends the socket.
    if state['permissions'] - permissions:
        return 'permission withdrawn'
    return None


def _drop(sid, reason):
    """Forget the socket locally, then close it: it receives nothing more."""
    connected_clients.pop(sid, None)
    logger.info("WebSocket client disconnected by the server: %s", reason)
    try:
        disconnect(sid)
    except Exception as exc:  # noqa: BLE001: the local state is already gone
        logger.warning("Could not close WebSocket client: %s", exc)


def _current_client():
    """State of the calling socket, revalidated when due; None once it has been cut."""
    sid = request.sid
    state = connected_clients.get(sid)
    if state is None:
        _drop(sid, 'no local state')
        return None
    if _monotonic() - state['validated_at'] < _revalidate_after():
        return state
    identity = _session_identity()
    reason = _revalidation_failure(state, identity)
    if reason:
        _drop(sid, reason)
        return None
    permissions = identity[1]
    for room in _scope_rooms(permissions) - state['managed_rooms']:
        join_room(room)
        state['managed_rooms'].add(room)
        state['rooms'].add(room)
    state['permissions'] = permissions
    state['validated_at'] = _monotonic()
    return state


def _rate_limited(state) -> bool:
    """Sliding window: every subscribe/unsubscribe request counts, refused ones included."""
    now = _monotonic()
    ops = state['ops']
    while ops and now - ops[0] >= SUBSCRIPTION_WINDOW_SECONDS:
        ops.popleft()
    limited = len(ops) >= SUBSCRIPTION_OPS_LIMIT
    ops.append(now)  # the deque keeps the latest LIMIT requests, enough to decide
    return limited


def _requested_rooms(data):
    """The `rooms` list of a payload, or None when there is no such list."""
    if not isinstance(data, dict):
        return None
    rooms = data.get('rooms')
    return rooms if isinstance(rooms, list) else None


def _subscription_error(error, message):
    emit('subscription_error', {'error': error, 'message': message})


def _checked_request(state, data, reply):
    """Valid distinct room names of the request, or None once an answer has been sent."""
    if _rate_limited(state):
        _subscription_error('rate_limited', 'Too many subscription requests, slow down')
        return None
    requested = _requested_rooms(data)
    if requested is None:
        emit(reply, {'rooms': []})
        return None
    if len(requested) > MAX_ROOMS_PER_REQUEST:
        _subscription_error('too_many_rooms',
                            f'At most {MAX_ROOMS_PER_REQUEST} rooms per request')
        return None
    return list(dict.fromkeys(room for room in requested if _valid_room_name(room)))


# ================== Socket Event Handlers ==================
@socketio.on('connect')
def handle_connect(auth=None):
    """Session cookie only: the auth payload, query string and API key headers are ignored."""
    identity = _session_identity()
    if identity is None:
        logger.debug("WebSocket connection refused: no valid session")
        return False
    user_id, permissions = identity
    managed = {_user_room(user_id)} | _scope_rooms(permissions)
    for room in managed:
        join_room(room)
    connected_clients[request.sid] = {
        'user_id': user_id,
        'permissions': permissions,
        'managed_rooms': set(managed),
        'rooms': set(managed),
        'connected_at': utc_now(),
        'auth_method': 'session',
        'validated_at': _monotonic(),
        'ops': deque(maxlen=SUBSCRIPTION_OPS_LIMIT),
    }
    emit('connected', {'status': 'ok', 'user_id': user_id, 'timestamp': _timestamp()})
    return True


@socketio.on('disconnect')
def handle_disconnect(reason=None):
    connected_clients.pop(request.sid, None)


@socketio.on('subscribe')
def handle_subscribe(data=None):
    state = _current_client()
    if state is None:
        return
    rooms = _checked_request(state, data, 'subscribed')
    if rooms is None:
        return
    joined = []
    own_room = _user_room(state['user_id'])
    for room in rooms:
        if room != own_room and not _is_privileged(state['permissions']):
            continue
        if room not in state['rooms']:
            if len(state['rooms']) >= MAX_ROOMS_PER_SOCKET:
                continue
            join_room(room)
            state['rooms'].add(room)
        joined.append(room)
    emit('subscribed', {'rooms': joined})


@socketio.on('unsubscribe')
def handle_unsubscribe(data=None):
    state = _current_client()
    if state is None:
        return
    rooms = _checked_request(state, data, 'unsubscribed')
    if rooms is None:
        return
    left = []
    for room in rooms:
        # Server-managed rooms (own user room, scopes) cannot be left.
        if room in state['managed_rooms'] or room not in state['rooms']:
            continue
        leave_room(room)
        state['rooms'].discard(room)
        left.append(room)
    emit('unsubscribed', {'rooms': left})


@socketio.on('ping')
def handle_ping(_data=None):
    if _current_client() is None:
        return
    emit('pong', {'timestamp': _timestamp()})


# ================== Event Emitter Functions ==================
def _event_name(event_type) -> str:
    value = event_type.value if isinstance(event_type, Enum) else event_type
    if not isinstance(value, str) or not value:
        raise WebSocketValidationError('event type must be a non-empty string')
    return value


def _checked_room(room) -> str:
    if not isinstance(room, str) or not room:
        raise WebSocketValidationError('room must be a non-empty string')
    if room not in SCOPE_ROOM_NAMES and not _valid_room_name(room):
        raise WebSocketValidationError(f'unknown room {room!r}')
    return room


def _check_payload(data):
    if not isinstance(data, dict):
        raise WebSocketValidationError('event data must be a dict')
    try:
        json.dumps(data, allow_nan=False)
    except (TypeError, ValueError) as exc:
        raise WebSocketValidationError(f'event data is not JSON serializable: {exc}') from exc


def _require_text(name, value):
    if not isinstance(value, str) or not value.strip():
        raise WebSocketValidationError(f'{name} must be a non-empty string')


def _calling_sid():
    return getattr(request, 'sid', None) if has_request_context() else None


def emit_event(event_type, data, room=None, include_self=True):
    """Validate, then send `event` to one explicit room; a transport failure is only logged."""
    room = _checked_room(room)
    type_name = _event_name(event_type)
    _check_payload(data)
    payload = {'type': type_name, 'data': data, 'timestamp': _timestamp()}
    options = {'to': room}
    if not include_self and _calling_sid():
        options['skip_sid'] = _calling_sid()
    try:
        socketio.emit('event', payload, **options)
    except Exception as exc:  # noqa: BLE001: a dead transport must not reach business code
        logger.warning("WebSocket emit of %s to %s failed: %s", type_name, room, exc)


def emit_to_scope(room, event_type, data):
    """Send to one of the server-managed scope rooms (ROOM_* of websocket.emitters)."""
    if room not in SCOPE_ROOM_NAMES:
        raise WebSocketValidationError(f'not a scope room: {room!r}')
    emit_event(event_type, data, room=room)


def emit_to_user(user_id, event_type, data):
    if isinstance(user_id, bool) or not isinstance(user_id, (int, str)) or user_id == '':
        raise WebSocketValidationError('user_id must be an integer or a non-empty string')
    emit_event(event_type, data, room=_user_room(user_id))


def emit_certificate_event(event_type, cert_data):
    emit_to_scope(ROOM_CERTIFICATES, event_type, cert_data)


def emit_ca_event(event_type, ca_data):
    emit_to_scope(ROOM_CAS, event_type, ca_data)


def emit_system_alert(alert_type: str, message: str, severity: str = 'info', details: Optional[Dict] = None):
    """Alert the system-alerts scope; invalid arguments raise before anything is sent."""
    _require_text('alert_type', alert_type)
    _require_text('message', message)
    if not isinstance(severity, str) or severity not in ALERT_SEVERITIES:
        raise WebSocketValidationError(f'severity must be one of {sorted(ALERT_SEVERITIES)}')
    if details is not None and not isinstance(details, dict):
        raise WebSocketValidationError('details must be a dict')
    emit_to_scope(ROOM_SYSTEM_ALERTS, EventType.SYSTEM_ALERT, {
        'alert_type': alert_type,
        'message': message,
        'severity': severity,
        'details': details or {},
    })


def _without_secrets(value, depth=0):
    """Copy of `value` without secret-looking keys, PEM private keys or tracebacks."""
    if depth > _DETAILS_MAX_DEPTH:
        return None
    if isinstance(value, dict):
        return {key: _without_secrets(item, depth + 1) for key, item in value.items()
                if not (isinstance(key, str) and _SECRET_KEY_RE.search(key))
                and not _is_secret_text(item)}
    if isinstance(value, (list, tuple)):
        return [_without_secrets(item, depth + 1) for item in value if not _is_secret_text(item)]
    return value


def _is_secret_text(value) -> bool:
    return isinstance(value, str) and any(marker in value for marker in _SECRET_VALUE_MARKERS)


def emit_audit_critical(action, user, resource, details=None):
    """Tell the audit scope about a critical action; never forwards secrets in `details`."""
    _require_text('action', action)
    _require_text('user', user)
    _require_text('resource', resource)
    if details is not None and not isinstance(details, dict):
        raise WebSocketValidationError('details must be a dict')
    emit_to_scope(ROOM_AUDIT, EventType.AUDIT_CRITICAL, {
        'action': action,
        'user': user,
        'resource': resource,
        'details': _without_secrets(details or {}),
    })


# ================== Stats & Management ==================
def get_connected_clients_count() -> int:
    """Return the connected client count of this worker."""
    return len(connected_clients)


def get_connected_clients_info() -> Dict[str, Any]:
    """Counts and anonymous per-socket facts: no user, session, permission or room name."""
    clients = [{
        'connected_at': utc_isoformat(state['connected_at']),
        'auth_method': state['auth_method'],
        'room_count': len(state['rooms']),
        'privileged': _is_privileged(state['permissions']),
    } for state in list(connected_clients.values())]
    return {'count': len(clients), 'local_worker_count': len(clients), 'clients': clients}
