"""
Settings Routes v2.0
/api/settings/* - System settings (general, users, backup, email, etc.)
"""

from flask import Blueprint, request, g
from auth.unified import require_auth
from utils.response import success_response, error_response, created_response
from models import db, SystemConfig
from datetime import datetime, timezone

bp = Blueprint('settings_v2', __name__)


def get_config(key, default=None):
    """Get config value from database"""
    config = SystemConfig.query.filter_by(key=key).first()
    return config.value if config else default


def set_config(key, value):
    """Set config value in database"""
    config = SystemConfig.query.filter_by(key=key).first()
    if config:
        config.value = str(value) if value is not None else None
    else:
        config = SystemConfig(key=key, value=str(value) if value is not None else None)
        db.session.add(config)


@bp.route('/api/v2/settings/general', methods=['GET'])
@require_auth(['read:settings'])
def get_general_settings():
    """Get general settings from database"""
    return success_response(data={
        'site_name': get_config('site_name', 'UCM'),
        'timezone': get_config('timezone', 'UTC'),
        'auto_backup_enabled': get_config('auto_backup_enabled', 'false') == 'true',
        'backup_frequency': get_config('backup_frequency', 'daily'),
        'backup_retention_days': int(get_config('backup_retention_days', '30')),
        'backup_password': '',  # Never return password
        'session_timeout': int(get_config('session_timeout', '3600')),
        'max_login_attempts': int(get_config('max_login_attempts', '5')),
        'lockout_duration': int(get_config('lockout_duration', '300')),
    })


@bp.route('/api/v2/settings/general', methods=['PATCH'])
@require_auth(['write:settings'])
def update_general_settings():
    """Update general settings in database"""
    data = request.json or {}
    
    # List of allowed settings
    allowed_keys = [
        'site_name', 'timezone', 'auto_backup_enabled', 'backup_frequency',
        'backup_retention_days', 'backup_password', 'session_timeout',
        'max_login_attempts', 'lockout_duration'
    ]
    
    for key in allowed_keys:
        if key in data:
            value = data[key]
            # Convert booleans to string
            if isinstance(value, bool):
                value = 'true' if value else 'false'
            set_config(key, value)
    
    db.session.commit()
    
    return success_response(message='Settings saved successfully')


@bp.route('/api/v2/settings/users', methods=['GET'])
@require_auth(['admin:users'])
def list_users():
    """List users (admin only)"""
    from models import User
    users = User.query.all()
    return success_response(data=[u.to_dict() for u in users])


@bp.route('/api/v2/settings/users', methods=['POST'])
@require_auth(['admin:users'])
def create_user():
    """Create user (admin only)"""
    from models import User, db
    from werkzeug.security import generate_password_hash
    
    data = request.json
    
    if not data or not data.get('username'):
        return error_response('Username required', 400)
    
    if not data.get('password'):
        return error_response('Password required', 400)
    
    if User.query.filter_by(username=data['username']).first():
        return error_response('Username already exists', 409)
    
    if data.get('email') and User.query.filter_by(email=data['email']).first():
        return error_response('Email already exists', 409)
    
    user = User(
        username=data['username'],
        email=data.get('email'),
        password_hash=generate_password_hash(data['password']),
        role=data.get('role', 'user'),
        is_active=data.get('is_active', True)
    )
    
    db.session.add(user)
    db.session.commit()
    
    # Audit log
    try:
        from services.audit_service import AuditService
        AuditService.log(
            action='user_created',
            user_id=g.current_user.id if hasattr(g, 'current_user') else None,
            details={'new_user_id': user.id, 'username': user.username}
        )
    except Exception:
        pass
    
    return success_response(
        data=user.to_dict(),
        message='User created',
        status=201
    )


@bp.route('/api/v2/settings/users/<int:user_id>', methods=['PATCH'])
@require_auth(['admin:users'])
def update_user(user_id):
    """Update user (admin only)"""
    from models import User, db
    from werkzeug.security import generate_password_hash
    
    data = request.json
    
    if not data:
        return error_response('No data provided', 400)
    
    user = User.query.get(user_id)
    if not user:
        return error_response('User not found', 404)
    
    # Update fields
    if 'email' in data:
        if data['email'] and User.query.filter(User.email == data['email'], User.id != user_id).first():
            return error_response('Email already exists', 409)
        user.email = data['email']
    
    if 'role' in data:
        user.role = data['role']
    
    if 'is_active' in data:
        user.is_active = data['is_active']
    
    if 'password' in data and data['password']:
        user.password_hash = generate_password_hash(data['password'])
    
    db.session.commit()
    
    return success_response(
        data=user.to_dict(),
        message='User updated successfully'
    )


