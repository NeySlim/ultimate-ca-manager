"""
WebSocket events handler and emitter.
Provides real-time event broadcasting to connected clients.
"""

import hashlib
import importlib.util
import json
import logging
import os
import re
import socket
import threading
import time
from collections import deque
from enum import Enum
from typing import Any, Dict, Optional
from urllib.parse import parse_qs, urlparse

import socketio as socketio_pkg

from flask import current_app, has_request_context, request, session
from flask_socketio import SocketIO, disconnect, emit, join_room, leave_room
from flask_socketio import ConnectionRefusedError as HandshakeRefused

from auth.password_change_gate import password_change_pending
from auth.session_epoch import SESSION_KEY as EPOCH_SESSION_KEY
from auth.twofa_enforcement import ENROLL_SESSION_KEY
from auth.unified import AuthManager, has_permission
from config.settings import redis_url as config_redis_url
from .emitters import (ROOM_AUDIT, ROOM_CAS, ROOM_CERTIFICATES, ROOM_SSH, ROOM_SSH_CAS,
                       ROOM_SYSTEM_ALERTS)
from .event_types import EventType
from utils.datetime_utils import utc_isoformat, utc_now

logger = logging.getLogger(__name__)

# SocketIO instance - initialized in init_websocket()
socketio = SocketIO()

# Worker-local socket state; counts and rooms are per worker by design.
connected_clients: Dict[str, Dict[str, Any]] = {}

# True once init_websocket gave SocketIO a message queue: it carries every process's events
_queue_in_use = False
# Without a message queue: events go to the other processes through the database
# (services.ws_relay); the scheduler process emits nowhere else, an HA web worker also here
_relay_publisher = None
_relay_emits_here = False

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
    options = {"socket_connect_timeout": 2}
    if urlparse(url).scheme != "unix":  # TCP options: a Unix socket connection refuses them
        options.update(socket_keepalive=True, socket_keepalive_options=_KEEPALIVE_OPTIONS)
    return _session_ending(socketio_pkg.RedisManager)(
        url,
        channel=_queue_channel(url, app.config.get("SESSION_KEY_PREFIX", "ucm:session:")),
        redis_options=options,
    )


def _session_ending(base):
    """``base`` whose queue listener ends a session's sockets on its host instead of emitting.

    Built on call: the manager class stays the one ``socketio_pkg`` names."""
    class SessionEndingManager(base):
        def _handle_emit(self, message):
            if message.get('event') == SESSION_END_EVENT and message.get('room') == SESSION_END_ROOM:
                data = message.get('data')
                apply_session_end_here(data[0] if isinstance(data, list) and data else data)
                return
            super()._handle_emit(message)
    return SessionEndingManager


