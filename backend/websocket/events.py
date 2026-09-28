"""
WebSocket events handler and emitter.

Production-focused Socket.IO implementation with:

- Authenticated connections only (Flask session).
- Permission-scoped server-managed rooms.
- No unrestricted/global sensitive event broadcasts.
- Periodic session revalidation.
- Redis message queue when a Redis URL is configured, so events reach every instance.
- Strict room validation, subscription limits, and rate limits.
- JSON-safe event payload validation.
- Mandatory room protection.
"""

from __future__ import annotations

import importlib.util
import json
import logging
import re
import time
from collections import deque
from dataclasses import dataclass
from functools import wraps
from typing import Any, Callable, Deque, Dict, Iterable, Optional, Set, Tuple, Union
from urllib.parse import parse_qs, urlparse

import socketio as socketio_pkg

from flask import current_app, request, session
from flask_socketio import SocketIO, disconnect, emit, join_room, leave_room

from config.settings import redis_url as config_redis_url
from .event_types import EventType
from utils.datetime_utils import utc_now

logger = logging.getLogger(__name__)

# Socket.IO instance. Initialized in init_websocket().
socketio = SocketIO()

# Worker-local socket state; counts and rooms are per worker by design.
connected_clients: Dict[str, Dict[str, Any]] = {}


# ---------------------------------------------------------------------------
# Configuration defaults
# ---------------------------------------------------------------------------

_SOCKET_MIN_PERMISSION = "read:certificates"

DEFAULT_SESSION_REVALIDATE_SECONDS = 60

MAX_ROOM_NAME_LENGTH = 128
MAX_ROOMS_PER_REQUEST = 25
MAX_ROOMS_PER_SOCKET = 100

MAX_SUBSCRIPTION_OPERATIONS_PER_WINDOW = 30
SUBSCRIPTION_RATE_WINDOW_SECONDS = 60


# ---------------------------------------------------------------------------
# Server-managed authorization rooms
# ---------------------------------------------------------------------------

ROOM_CERTIFICATES = "scope:certificates"
ROOM_CAS = "scope:cas"
ROOM_SYSTEM_ALERTS = "scope:system-alerts"
ROOM_AUDIT = "scope:audit"

SERVER_MANAGED_ROOMS = {
    ROOM_CERTIFICATES,
    ROOM_CAS,
    ROOM_SYSTEM_ALERTS,
    ROOM_AUDIT,
}

# Externally supplied resource rooms only.
#
# Examples:
# - user:123
# - ca:12
# - cert:abc123
# - group:security-team
RESOURCE_ROOM_RE = re.compile(
    r"^(?:ca|cert|user|group):[A-Za-z0-9][A-Za-z0-9_.:-]{0,126}$"
)


@dataclass(frozen=True)
class AuthResult:
    """Authenticated socket identity."""

    user_id: Any
    username: Optional[str]
    permissions: Tuple[str, ...]
    auth_method: str  # "session"


# ---------------------------------------------------------------------------
# General helpers
# ---------------------------------------------------------------------------

def _config_int(
    key: str,
    default: int,
    minimum: int = 1,
) -> int:
    """Return a validated positive integer from Flask configuration."""
    value = current_app.config.get(key, default)

    try:
        value = int(value)
    except (TypeError, ValueError) as exc:
        raise RuntimeError(f"{key} must be an integer") from exc

    if value < minimum:
        raise RuntimeError(f"{key} must be at least {minimum}")

    return value


def _event_type_value(event_type: Union[EventType, str]) -> str:
    """Normalize EventType or a non-empty string to its event name."""
    if isinstance(event_type, EventType):
        return event_type.value

    if not isinstance(event_type, str) or not event_type.strip():
        raise ValueError("event_type must be a non-empty EventType or string")

    return event_type


def _ensure_json_serializable(value: Any) -> None:
    """
    Validate event data before emission.

    Payloads must contain only JSON-compatible primitives, lists, and dicts.
    Convert datetime, UUID, Decimal, ORM objects, and other custom types before
    calling an event emitter.
    """
    try:
        json.dumps(value, allow_nan=False)
    except (TypeError, ValueError) as exc:
        raise ValueError(
            "WebSocket event payload must be JSON serializable"
        ) from exc