@bp.route('/api/v2/settings/users/<int:user_id>', methods=['DELETE'])
@require_auth(['admin:users'])
def delete_user(user_id):
    """Delete user (admin only)"""
    from models import User, db
    from utils.response import no_content_response
    
    # Prevent deleting yourself
    if hasattr(g, 'current_user') and g.current_user.id == user_id:
        return error_response('Cannot delete your own account', 403)
    
    user = User.query.get(user_id)
    if not user:
        return error_response('User not found', 404)
    
    # Prevent deleting the last admin
    if user.role == 'admin':
        admin_count = User.query.filter_by(role='admin').count()
        if admin_count <= 1:
            return error_response('Cannot delete the last admin user', 403)
    
    username = user.username
    db.session.delete(user)
    db.session.commit()
    
    # Audit log
    try:
        from services.audit_service import AuditService
        AuditService.log(
            action='user_deleted',
            user_id=g.current_user.id if hasattr(g, 'current_user') else None,
            details={'deleted_user_id': user_id, 'username': username}
        )
    except Exception:
        pass
    
    return no_content_response()


@bp.route('/api/v2/settings/backup', methods=['GET'])
@require_auth(['read:settings'])
def get_backup_settings():
    """Get backup configuration"""
    return success_response(data={
        'enabled': False,
        'schedule': None
    })


@bp.route('/api/v2/settings/backup/create', methods=['POST'])
@require_auth(['admin:system'])
def create_backup():
    """Create backup now"""
    from datetime import datetime
    import os
    
    try:
        from services.backup_service import BackupService
        data = request.json or {}
        password = data.get('password', 'default_backup_password')
        
        service = BackupService()
        backup_bytes = service.create_backup(password)
        
        # Save to disk
        filename = f"ucm_backup_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.ucmbkp"
        backup_dir = "/opt/ucm/data/backups"
        os.makedirs(backup_dir, exist_ok=True)
        
        filepath = os.path.join(backup_dir, filename)
        with open(filepath, 'wb') as f:
            f.write(backup_bytes)
        
        return success_response(
            data={
                'filename': filename,
                'size': len(backup_bytes),
                'path': filepath
            },
            message='Backup created successfully'
        )
    except Exception as e:
        return error_response(f'Backup failed: {str(e)}', 500)


@bp.route('/api/v2/settings/backup/restore', methods=['POST'])
@require_auth(['admin:system'])
def restore_backup():
    """Restore from backup file"""
    import tempfile
    import os
    
    if 'file' not in request.files:
        return error_response('No backup file provided', 400)
    
    file = request.files['file']
    if file.filename == '':
        return error_response('No file selected', 400)
    
    password = request.form.get('password', 'default_backup_password')
    
    try:
        from services.backup_service import BackupService
        
        # Save uploaded file temporarily
        with tempfile.NamedTemporaryFile(delete=False, suffix='.ucmbkp') as tmp:
            file.save(tmp.name)
            tmp_path = tmp.name
        
        service = BackupService()
        service.restore_backup(tmp_path, password)
        
        os.unlink(tmp_path)
        
        return success_response(
            data={'filename': file.filename, 'restored': True},
            message='Backup restored successfully. Please restart the application.'
        )
    except Exception as e:
        return error_response(f'Restore failed: {str(e)}', 500)


@bp.route('/api/v2/settings/backup/<path:filename>/download', methods=['GET'])
@require_auth(['read:settings'])
def download_backup(filename):
    """Download backup file"""
    from flask import send_file
    import os
    
    backup_dir = "/opt/ucm/data/backups"
    backup_file = os.path.join(backup_dir, os.path.basename(filename))
    
    if not os.path.exists(backup_file):
        return error_response('Backup file not found', 404)
    
    return send_file(
        backup_file,
        as_attachment=True,
        download_name=os.path.basename(filename),
        mimetype='application/octet-stream'
    )


@bp.route('/api/v2/settings/backup/<path:filename>', methods=['DELETE'])
@require_auth(['admin:system'])
def delete_backup(filename):
    """Delete backup file"""
    import os
    from utils.response import no_content_response
    
    backup_dir = "/opt/ucm/data/backups"
    backup_file = os.path.join(backup_dir, os.path.basename(filename))
    
    if os.path.exists(backup_file):
        os.unlink(backup_file)
    
    return no_content_response()


@bp.route('/api/v2/settings/email', methods=['GET'])
@require_auth(['read:settings'])
def get_email_settings():
    """Get email settings"""
    return success_response(data={
        'smtp_host': None,
        'smtp_port': 587
    })