# ================== Policy ==================
# Every socket needs this permission; each scope permission maps to a server-managed room.
MIN_PERMISSION = 'read:certificates'
SCOPE_ROOMS = {
    'read:certificates': ROOM_CERTIFICATES,
    'read:cas': ROOM_CAS,
    'read:ssh': ROOM_SSH,
    'read:ssh_cas': ROOM_SSH_CAS,
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
# The server's own round over its sockets: a socket that only listens is checked within
# the revalidation delay plus one tick
REVALIDATE_TICK_SECONDS = 15.0
# A check that cannot reach the database or the session store keeps the socket this many
# revalidation delays after the first such failure, then cuts it; a refusal cuts at once
UNVERIFIED_GRACE_DELAYS = 2
# What a handshake refused for that reason tells the browser (connect_error), which tries again
HANDSHAKE_UNAVAILABLE = 'session check unavailable'
REVALIDATOR_NAME = 'WebSocketRevalidator'
ALERT_SEVERITIES = frozenset({'info', 'warning', 'error', 'critical'})

# Detail keys and values never forwarded with a critical audit event.
_SECRET_KEY_RE = re.compile(
    r'pass(?:word|wd|phrase)?|pwd|secret|token|credential|private|api[-_]?key|session|^sid$'
    r'|cookie|auth|bearer|jwt|csrf|body|payload|trace|stack|exception|otp|^pin$|^key$',
    re.IGNORECASE)
_SECRET_VALUE_MARKERS = ('PRIVATE KEY-----', 'Traceback (most recent call last)')
_DETAILS_MAX_DEPTH = 8

# A session's end (lock) told to every process: a room no socket joins and emit_event refuses
SESSION_END_ROOM = 'control:session-end'
SESSION_END_EVENT = 'session.end'

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


def _checked_origins(app) -> list:
    """Normalized start origins; invalid entries are skipped, `*` or nothing usable refuses."""
    from utils.public_endpoints import normalize_origin
    origins = app.config.get('CORS_ORIGINS')
    if not isinstance(origins, (list, tuple)) or not origins:
        raise RuntimeError('CORS_ORIGINS must be a non-empty list of explicit http(s) origins')
    kept = []
    for origin in origins:
        if isinstance(origin, str) and origin.strip().rstrip('/') == '*':
            raise RuntimeError('CORS_ORIGINS must not allow every origin for the WebSocket')
        normalized = normalize_origin(origin)
        if normalized is None:
            logger.warning("Ignoring invalid WebSocket origin in CORS_ORIGINS: %r", origin)
        elif normalized not in kept:
            kept.append(normalized)
    if not kept:
        raise RuntimeError('CORS_ORIGINS holds no explicit http(s) origin')
    return kept


def _engineio_origin_check(app):
    """Engine.IO's origin check, on the live list; the WSGI gate in front answers 403 first."""
    from .origin_gate import ACCEPTED_KEY, origin_accepted

    def accepted(origin, environ=None):
        if not origin:
            return False
        if environ is not None and environ.get(ACCEPTED_KEY) == origin:
            return True
        with app.app_context():
            return origin_accepted(origin)
    return accepted


# ================== Initialization ==================
def init_websocket(app):
    """Initialize WebSocket with Flask app; refuses to start without explicit origins."""
    global _queue_in_use
    _checked_origins(app)
    message_queue = _message_queue(app)
    _queue_in_use = message_queue is not None
    socketio.init_app(
        app,
        cors_allowed_origins=_engineio_origin_check(app),
        async_mode=_setting(app, 'WEBSOCKET_ASYNC_MODE', 'gevent'),
        client_manager=message_queue,
        manage_session=False,
        ping_timeout=int(_setting(app, 'WEBSOCKET_PING_TIMEOUT', 60)),
        ping_interval=int(_setting(app, 'WEBSOCKET_PING_INTERVAL', 25)),
        logger=_flag(_setting(app, 'WEBSOCKET_LOGGER', False)),
        engineio_logger=_flag(_setting(app, 'WEBSOCKET_ENGINEIO_LOGGER', False)))
    logger.info("WebSocket initialized (message queue: %s)", bool(message_queue))
    return socketio


def message_queue_in_use() -> bool:
    return _queue_in_use


def relay_through(publisher, emit_here=False):
    """Route this process's events to ``publisher`` (None: emit them here again only)."""
    global _relay_publisher, _relay_emits_here
    _relay_publisher = publisher
    _relay_emits_here = bool(emit_here) and publisher is not None


# ================== Identity and rooms ==================
def _user_room(user_id) -> str:
    return f'user:{user_id}'


def _enrollment_pending() -> bool:
    # Invariant 27 (pending maintainer review): a session limited to 2FA enrollment gets no socket.
    return bool(session.get(ENROLL_SESSION_KEY))


class SessionCheckUnavailable(Exception):
    """The database or the session store did not answer: neither a valid session nor a refusal."""


def _session_identity():
    """(user_id, permissions) for a full, valid session cookie holding the minimum permission,
    None for a refusal; SessionCheckUnavailable when the session could not be read."""
    try:
        info = AuthManager().verify_session()
    except Exception as exc:  # noqa: BLE001
        raise SessionCheckUnavailable(f'{type(exc).__name__}: {exc}') from exc
    if not info:
        return None
    if _enrollment_pending() or password_change_pending(info):
        return None
    permissions = frozenset(p for p in (info.get('permissions') or []) if isinstance(p, str))
    if not has_permission(MIN_PERMISSION, permissions):
        return None
    return info['user_id'], permissions


def session_key(session_id) -> Optional[str]:
    """What names a session's sockets to the other processes: a digest, never the id itself."""
    if not isinstance(session_id, str) or not session_id:
        return None
    return hashlib.sha256(session_id.encode()).hexdigest()[:32]


def _handshake_session_key() -> Optional[str]:
    return session_key(getattr(session, 'sid', None))


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


def _unverified_grace() -> float:
    return UNVERIFIED_GRACE_DELAYS * _revalidate_after()


def _check_unavailable(state, exc) -> Optional[str]:
    """A check that could not read the session: the socket stays until the grace, counted from
    its first such failure, has run out; ``validated_at`` stays, so every round tries again."""
    now = _monotonic()
    since = state.get('unverified_since')
    if since is None:
        state['unverified_since'] = since = now
        logger.warning("WebSocket session check unavailable, socket kept for now: %s", exc)
    if now - since >= _unverified_grace():
        return 'session check unavailable'
    return None


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
    except Exception as exc:  # noqa: BLE001  # the local state is already gone
        logger.warning("Could not close WebSocket client: %s", exc)


def _refresh(sid, state, identity) -> Optional[str]:
    """Why the socket must close under its session's ``identity`` as it is now, else None
    once the scope rooms of its new permissions are joined."""
    reason = _revalidation_failure(state, identity)
    if reason:
        return reason
    permissions = identity[1]
    for room in _scope_rooms(permissions) - state['managed_rooms']:
        join_room(room, sid=sid, namespace='/')
        state['managed_rooms'].add(room)
        state['rooms'].add(room)
    state['permissions'] = permissions
    state['validated_at'] = _monotonic()
    state['unverified_since'] = None
    return None


def _current_client():
    """State of the calling socket, revalidated when due; None once it has been cut."""
    sid = request.sid
    state = connected_clients.get(sid)
    if state is None:
        _drop(sid, 'no local state')
        return None
    if _monotonic() - state['validated_at'] < _revalidate_after():
        return state
    try:
        reason = _refresh(sid, state, _session_identity())
    except SessionCheckUnavailable as exc:
        reason = _check_unavailable(state, exc)
    if reason:
        _drop(sid, reason)
        return None
    return state


def _stored_identity(app, environ):
    """``_session_identity()`` of the session the store holds now for the handshake's cookie."""
    try:
        with app.request_context(environ):
            return _session_identity()
    except SessionCheckUnavailable:
        raise
    except Exception as exc:  # noqa: BLE001  # the store did not open the session
        raise SessionCheckUnavailable(f'{type(exc).__name__}: {exc}') from exc


def _check_away(app, sid, state) -> Optional[str]:
    """``_refresh`` outside any message: the session read again from the socket's handshake."""
    environ = socketio.server.get_environ(sid, namespace='/')
    if environ is None:
        return 'no handshake left'
    with app.app_context():
        try:
            return _refresh(sid, state, _stored_identity(app, environ))
        except Exception as exc:  # noqa: BLE001  # neither valid nor refused: checked again next round
            return _check_unavailable(state, exc)


def revalidate_due_sockets(app) -> int:
    """This process's sockets due for revalidation, checked against their session as it is now,
    as their next message would be: one that only listens sends none. Returns the count cut."""
    with app.app_context():
        after = _revalidate_after()
    cut = 0
    for sid, state in list(connected_clients.items()):
        if _monotonic() - state['validated_at'] < after:
            continue
        reason = _check_away(app, sid, state)
        if reason and connected_clients.get(sid) is state:
            logger.info("WebSocket client disconnected by the server: %s", reason)
            cut += _close_here([sid])
        socketio.sleep(0)  # under gevent: the requests run between two sockets
    return cut


class _Revalidator:
    """The process's one timer over its sockets; a thread that gevent's patching makes a greenlet."""

    def __init__(self, app, tick):
        self.app, self.tick = app, tick
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._loop, daemon=True, name=REVALIDATOR_NAME)

    def _loop(self):
        while not self._stop.wait(self.tick):
            try:
                revalidate_due_sockets(self.app)
            except Exception as exc:  # noqa: BLE001  # the next tick tries again
                logger.error("WebSocket sockets not revalidated: %s", type(exc).__name__)

    def start(self):
        self._thread.start()
        return self

    def stop(self, timeout=5.0):
        self._stop.set()
        if self._thread is not threading.current_thread():
            self._thread.join(timeout)