# ---------------------------------------------------------------------------
# Initialization
# ---------------------------------------------------------------------------

_QUEUE_SCHEMES = ("redis", "rediss", "unix", "redis+sentinel")


def _queue_channel(url: str, key_prefix: str) -> str:
    """Pub/sub ignores the Redis database number: scope the channel like the session keys."""
    parsed = urlparse(url)
    db = (parse_qs(parsed.query).get("db") or [None])[0]
    if db is None:
        parts = [part for part in parsed.path.split("/") if part]
        if parsed.scheme in ("redis", "rediss") and parts:
            db = parts[0]
        elif parsed.scheme == "redis+sentinel" and len(parts) > 1:
            db = parts[1]
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
    # A connect timeout bounds each emit when Redis is unreachable.
    return socketio_pkg.RedisManager(
        url,
        channel=_queue_channel(url, app.config.get("SESSION_KEY_PREFIX", "ucm:session:")),
        redis_options={"socket_connect_timeout": 2},
    )


def init_websocket(app) -> SocketIO:
    """Initialize Flask-SocketIO."""
    cors_origins = app.config.get("CORS_ORIGINS")

    if not cors_origins:
        raise RuntimeError(
            "CORS_ORIGINS must be explicitly configured for WebSocket access"
        )

    if cors_origins == "*":
        raise RuntimeError(
            "CORS_ORIGINS cannot be '*' for authenticated WebSocket access"
        )

    if isinstance(cors_origins, str):
        cors_origins = [cors_origins]

    if not isinstance(cors_origins, (list, tuple)) or not all(
        isinstance(origin, str)
        and origin.startswith(("https://", "http://"))
        for origin in cors_origins
    ):
        raise RuntimeError(
            "CORS_ORIGINS must be a list of explicit http(s) origins"
        )

    message_queue = _message_queue(app)

    socketio.init_app(
        app,
        async_mode=app.config.get("SOCKETIO_ASYNC_MODE", "gevent"),
        cors_allowed_origins=list(cors_origins),
        client_manager=message_queue,
        manage_session=False,
        logger=app.config.get("SOCKETIO_LOGGER", False),
        engineio_logger=app.config.get("ENGINEIO_LOGGER", False),
        ping_timeout=int(app.config.get("SOCKETIO_PING_TIMEOUT", 60)),
        ping_interval=int(app.config.get("SOCKETIO_PING_INTERVAL", 25)),
    )

    logger.info(
        "WebSocket initialized",
        extra={
            "async_mode": app.config.get("SOCKETIO_ASYNC_MODE", "gevent"),
            "message_queue_enabled": bool(message_queue),
        },
    )

    return socketio


# ---------------------------------------------------------------------------
# Authentication and permissions
# ---------------------------------------------------------------------------

def _result_to_auth_result(
    result: Optional[Dict[str, Any]],
    auth_method: str,
) -> Optional[AuthResult]:
    """Convert AuthManager response to immutable socket authentication data."""
    if not result:
        return None

    user_id = result.get("user_id")
    if user_id is None:
        return None

    user = result.get("user")
    username = getattr(user, "username", None)

    permissions = result.get("permissions") or []
    if not isinstance(permissions, (list, tuple, set)):
        logger.warning(
            "WebSocket authentication returned invalid permissions",
            extra={"user_id": user_id},
        )
        return None

    return AuthResult(
        user_id=user_id,
        username=username,
        permissions=tuple(str(permission) for permission in permissions),
        auth_method=auth_method,
    )


def _resolve_user_from_session() -> Optional[AuthResult]:
    """
    Resolve the active authenticated Flask session.

    AuthManager.verify_session() should enforce normal session expiry,
    inactivity timeout, logout handling, user-disablement, and authorization.
    """
    if "user_id" not in session:
        return None

    try:
        from auth.unified import AuthManager

        result = AuthManager().verify_session()
        return _result_to_auth_result(result, "session")

    except Exception:
        logger.exception("WebSocket session verification failed")
        return None


