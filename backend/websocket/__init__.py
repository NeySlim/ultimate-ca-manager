"""
WebSocket module for UCM real-time events.
Uses Flask-SocketIO for bidirectional communication.
"""

from .events import (
    socketio,
    init_websocket,
    emit_event,
    emit_to_user,
    emit_certificate_event,
    emit_ca_event,
    emit_system_alert,
    emit_audit_critical,
    broadcast_to_scope,
    get_connected_clients_count,
    get_connected_clients_info,
)
from .event_types import EventType
from .emitters import (
    on_certificate_issued,
    on_certificate_revoked,
    on_certificate_renewed,
    on_certificate_deleted,
    on_ca_created,
    on_ca_updated,
    on_ca_deleted,
    on_ca_revoked,
    on_crl_regenerated,
    on_user_login,
    on_user_logout,
    on_user_created,
    on_user_deleted,
    on_group_created,
    on_group_deleted,
    on_system_alert,
    on_audit_critical,
)

__all__ = [
    'socketio',
    'init_websocket',
    'emit_event',
    'emit_to_user',
    'emit_certificate_event',
    'emit_ca_event',
    'emit_system_alert',
    'emit_audit_critical',
    'broadcast_to_scope',
    'EventType',
    # Emitter functions
    'on_certificate_issued',
    'on_certificate_revoked',
    'on_certificate_renewed',
    'on_certificate_deleted',
    'on_ca_created',
    'on_ca_updated',
    'on_ca_deleted',
    'on_ca_revoked',
    'on_crl_regenerated',
    'on_user_login',
    'on_user_logout',
    'on_user_created',
    'on_user_deleted',
    'on_group_created',
    'on_group_deleted',
    'on_system_alert',
    'on_audit_critical',
    # Management functions
    'get_connected_clients_count',
    'get_connected_clients_info',
]
