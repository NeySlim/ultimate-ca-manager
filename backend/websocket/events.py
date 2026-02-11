"""
WebSocket events handler and emitter.
Provides real-time event broadcasting to connected clients.
"""

import logging
from datetime import datetime
from typing import Any, Dict, Optional
from functools import wraps

from flask import request, current_app
from flask_socketio import SocketIO, emit, join_room, leave_room, disconnect

from .event_types import EventType

logger = logging.getLogger(__name__)

# SocketIO instance - initialized in init_websocket()
socketio = SocketIO()

# Connected clients tracking
connected_clients: Dict[str, Dict[str, Any]] = {}


def init_websocket(app):
    """Initialize WebSocket with Flask app."""
    socketio.init_app(
        app,
        cors_allowed_origins="*",
        async_mode='gevent',
        logger=True,
        engineio_logger=False,
        ping_timeout=60,
        ping_interval=25
    )
    
    logger.info("WebSocket initialized with gevent async mode")
    return socketio


def authenticate_socket(f):
    """Decorator to authenticate WebSocket connections via session cookie."""
    @wraps(f)
    def decorated(*args, **kwargs):
        try:
            from flask import session
            
            # Check if user is authenticated via session
            user_id = session.get('user_id')
            username = session.get('username')
            
            # Debug log
            logger.debug(f"WebSocket auth: user_id={user_id}, username={username}, session keys={list(session.keys())}")
            
            if not user_id and not username:
                # Allow as anonymous (session not shared with websocket)
                logger.info("WebSocket connection as anonymous (session not shared)")
                user_id = 'anonymous'
                username = 'anonymous'
            
            request.user_id = user_id or username
            request.username = username or str(user_id)
            
            return f(*args, **kwargs)
        except Exception as e:
            logger.warning(f"WebSocket auth failed: {e}")
            # Don't disconnect, allow as anonymous
            request.user_id = 'anonymous'
            request.username = 'anonymous'
            return f(*args, **kwargs)
    
    return decorated


# ================== Socket Event Handlers ==================

@socketio.on('connect')
@authenticate_socket
def handle_connect(auth=None):
    """Handle new WebSocket connection."""
    user_id = getattr(request, 'user_id', 'anonymous')
    sid = request.sid
    
    connected_clients[sid] = {
        'user_id': user_id,
        'connected_at': datetime.utcnow().isoformat(),
        'rooms': ['global']
    }
    
    # Join global room for broadcasts
    join_room('global')
    
    # Join user-specific room
    join_room(f'user:{user_id}')
    
    logger.info(f"WebSocket connected: user={user_id}, sid={sid}")
    
    # Send connection confirmation
    emit('connected', {
        'status': 'ok',
        'user_id': user_id,
        'timestamp': datetime.utcnow().isoformat()
    })


@socketio.on('disconnect')
def handle_disconnect():
    """Handle WebSocket disconnection."""
    sid = request.sid
    client = connected_clients.pop(sid, None)
    
    if client:
        logger.info(f"WebSocket disconnected: user={client.get('user_id')}, sid={sid}")
    else:
        logger.info(f"WebSocket disconnected: sid={sid}")


@socketio.on('subscribe')
@authenticate_socket
def handle_subscribe(data):
    """Subscribe to specific event rooms."""
    rooms = data.get('rooms', [])
    sid = request.sid
    
    for room in rooms:
        # Validate room name (prevent injection)
        if room.startswith(('ca:', 'cert:', 'user:', 'group:')):
            join_room(room)
            if sid in connected_clients:
                connected_clients[sid]['rooms'].append(room)
            logger.debug(f"Client {sid} subscribed to room: {room}")
    
    emit('subscribed', {'rooms': rooms})


@socketio.on('unsubscribe')
def handle_unsubscribe(data):
    """Unsubscribe from specific event rooms."""
    rooms = data.get('rooms', [])
    sid = request.sid
    
    for room in rooms:
        leave_room(room)
        if sid in connected_clients and room in connected_clients[sid]['rooms']:
            connected_clients[sid]['rooms'].remove(room)
    
    emit('unsubscribed', {'rooms': rooms})


@socketio.on('ping')
def handle_ping():
    """Handle ping for connection keep-alive."""
    emit('pong', {'timestamp': datetime.utcnow().isoformat()})


# ================== Event Emitter Functions ==================

def emit_event(
    event_type: EventType,
    data: Dict[str, Any],
    room: Optional[str] = None,
    broadcast: bool = True,
    include_self: bool = True
):
    """
    Emit a WebSocket event to connected clients.
    
    Args:
        event_type: The type of event from EventType enum
        data: Event payload data
        room: Specific room to emit to (default: global)
        broadcast: Whether to broadcast to all clients
        include_self: Whether to include the sender
    """
    payload = {
        'type': event_type.value if isinstance(event_type, EventType) else event_type,
        'data': data,
        'timestamp': datetime.utcnow().isoformat()
    }
    
    target_room = room or 'global'
    
    try:
        socketio.emit(
            'event',
            payload,
            room=target_room,
            include_self=include_self
        )
        logger.debug(f"Emitted {event_type} to room {target_room}")
    except Exception as e:
        logger.error(f"Failed to emit WebSocket event: {e}")


def emit_to_user(user_id: str, event_type: EventType, data: Dict[str, Any]):
    """Emit event to a specific user."""
    emit_event(event_type, data, room=f'user:{user_id}')


def emit_certificate_event(event_type: EventType, cert_data: Dict[str, Any]):
    """Emit certificate-related event."""
    emit_event(event_type, cert_data, room='global')
    
    # Also emit to CA-specific room if ca_id present
    if 'ca_id' in cert_data:
        emit_event(event_type, cert_data, room=f'ca:{cert_data["ca_id"]}')


def emit_ca_event(event_type: EventType, ca_data: Dict[str, Any]):
    """Emit CA-related event."""
    emit_event(event_type, ca_data, room='global')


def emit_system_alert(alert_type: str, message: str, severity: str = 'info', details: Optional[Dict] = None):
    """Emit system alert to all connected clients."""
    emit_event(
        EventType.SYSTEM_ALERT,
        {
            'alert_type': alert_type,
            'message': message,
            'severity': severity,  # info, warning, error, critical
            'details': details or {}
        },
        room='global'
    )


def emit_audit_critical(action: str, user: str, resource: str, details: Optional[Dict] = None):
    """Emit critical audit event."""
    emit_event(
        EventType.AUDIT_CRITICAL,
        {
            'action': action,
            'user': user,
            'resource': resource,
            'details': details or {}
        },
        room='global'
    )


# ================== Stats & Management ==================

def get_connected_clients_count() -> int:
    """Get count of connected WebSocket clients."""
    return len(connected_clients)


def get_connected_clients_info() -> Dict[str, Any]:
    """Get information about connected clients."""
    return {
        'count': len(connected_clients),
        'clients': [
            {
                'sid': sid,
                'user_id': info['user_id'],
                'connected_at': info['connected_at'],
                'rooms': info['rooms']
            }
            for sid, info in connected_clients.items()
        ]
    }


def broadcast_to_all(event_type: EventType, data: Dict[str, Any]):
    """Broadcast event to all connected clients."""
    emit_event(event_type, data, room='global', broadcast=True)