def _authenticate_handshake() -> Optional[AuthResult]:
    """Authenticate the handshake from the Flask session."""
    return _resolve_user_from_session()


def _has_permission(
    permission: str,
    permissions: Iterable[str],
) -> bool:
    """Perform permission checks fail-closed."""
    try:
        from auth.unified import has_permission

        return bool(has_permission(permission, list(permissions)))

    except Exception:
        logger.exception(
            "WebSocket permission check failed",
            extra={"permission": permission},
        )
        return False


def _has_socket_permission(permissions: Iterable[str]) -> bool:
    """Return whether a user may open a certificate event socket."""
    return _has_permission(_SOCKET_MIN_PERMISSION, permissions)


def _is_privileged(permissions: Iterable[str]) -> bool:
    """
    Return whether a user may subscribe to broad resource-specific rooms.

    Uses effective permissions only. There is intentionally no role-column or
    database fallback because authorization failures must fail closed.
    """
    return (
        _has_permission("read:certificates", permissions)
        and _has_permission("read:cas", permissions)
    )


def authenticate_socket(f: Callable) -> Callable:
    """Authenticate and authorize the Socket.IO connect handshake."""

    @wraps(f)
    def decorated(*args, **kwargs):
        identity = _authenticate_handshake()

        if identity is None:
            logger.warning(
                "WebSocket connection rejected: unauthenticated",
                extra={
                    "sid": getattr(request, "sid", None),
                    "remote_addr": request.remote_addr,
                },
            )
            return False

        if not _has_socket_permission(identity.permissions):
            logger.warning(
                "WebSocket connection rejected: insufficient permission",
                extra={
                    "sid": getattr(request, "sid", None),
                    "user_id": identity.user_id,
                    "remote_addr": request.remote_addr,
                },
            )
            return False

        request.user_id = identity.user_id
        request.username = identity.username
        request.permissions = identity.permissions
        request.auth_method = identity.auth_method

        return f(*args, **kwargs)

    return decorated


def _session_revalidation_due(client: Dict[str, Any]) -> bool:
    """Return whether a session client needs authorization revalidation."""
    return (
        client["auth_method"] == "session"
        and time.monotonic() >= client["next_auth_check_at"]
    )


def _revalidate_session_client(client: Dict[str, Any]) -> bool:
    """
    Revalidate session-backed socket authorization.

    Returns False when the session has expired, the user was disabled, or
    required permissions are no longer present.
    """
    identity = _resolve_user_from_session()

    if identity is None:
        return False

    if identity.user_id != client["user_id"]:
        logger.warning(
            "WebSocket session identity changed",
            extra={"user_id": client["user_id"]},
        )
        return False

    if not _has_socket_permission(identity.permissions):
        return False

    client["username"] = identity.username or str(identity.user_id)
    client["permissions"] = identity.permissions
    client["is_privileged"] = _is_privileged(identity.permissions)
    client["next_auth_check_at"] = (
        time.monotonic() + client["session_revalidate_seconds"]
    )

    _sync_managed_rooms(client)
    return True


def _socket_auth_is_valid(sid: str, client: Dict[str, Any]) -> bool:
    """Validate cached socket authentication, revalidating the session when due."""
    if _session_revalidation_due(client):
        return _revalidate_session_client(client)

    return True


def require_socket_auth(f: Callable) -> Callable:
    """Require a currently valid authenticated socket for an event handler."""

    @wraps(f)
    def decorated(*args, **kwargs):
        sid = getattr(request, "sid", None)
        client = connected_clients.get(sid)

        if not client or not _socket_auth_is_valid(sid, client):
            logger.warning(
                "WebSocket event rejected: invalid authentication",
                extra={
                    "sid": sid,
                    "event": getattr(f, "__name__", "unknown"),
                },
            )

            connected_clients.pop(sid, None)
            disconnect()
            return False

        request.user_id = client["user_id"]
        request.username = client["username"]
        request.permissions = client["permissions"]

        return f(*args, **kwargs)

    return decorated


# ---------------------------------------------------------------------------
# Room management
# ---------------------------------------------------------------------------