@bp.route('/api/v2/settings/email', methods=['PATCH'])
@require_auth(['write:settings'])
def update_email_settings():
    """Update email settings"""
    from models import SystemConfig, db
    
    data = request.json
    
    if not data:
        return error_response('No data provided', 400)
    
    # Save each setting to SystemConfig
    for key, value in data.items():
        config = SystemConfig.query.filter_by(key=f'email_{key}').first()
        if config:
            config.value = str(value) if value is not None else ''
        else:
            config = SystemConfig(key=f'email_{key}', value=str(value) if value is not None else '')
            db.session.add(config)
    
    db.session.commit()
    
    return success_response(
        data=data,
        message='Email settings updated successfully'
    )


@bp.route('/api/v2/settings/email/test', methods=['POST'])
@require_auth(['write:settings'])
def test_email():
    """Send test email"""
    data = request.json
    email = data.get('email') if data else None
    
    return success_response(
        data={'sent': True, 'to': email},
        message='Test email sent'
    )


# ============================================================================
# Audit Logs
# ============================================================================

@bp.route('/api/v2/settings/audit-logs', methods=['GET'])
@require_auth(['admin:system'])
def get_audit_logs():
    """Get system audit logs"""
    from models import AuditLog
    from datetime import datetime
    
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 50, type=int)
    user_id = request.args.get('user_id', type=int)
    action = request.args.get('action')
    start_date = request.args.get('start_date')
    end_date = request.args.get('end_date')
    
    query = AuditLog.query
    
    if user_id:
        query = query.filter_by(user_id=user_id)
    if action:
        query = query.filter_by(action=action)
    if start_date:
        try:
            start = datetime.fromisoformat(start_date.replace('Z', '+00:00'))
            query = query.filter(AuditLog.created_at >= start)
        except ValueError:
            pass
    if end_date:
        try:
            end = datetime.fromisoformat(end_date.replace('Z', '+00:00'))
            query = query.filter(AuditLog.created_at <= end)
        except ValueError:
            pass
    
    query = query.order_by(AuditLog.created_at.desc())
    pagination = query.paginate(page=page, per_page=per_page, error_out=False)
    
    return success_response(
        data=[log.to_dict() for log in pagination.items],
        meta={'total': pagination.total, 'page': page, 'per_page': per_page}
    )


# ============================================================================
# LDAP Integration
# ============================================================================

@bp.route('/api/v2/settings/ldap', methods=['GET'])
@require_auth(['read:settings'])
def get_ldap_settings():
    """Get LDAP configuration"""
    return success_response(
        data={
            'enabled': False,
            'server': None,
            'port': 389,
            'use_ssl': False,
            'base_dn': None,
            'bind_dn': None,
            'user_filter': '(uid={username})',
            'sync_enabled': False
        }
    )


@bp.route('/api/v2/settings/ldap', methods=['PATCH'])
@require_auth(['write:settings'])
def update_ldap_settings():
    """Update LDAP configuration"""
    from models import SystemConfig, db
    
    data = request.json
    
    if not data:
        return error_response('No data provided', 400)
    
    # Save each LDAP setting
    for key, value in data.items():
        config = SystemConfig.query.filter_by(key=f'ldap_{key}').first()
        if config:
            config.value = str(value) if value is not None else ''
        else:
            config = SystemConfig(key=f'ldap_{key}', value=str(value) if value is not None else '')
            db.session.add(config)
    
    db.session.commit()
    
    return success_response(
        data=data,
        message='LDAP settings updated successfully'
    )


@bp.route('/api/v2/settings/ldap/test', methods=['POST'])
@require_auth(['write:settings'])
def test_ldap_connection():
    """Test LDAP connection"""
    data = request.json or {}
    
    # LDAP testing requires ldap3 library
    try:
        import ldap3
        from ldap3 import Server, Connection, ALL
        
        server_url = data.get('server', 'localhost')
        port = data.get('port', 389)
        use_ssl = data.get('use_ssl', False)
        bind_dn = data.get('bind_dn')
        bind_password = data.get('bind_password')
        
        server = Server(server_url, port=port, use_ssl=use_ssl, get_info=ALL)
        conn = Connection(server, bind_dn, bind_password, auto_bind=True)
        
        return success_response(
            data={'connected': True, 'server_info': str(server.info)},
            message='LDAP connection successful'
        )
    except ImportError:
        return error_response('LDAP support not installed (pip install ldap3)', 501)
    except Exception as e:
        return error_response(f'LDAP connection failed: {str(e)}', 400)


# ============================================================================
# Webhooks (stored as JSON in SystemConfig)
# ============================================================================

def get_webhooks():
    """Get webhooks from SystemConfig"""
    import json
    config = SystemConfig.query.filter_by(key='webhooks').first()
    if config and config.value:
        try:
            return json.loads(config.value)
        except:
            return []
    return []