_revalidator: Optional[_Revalidator] = None


def start_revalidator(app, tick=REVALIDATE_TICK_SECONDS) -> _Revalidator:
    """Web worker (post_worker_init): one per process, whatever the event transport."""
    global _revalidator
    if _revalidator is None:
        _revalidator = _Revalidator(app, tick).start()
    return _revalidator


def stop_revalidator():
    global _revalidator
    revalidator, _revalidator = _revalidator, None
    if revalidator is not None:
        revalidator.stop()


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
    """Session cookie only: the auth payload, query string and API key headers are ignored.
    A session that could not be read is refused as unavailable, which the browser tries again."""
    try:
        identity = _session_identity()
    except SessionCheckUnavailable as exc:
        raise _unavailable(exc) from exc
    if identity is None:
        logger.debug("WebSocket connection refused: no valid session")
        return False
    user_id, permissions = identity
    managed = {_user_room(user_id)} | _scope_rooms(permissions)
    state = {
        'user_id': user_id,
        'permissions': permissions,
        'managed_rooms': set(managed),
        'rooms': set(managed),
        'connected_at': utc_now(),
        'auth_method': 'session',
        'session': _handshake_session_key(),
        # What an account's or a restore's end of sessions compares (end_account_sockets)
        'session_version': _int_or_zero(session.get('session_version')),
        'epoch': _int_or_zero(session.get(EPOCH_SESSION_KEY)),
        'validated_at': _monotonic(),
        'unverified_since': None,
        'ops': deque(maxlen=SUBSCRIPTION_OPS_LIMIT),
    }
    # Listed first, then read again: a cut committed since the check above either finds the
    # socket listed or shows here
    connected_clients[request.sid] = state
    for room in managed:
        join_room(room)
    try:
        current = _still_current(state)
    except SessionCheckUnavailable as exc:
        connected_clients.pop(request.sid, None)
        raise _unavailable(exc) from exc
    if not current or connected_clients.get(request.sid) is not state:
        connected_clients.pop(request.sid, None)
        logger.info("WebSocket connection refused: its session ended during the handshake")
        return False
    emit('connected', {'status': 'ok', 'user_id': user_id, 'timestamp': _timestamp()})
    return True


