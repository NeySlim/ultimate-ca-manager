"""
WebSocket API endpoints for management and monitoring.
"""

from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity

from websocket import (
    get_connected_clients_info,
    get_connected_clients_count,
    emit_system_alert,
    EventType
)

websocket_bp = Blueprint('websocket', __name__, url_prefix='/api/v2/websocket')


@websocket_bp.route('/status', methods=['GET'])
@jwt_required()
def get_status():
    """
    Get WebSocket server status.
    ---
    tags:
      - WebSocket
    security:
      - Bearer: []
    responses:
      200:
        description: WebSocket server status
    """
    clients_info = get_connected_clients_info()
    
    return jsonify({
        'success': True,
        'websocket': {
            'enabled': True,
            'connected_clients': clients_info['count'],
            'endpoint': '/socket.io'
        }
    })


@websocket_bp.route('/clients', methods=['GET'])
@jwt_required()
def get_clients():
    """
    Get list of connected WebSocket clients (admin only).
    ---
    tags:
      - WebSocket
    security:
      - Bearer: []
    responses:
      200:
        description: List of connected clients
    """
    clients_info = get_connected_clients_info()
    
    return jsonify({
        'success': True,
        'data': clients_info
    })


@websocket_bp.route('/broadcast', methods=['POST'])
@jwt_required()
def broadcast_message():
    """
    Broadcast a system alert to all connected clients (admin only).
    ---
    tags:
      - WebSocket
    security:
      - Bearer: []
    parameters:
      - in: body
        name: body
        schema:
          type: object
          required:
            - message
          properties:
            message:
              type: string
            alert_type:
              type: string
              default: info
            severity:
              type: string
              enum: [info, warning, error, critical]
              default: info
    responses:
      200:
        description: Message broadcast successfully
    """
    data = request.get_json()
    message = data.get('message', '')
    alert_type = data.get('alert_type', 'system')
    severity = data.get('severity', 'info')
    
    if not message:
        return jsonify({'success': False, 'error': 'Message required'}), 400
    
    emit_system_alert(alert_type, message, severity)
    
    user = get_jwt_identity()
    
    return jsonify({
        'success': True,
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
    
    return jsonify({
        'success': True,
        'events': events
    })
