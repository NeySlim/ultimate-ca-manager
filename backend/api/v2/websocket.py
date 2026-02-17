"""
WebSocket API endpoints for management and monitoring.
"""

from flask import Blueprint, request, g
from auth.unified import require_auth
from utils.response import success_response, error_response

from websocket import (
    get_connected_clients_info,
    get_connected_clients_count,
    emit_system_alert,
    EventType
)

websocket_bp = Blueprint('websocket', __name__, url_prefix='/api/v2/websocket')


@websocket_bp.route('/status', methods=['GET'])
@require_auth()
def get_status():
    """Get WebSocket server status."""
    clients_info = get_connected_clients_info()
    
    return success_response(data={
        'websocket': {
            'enabled': True,
            'connected_clients': clients_info['count'],
            'endpoint': '/socket.io'
        }
    })


@websocket_bp.route('/clients', methods=['GET'])
@require_auth()
def get_clients():
    """Get list of connected WebSocket clients (admin only)."""
    clients_info = get_connected_clients_info()
    
    return success_response(data=clients_info)


@websocket_bp.route('/broadcast', methods=['POST'])
@require_auth()
def broadcast_message():
    """Broadcast a system alert to all connected clients (admin only)."""
    data = request.get_json()
    message = data.get('message', '')
    alert_type = data.get('alert_type', 'system')
    severity = data.get('severity', 'info')
    
    if not message:
        return error_response('Message required', 400)
    
    emit_system_alert(alert_type, message, severity)
    
    user = g.current_user.username if hasattr(g, 'current_user') else 'unknown'
    
    return success_response(data={
        'message': 'Broadcast sent',
        'details': {
            'alert_type': alert_type,
            'severity': severity,
            'sent_by': user
        }
    })


@websocket_bp.route('/events', methods=['GET'])
def get_event_types():
    """
    Get list of all available WebSocket event types.
    ---
    tags:
      - WebSocket
    responses:
      200:
        description: List of event types
    """
    events = [
        {'name': e.name, 'value': e.value}
        for e in EventType
    ]
    
    return success_response(data={'events': events})