def _managed_rooms_for_permissions(
    permissions: Iterable[str],
) -> Set[str]:
    """Return server-controlled rooms granted by effective permissions."""
    rooms: Set[str] = set()

    if _has_permission("read:certificates", permissions):
        rooms.add(ROOM_CERTIFICATES)

    if _has_permission("read:cas", permissions):
        rooms.add(ROOM_CAS)

    if _has_permission("read:system", permissions):
        rooms.add(ROOM_SYSTEM_ALERTS)

    if _has_permission("read:audit", permissions):
        rooms.add(ROOM_AUDIT)

    return rooms


def _mandatory_rooms(client: Dict[str, Any]) -> Set[str]:
    """Return rooms the connected client is not allowed to leave."""
    return {
        f"user:{client['user_id']}",
        *_managed_rooms_for_permissions(client["permissions"]),
    }


def _sync_managed_rooms(client: Dict[str, Any]) -> None:
    """
    Synchronize server-managed rooms after connect or session revalidation.

    This function runs inside a Socket.IO event context where join_room and
    leave_room are valid.
    """
    current_rooms: Set[str] = client["rooms"]
    expected_rooms = _mandatory_rooms(client)

    current_managed_rooms = {
        room
        for room in current_rooms
        if room.startswith("scope:") or room.startswith("user:")
    }

    for room in current_managed_rooms - expected_rooms:
        leave_room(room)
        current_rooms.discard(room)

    for room in expected_rooms - current_rooms:
        join_room(room)
        current_rooms.add(room)


def _is_valid_resource_room(room: Any) -> bool:
    """Validate a user-supplied resource-specific room name."""
    return (
        isinstance(room, str)
        and len(room) <= MAX_ROOM_NAME_LENGTH
        and bool(RESOURCE_ROOM_RE.fullmatch(room))
    )


def _subscription_rate_allowed(client: Dict[str, Any]) -> bool:
    """Apply a sliding-window rate limit to subscribe/unsubscribe operations."""
    now = time.monotonic()
    history: Deque[float] = client["subscription_history"]

    while history and history[0] <= now - SUBSCRIPTION_RATE_WINDOW_SECONDS:
        history.popleft()

    if len(history) >= MAX_SUBSCRIPTION_OPERATIONS_PER_WINDOW:
        return False

    history.append(now)
    return True


def _can_subscribe_to_room(
    client: Dict[str, Any],
    room: str,
) -> bool:
    """
    Authorize a resource-specific subscription.

    By default:
    - Users can subscribe to their own `user:<id>` room.
    - Broad CA/certificate/group room subscription requires privileged access.

    If your application has tenant-specific or ownership-specific access rules,
    replace this with a resource authorization lookup.
    """
    if room == f"user:{client['user_id']}":
        return True

    return bool(client["is_privileged"])


# ---------------------------------------------------------------------------
# Socket event handlers
# ---------------------------------------------------------------------------

@socketio.on("connect")
@authenticate_socket
def handle_connect(auth: Optional[Dict[str, Any]] = None):
    """Handle a successfully authenticated Socket.IO connection."""
    sid = request.sid
    user_id = request.user_id
    permissions = tuple(request.permissions)

    session_revalidate_seconds = _config_int(
        "SOCKETIO_SESSION_REVALIDATE_SECONDS",
        DEFAULT_SESSION_REVALIDATE_SECONDS,
    )

    client = {
        "user_id": user_id,
        "username": request.username or str(user_id),
        "permissions": permissions,
        "auth_method": request.auth_method,
        "is_privileged": _is_privileged(permissions),
        "connected_at": utc_now().isoformat(),
        "rooms": set(),
        "subscription_history": deque(),
        "session_revalidate_seconds": session_revalidate_seconds,
        "next_auth_check_at": (
            time.monotonic() + session_revalidate_seconds
        ),
    }

    connected_clients[sid] = client
    _sync_managed_rooms(client)

    logger.info(
        "WebSocket connected",
        extra={
            "sid": sid,
            "user_id": user_id,
            "auth_method": request.auth_method,
        },
    )

    emit(
        "connected",
        {
            "status": "ok",
            "user_id": user_id,
            "timestamp": utc_now().isoformat(),
        },
    )


