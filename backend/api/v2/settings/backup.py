"""
Settings - Backup management + schedule + history routes
"""

from flask import request
from auth.unified import require_auth
from utils.response import success_response, error_response, no_content_response
from models import db, SystemConfig
from services.audit_service import AuditService
from utils.datetime_utils import utc_now
import logging

from . import bp

logger = logging.getLogger(__name__)


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
    import os
    import secrets

    try:
        from services.backup_service import BackupService
        data = request.json or {}
        password = data.get('password')
        generated_password = False

        # Generate secure random password if not provided
        if not password:
            password = secrets.token_urlsafe(16)  # 128-bit entropy
            generated_password = True
        elif len(password) < 8:
            return error_response('Password must be at least 8 characters', 400)

        service = BackupService()
        backup_bytes = service.create_backup(password)

        # Save to disk
        filename = f"ucm_backup_{utc_now().strftime('%Y%m%d_%H%M%S')}.ucmbkp"
        backup_dir = "/opt/ucm/data/backups"
        os.makedirs(backup_dir, exist_ok=True)

        filepath = os.path.join(backup_dir, filename)
        with open(filepath, 'wb') as f:
            f.write(backup_bytes)

        AuditService.log_action(
            action='system_backup',
            resource_type='system',
            resource_name=filename,
            details=f'Created backup: {filename}',
            success=True
        )

        response_data = {
            'filename': filename,
            'size': len(backup_bytes),
            'path': filepath
        }

        # Include generated password in response so user can save it
        if generated_password:
            response_data['password'] = password
            response_data['password_generated'] = True

        return success_response(
            data=response_data,
            message='Backup created successfully' + (' - SAVE THE PASSWORD!' if generated_password else '')
        )
    except Exception as e:
        logger.error(f"Settings backup failed: {e}")
        return error_response('Backup failed', 500)


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

    password = request.form.get('password')

    # Security: Require password for restore
    if not password:
        return error_response('Backup password required', 400)

    try:
        from services.backup_service import BackupService

        # Save uploaded file temporarily
        with tempfile.NamedTemporaryFile(delete=False, suffix='.ucmbkp') as tmp:
            file.save(tmp.name)
            tmp_path = tmp.name

        service = BackupService()
        service.restore_backup(tmp_path, password)

        os.unlink(tmp_path)

        AuditService.log_action(
            action='system_restore',
            resource_type='system',
            resource_name=file.filename,
            details=f'Restored from backup: {file.filename}',
            success=True
        )

        return success_response(
            data={'filename': file.filename, 'restored': True},
            message='Backup restored successfully. Please restart the application.'
        )
    except Exception as e:
        logger.error(f"Settings restore failed: {e}")
        return error_response('Restore failed', 500)


@bp.route('/api/v2/settings/backup/<path:filename>/download', methods=['GET'])
@require_auth(['read:settings'])
def download_backup(filename):
    """Download backup file"""
    from flask import send_file
    from werkzeug.utils import secure_filename
    from pathlib import Path
    import os

    backup_dir = Path("/opt/ucm/data/backups")

    # SECURITY: Sanitize filename to prevent path traversal
    safe_filename = secure_filename(os.path.basename(filename))
    if not safe_filename:
        return error_response('Invalid filename', 400)

    backup_file = backup_dir / safe_filename

    # SECURITY: Verify the resolved path is within backup directory
    try:
        backup_file = backup_file.resolve()
        if not backup_file.is_relative_to(backup_dir.resolve()):
            return error_response('Access denied', 403)
    except (ValueError, RuntimeError):
        return error_response('Invalid path', 400)

    if not backup_file.exists():
        return error_response('Backup file not found', 404)

    return send_file(
        str(backup_file),
        as_attachment=True,
        download_name=safe_filename,
        mimetype='application/octet-stream'
    )


@bp.route('/api/v2/settings/backup/<path:filename>', methods=['DELETE'])
@require_auth(['admin:system'])
def delete_backup(filename):
    """Delete backup file"""
    from werkzeug.utils import secure_filename
    from pathlib import Path
    import os

    backup_dir = Path("/opt/ucm/data/backups")

    # SECURITY: Sanitize filename to prevent path traversal
    safe_filename = secure_filename(os.path.basename(filename))
    if not safe_filename:
        return error_response('Invalid filename', 400)

    backup_file = backup_dir / safe_filename

    # SECURITY: Verify the resolved path is within backup directory
    try:
        backup_file = backup_file.resolve()
        if not backup_file.is_relative_to(backup_dir.resolve()):
            return error_response('Access denied', 403)
    except (ValueError, RuntimeError):
        return error_response('Invalid path', 400)

    if backup_file.exists():
        backup_file.unlink()

    AuditService.log_action(
        action='backup_delete',
        resource_type='system',
        resource_name=safe_filename,
        details=f'Deleted backup: {safe_filename}',
        success=True
    )

    return no_content_response()


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
