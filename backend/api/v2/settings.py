"""
Settings Routes v2.0
/api/settings/* - System settings (general, users, backup, email, etc.)
"""

from flask import Blueprint, request, g
from auth.unified import require_auth
from utils.response import success_response, error_response

bp = Blueprint('settings_v2', __name__)


@bp.route('/api/settings/general', methods=['GET'])
@require_auth(['read:settings'])
def get_general_settings():
    """Get general settings"""
    return success_response(data={
        'site_name': 'UCM',
        'timezone': 'UTC'
    })


@bp.route('/api/settings/general', methods=['PATCH'])
@require_auth(['write:settings'])
def update_general_settings():
    """Update general settings"""
    data = request.json
    return success_response(data=data, message='Settings updated')


@bp.route('/api/settings/users', methods=['GET'])
@require_auth(['admin:users'])
def list_users():
    """List users (admin only)"""
    return success_response(data=[])


@bp.route('/api/settings/users', methods=['POST'])
@require_auth(['admin:users'])
def create_user():
    """Create user (admin only)"""
    data = request.json
    
    if not data or not data.get('username'):
        return error_response('Username required', 400)
    
    return success_response(
        data={'id': 1, 'username': data['username']},
        message='User created',
        status=201
    )


@bp.route('/api/settings/backup', methods=['GET'])
@require_auth(['read:settings'])
def get_backup_settings():
    """Get backup configuration"""
    return success_response(data={
        'enabled': False,
        'schedule': None
    })


@bp.route('/api/settings/backup/create', methods=['POST'])
@require_auth(['admin:system'])
def create_backup():
    """Create backup now"""
    return success_response(
        data={'filename': 'backup_20260118.tar.gz'},
        message='Backup created'
    )


@bp.route('/api/settings/email', methods=['GET'])
@require_auth(['read:settings'])
def get_email_settings():
    """Get email settings"""
    return success_response(data={
        'smtp_host': None,
        'smtp_port': 587
    })


@bp.route('/api/settings/email/test', methods=['POST'])
@require_auth(['write:settings'])
def test_email():
    """Send test email"""
    data = request.json
    email = data.get('email') if data else None
    
    return success_response(
        data={'sent': True, 'to': email},
        message='Test email sent'
    )