def _unavailable(exc) -> HandshakeRefused:
    logger.warning("WebSocket connection refused, session check unavailable: %s", exc)
    return HandshakeRefused(HANDSHAKE_UNAVAILABLE)


def _still_current(state) -> bool:
    """The account is still active, at the socket's session version, under its epoch, read in a
    new transaction (a SQLite snapshot would show the rows as the check read them), and its
    session as the store holds it now (signed out, locked or replaced meanwhile) still valid
    for the same identity. SessionCheckUnavailable when either could not be read."""
    from auth.session_epoch import current_epoch
    from models import User, db
    try:
        db.session.rollback()
        row = db.session.execute(db.select(User.active, User.session_version)
                                 .where(User.id == state['user_id'])).first()
        if not (row is not None and bool(row.active)
                and (row.session_version or 0) == state['session_version']
                and current_epoch() == state['epoch']):
            return False
    except Exception as exc:  # noqa: BLE001
        raise SessionCheckUnavailable(f'{type(exc).__name__}: {exc}') from exc
    identity = _stored_identity(current_app._get_current_object(), request.environ)
    return _revalidation_failure(state, identity) is None


def _int_or_zero(value) -> int:
    return value if isinstance(value, int) and not isinstance(value, bool) else 0


def _close_here(sids) -> int:
    for sid in sids:
        connected_clients.pop(sid, None)
        try:
            socketio.server.disconnect(sid, namespace='/', ignore_queue=True)
        except Exception as exc:  # noqa: BLE001  # the local state is already gone
            logger.warning("Could not close WebSocket client: %s", exc)
    return len(sids)