@socketio.on("disconnect")
def handle_disconnect():
    """Remove local metadata when a client disconnects."""
    sid = request.sid
    client = connected_clients.pop(sid, None)

    logger.info(
        "WebSocket disconnected",
        extra={
            "sid": sid,
            "user_id": client.get("user_id") if client else None,
        },
    )


@socketio.on("subscribe")
@require_socket_auth
def handle_subscribe(data: Any):
    """Subscribe to authorized resource-specific rooms."""
    sid = request.sid
    client = connected_clients[sid]

    if not _subscription_rate_allowed(client):
        emit(
            "subscription_error",
            {
                "error": "rate_limited",
                "message": "Too many subscription operations",
            },
        )
        return

    if not isinstance(data, dict):
        emit("subscribed", {"rooms": []})
        return

    rooms = data.get("rooms")

    if not isinstance(rooms, list):
        emit("subscribed", {"rooms": []})
        return

    if len(rooms) > MAX_ROOMS_PER_REQUEST:
        emit(
            "subscription_error",
            {
                "error": "too_many_rooms",
                "message": f"Maximum {MAX_ROOMS_PER_REQUEST} rooms per request",
            },
        )
        return

    joined = []
    current_rooms: Set[str] = client["rooms"]

    for room in rooms:
        if not _is_valid_resource_room(room):
            continue

        if room in current_rooms:
            continue

        if len(current_rooms) >= MAX_ROOMS_PER_SOCKET:
            break

        if not _can_subscribe_to_room(client, room):
            logger.warning(
                "WebSocket subscription denied",
                extra={
                    "sid": sid,
                    "user_id": client["user_id"],
                    "room": room,
                },
            )
            continue

        join_room(room)
        current_rooms.add(room)
        joined.append(room)

    emit("subscribed", {"rooms": joined})


@socketio.on("unsubscribe")
@require_socket_auth
def handle_unsubscribe(data: Any):
    """Unsubscribe from non-mandatory resource-specific rooms."""
    sid = request.sid
    client = connected_clients[sid]

    if not _subscription_rate_allowed(client):
        emit(
            "subscription_error",
            {
                "error": "rate_limited",
                "message": "Too many subscription operations",
            },
        )
        return

    if not isinstance(data, dict):
        emit("unsubscribed", {"rooms": []})
        return

    rooms = data.get("rooms")

    if not isinstance(rooms, list) or len(rooms) > MAX_ROOMS_PER_REQUEST:
        emit("unsubscribed", {"rooms": []})
        return

    left = []
    mandatory_rooms = _mandatory_rooms(client)

    for room in rooms:
        if not _is_valid_resource_room(room):
            continue

        if room in mandatory_rooms:
            continue

        if room not in client["rooms"]:
            continue

        leave_room(room)
        client["rooms"].discard(room)
        left.append(room)

    emit("unsubscribed", {"rooms": left})


@socketio.on("ping")
@require_socket_auth
def handle_ping():
    """
    Application-level ping.

    Clients should emit this periodically, for example every 30 seconds, so
    session-backed connections are revalidated promptly.
    """
    emit("pong", {"timestamp": utc_now().isoformat()})


# ---------------------------------------------------------------------------
# Event emitters
# ---------------------------------------------------------------------------

def emit_event(
    event_type: Union[EventType, str],
    data: Dict[str, Any],
    room: str,
    include_self: bool = True,
) -> None:
    """
    Emit one event to one explicit room.

    There is intentionally no default/global room. Every event must declare its
    intended authorization scope.
    """
    if not isinstance(room, str) or not room:
        raise ValueError("A non-empty target room is required")

    if not isinstance(data, dict):
        raise ValueError("WebSocket event data must be a dictionary")

    _ensure_json_serializable(data)

    payload = {
        "type": _event_type_value(event_type),
        "data": data,
        "timestamp": utc_now().isoformat(),
    }

    try:
        socketio.emit(
            "event",
            payload,
            room=room,
            include_self=include_self,
        )

    except Exception:
        logger.exception(
            "Failed to emit WebSocket event",
            extra={
                "event_type": payload["type"],
                "room": room,
            },
        )