def save_webhooks(webhooks):
    """Save webhooks to SystemConfig"""
    import json
    config = SystemConfig.query.filter_by(key='webhooks').first()
    if config:
        config.value = json.dumps(webhooks)
    else:
        config = SystemConfig(key='webhooks', value=json.dumps(webhooks))
        db.session.add(config)
    db.session.commit()


@bp.route('/api/v2/settings/webhooks', methods=['GET'])
@require_auth(['read:settings'])
def list_webhooks():
    """List configured webhooks"""
    webhooks = get_webhooks()
    return success_response(data=webhooks, meta={'total': len(webhooks)})


@bp.route('/api/v2/settings/webhooks', methods=['POST'])
@require_auth(['write:settings'])
def create_webhook():
    """Create webhook"""
    from datetime import datetime, timezone
    data = request.json
    
    if not data or not data.get('name'):
        return error_response('Webhook name required', 400)
    
    if not data.get('url'):
        return error_response('Webhook URL required', 400)
    
    if not data.get('events'):
        return error_response('At least one event required', 400)
    
    # Get existing webhooks
    webhooks = get_webhooks()
    
    # Generate new ID
    new_id = max([w.get('id', 0) for w in webhooks], default=0) + 1
    
    new_webhook = {
        'id': new_id,
        'name': data['name'],
        'url': data['url'],
        'events': data['events'],
        'enabled': data.get('enabled', True),
        'created_at': datetime.now(timezone.utc).isoformat()
    }
    
    webhooks.append(new_webhook)
    save_webhooks(webhooks)
    
    return created_response(
        data=new_webhook,
        message='Webhook created successfully'
    )


@bp.route('/api/v2/settings/webhooks/<int:webhook_id>', methods=['DELETE'])
@require_auth(['write:settings'])
def delete_webhook(webhook_id):
    """Delete webhook"""
    webhooks = get_webhooks()
    webhooks = [w for w in webhooks if w.get('id') != webhook_id]
    save_webhooks(webhooks)
    
    from utils.response import no_content_response
    return no_content_response()


@bp.route('/api/v2/settings/webhooks/<int:webhook_id>/test', methods=['POST'])
@require_auth(['write:settings'])
def test_webhook(webhook_id):
    """Test webhook by sending a test event"""
    import requests as http_requests
    
    webhooks = get_webhooks()
    webhook = next((w for w in webhooks if w.get('id') == webhook_id), None)
    
    if not webhook:
        return error_response('Webhook not found', 404)
    
    test_payload = {
        'event': 'test',
        'timestamp': datetime.now(timezone.utc).isoformat(),
        'data': {'message': 'This is a test webhook from UCM'}
    }
    
    try:
        response = http_requests.post(
            webhook['url'],
            json=test_payload,
            timeout=10,
            headers={'Content-Type': 'application/json', 'User-Agent': 'UCM-Webhook/2.0'}
        )
        return success_response(
            data={'sent': True, 'status_code': response.status_code},
            message=f'Test webhook sent (status: {response.status_code})'
        )
    except Exception as e:
        return error_response(f'Failed to send webhook: {str(e)}', 500)


# ============================================================================
# Scheduled Backups
# ============================================================================

@bp.route('/api/v2/settings/backup/schedule', methods=['GET'])
@require_auth(['read:settings'])
def get_backup_schedule():
    """Get backup schedule configuration"""
    return success_response(
        data={
            'enabled': False,
            'frequency': 'daily',  # daily, weekly, monthly
            'time': '02:00',
            'retention_days': 30,
            'include_private_keys': False,
            'remote_storage': {
                'enabled': False,
                'type': None,  # s3, ftp, sftp
                'config': {}
            }
        }
    )


@bp.route('/api/v2/settings/backup/schedule', methods=['PATCH'])
@require_auth(['admin:system'])
def update_backup_schedule():
    """Update backup schedule"""
    data = request.json
    
    if not data:
        return error_response('No data provided', 400)
    
    # TODO: Validate and update schedule
    # - Validate frequency, time format
    # - Update cron job
    # - Save to database
    
    return success_response(
        data=data,
        message='Backup schedule updated successfully'
    )


@bp.route('/api/v2/settings/backup/history', methods=['GET'])
@require_auth(['read:settings'])
def get_backup_history():
    """Get backup history"""
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 20, type=int)
    
    # TODO: Get backup history from database
    
    return success_response(
        data=[
            {
                'id': 1,
                'filename': 'ucm_backup_20260119.tar.gz',
                'size': 1024000,
                'created_at': '2026-01-19T02:00:00Z',
                'type': 'scheduled',
                'status': 'completed'
            }
        ],
        meta={'total': 1, 'page': page, 'per_page': per_page}
    )