def _cut_where(predicate, what) -> int:
    cut = _close_here([sid for sid, state in list(connected_clients.items()) if predicate(state)])
    if cut:
        logger.info("WebSocket: %d socket(s) of %s closed", cut, what)
    return cut


def cut_session_here(key) -> int:
    """Close this process's sockets of the session ``key`` names; the others are left open."""
    if not isinstance(key, str) or not key:
        return 0
    return _cut_where(lambda state: state.get('session') == key, 'an ended session')


def cut_account_here(user_id, below=None, spare=None) -> int:
    """Close this process's sockets of account ``user_id`` opened under a session version
    lower than ``below`` (every one when None), but the one of session key ``spare``."""
    if not isinstance(user_id, int) or isinstance(user_id, bool):
        return 0
    if below is not None and (not isinstance(below, int) or isinstance(below, bool)):
        return 0
    return _cut_where(lambda state: (state.get('user_id') == user_id
                                     and (below is None or state.get('session_version', 0) < below)
                                     and (spare is None or state.get('session') != spare)),
                      'an account whose sessions ended')


def cut_before_epoch_here(epoch) -> int:
    """Close this process's sockets opened before the restore that set ``epoch``."""
    if not isinstance(epoch, int) or isinstance(epoch, bool):
        return 0
    return _cut_where(lambda state: state.get('epoch', 0) < epoch, 'sessions a restore ended')


def apply_session_end_here(data) -> int:
    """A session end told by any process, applied to this one's sockets."""
    if not isinstance(data, dict):
        return 0
    if 'user' in data:
        return cut_account_here(data.get('user'), data.get('below'), data.get('spare'))
    if 'epoch_below' in data:
        return cut_before_epoch_here(data.get('epoch_below'))
    return cut_session_here(data.get('session'))


def _tell_other_processes(payload):
    """Through the transport events take (database relay or Redis queue); never raises."""
    publisher = _relay_publisher
    try:
        if publisher is not None:
            publisher.publish(SESSION_END_ROOM, {'type': SESSION_END_EVENT, **payload})
        elif _queue_in_use:
            # The queue's listener on each host applies it instead of emitting (_session_ending)
            socketio.emit(SESSION_END_EVENT, payload, to=SESSION_END_ROOM)
    except Exception as exc:  # noqa: BLE001  # the revalidation still closes them later
        logger.warning("WebSocket session end not told to the other processes: %s", exc)


def end_session_sockets(session_id) -> int:
    """Close the sockets of this session here at once, and on the other processes through the
    transport their events take (database relay or Redis queue). Returns the count closed here."""
    key = session_key(session_id)
    if key is None:
        return 0
    cut = cut_session_here(key)
    _tell_other_processes({'session': key})
    return cut


def end_account_sockets(user_id, below=None, spare_session_id=None) -> int:
    """Close, on every process, the sockets of ``user_id``'s sessions older than version
    ``below`` (all of them when None), but those of ``spare_session_id``."""
    spare = session_key(spare_session_id)
    cut = cut_account_here(user_id, below, spare)
    _tell_other_processes({'user': user_id, 'below': below, 'spare': spare})
    return cut


def end_sockets_before_epoch(epoch) -> int:
    cut = cut_before_epoch_here(epoch)
    _tell_other_processes({'epoch_below': epoch})
    return cut


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
    publisher = _relay_publisher
    if publisher is not None:
        publisher.publish(room, payload)  # queues only, never raises
        if not _relay_emits_here:
            return
    # The skipped sid, if any, is a socket of this process: the relayed copies need no option
    options = {'to': room}
    if not include_self and _calling_sid():
        options['skip_sid'] = _calling_sid()
    try:
        socketio.emit('event', payload, **options)
    except Exception as exc:  # noqa: BLE001  # a dead transport must not reach business code
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