def emit_to_user(
    user_id: Union[int, str],
    event_type: Union[EventType, str],
    data: Dict[str, Any],
) -> None:
    """Emit an event to a particular user's mandatory server-managed room."""
    emit_event(
        event_type,
        data,
        room=f"user:{user_id}",
    )


def emit_certificate_event(
    event_type: Union[EventType, str],
    cert_data: Dict[str, Any],
) -> None:
    """
    Emit a certificate event once to certificate-authorized clients.

    Do not additionally send this event to `ca:<id>` within this function.
    Clients that belong to both rooms would otherwise receive duplicate events.

    For tenant- or owner-specific certificate access, replace ROOM_CERTIFICATES
    with a dedicated tenant/resource authorization room.
    """
    emit_event(
        event_type,
        cert_data,
        room=ROOM_CERTIFICATES,
    )


def emit_ca_event(
    event_type: Union[EventType, str],
    ca_data: Dict[str, Any],
) -> None:
    """Emit a CA event only to users with CA-read permission."""
    emit_event(
        event_type,
        ca_data,
        room=ROOM_CAS,
    )


def emit_system_alert(
    alert_type: str,
    message: str,
    severity: str = "info",
    details: Optional[Dict[str, Any]] = None,
) -> None:
    """Emit a system alert only to system-authorized clients."""
    allowed_severities = {"info", "warning", "error", "critical"}

    if severity not in allowed_severities:
        raise ValueError(
            f"Invalid severity '{severity}'; "
            f"expected one of {sorted(allowed_severities)}"
        )

    if not isinstance(alert_type, str) or not alert_type.strip():
        raise ValueError("alert_type must be a non-empty string")

    if not isinstance(message, str) or not message.strip():
        raise ValueError("message must be a non-empty string")

    emit_event(
        EventType.SYSTEM_ALERT,
        {
            "alert_type": alert_type,
            "message": message,
            "severity": severity,
            "details": details or {},
        },
        room=ROOM_SYSTEM_ALERTS,
    )


def emit_audit_critical(
    action: str,
    user: str,
    resource: str,
    details: Optional[Dict[str, Any]] = None,
) -> None:
    """
    Emit a critical audit event to audit-authorized clients only.

    Never include credentials, private keys, raw request bodies, session IDs,
    API-key values, or exception stack traces in `details`.
    """
    for field_name, value in {
        "action": action,
        "user": user,
        "resource": resource,
    }.items():
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"{field_name} must be a non-empty string")

    emit_event(
        EventType.AUDIT_CRITICAL,
        {
            "action": action,
            "user": user,
            "resource": resource,
            "details": details or {},
        },
        room=ROOM_AUDIT,
    )


def broadcast_to_scope(
    room: str,
    event_type: Union[EventType, str],
    data: Dict[str, Any],
) -> None:
    """
    Broadcast to an approved server-managed authorization room.

    This replaces the old unrestricted `broadcast_to_all` behavior.
    """
    if room not in SERVER_MANAGED_ROOMS:
        raise ValueError(
            "broadcast_to_scope only accepts server-managed scope rooms"
        )

    emit_event(event_type, data, room=room)


# ---------------------------------------------------------------------------
# Operational helpers
# ---------------------------------------------------------------------------

def get_connected_clients_count() -> int:
    """Return the connected client count of this worker."""
    return len(connected_clients)


def get_connected_clients_info() -> Dict[str, Any]:
    """
    Return safe operational connection metadata.

    Do not expose this output to untrusted users. It intentionally omits user
    IDs, session IDs, usernames, permissions, and subscribed resource rooms.
    """
    local_clients = list(connected_clients.values())

    return {
        "count": get_connected_clients_count(),
        "local_worker_count": len(local_clients),
        "clients": [
            {
                "connected_at": client["connected_at"],
                "auth_method": client["auth_method"],
                "room_count": len(client["rooms"]),
                "privileged": bool(client["is_privileged"]),
            }
            for client in local_clients
        ],
    }
