"""
System Backup Operations
"""

from . import bp
from flask import request, current_app, send_from_directory
from auth.unified import require_auth
from utils.response import success_response, error_response
from models import db
from services.audit_service import AuditService
from services.backup_service import BackupService
from pathlib import Path
import os
import werkzeug.utils
from datetime import datetime, timezone
import logging
from utils.datetime_utils import utc_now
from utils.file_validation import validate_upload, BACKUP_EXTENSIONS

logger = logging.getLogger(__name__)


@bp.route('/api/v2/system/backup', methods=['POST'])
@bp.route('/api/v2/system/backup/create', methods=['POST'])
@require_auth(['admin:system'])
def create_backup():
    """Create encrypted backup"""
    try:
        data = request.json or {}
        password = data.get('password')

        if not password:
            return error_response("Password required for encryption", 400)

        if len(password) < 12:
            return error_response("Password must be at least 12 characters", 400)

        service = BackupService()
        backup_bytes = service.create_backup(password)

        # Save to disk
        filename = f"ucm_backup_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}.ucmbkp"
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

        # Format size
        size = len(backup_bytes)
        if size > 1024*1024:
            size_str = f"{size/1024/1024:.1f} MB"
        elif size > 1024:
            size_str = f"{size/1024:.1f} KB"
        else:
            size_str = f"{size} B"

        return success_response(
            message="Backup created successfully",
            data={
                'filename': filename,
                'size': size_str,
                'path': filepath
            }
        )
    except ValueError as e:
        logger.warning(f"Backup validation error: {e}")
        return error_response("Invalid backup parameters", 400)
    except Exception as e:
        logger.error(f"Backup failed: {e}")
        return error_response("Backup failed", 500)


@bp.route('/api/v2/system/backups', methods=['GET'])
@bp.route('/api/v2/system/backup/list', methods=['GET'])
@require_auth(['read:settings'])
def list_backups():
    """List available backups"""
    try:
        backup_dir = "/opt/ucm/data/backups"
        if not os.path.exists(backup_dir):
            return success_response(data=[])

        files = []
        for f in os.listdir(backup_dir):
            if f.endswith('.ucmbkp') or f.endswith('.json.enc'):
                path = os.path.join(backup_dir, f)
                stat = os.stat(path)

                # Format size
                size = stat.st_size
                if size > 1024*1024:
                    size_str = f"{size/1024/1024:.1f} MB"
                elif size > 1024:
                    size_str = f"{size/1024:.1f} KB"
                else:
                    size_str = f"{size} B"

                files.append({
                    'filename': f,
                    'size': size_str,
                    'size_bytes': size,
                    'created_at': datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')
                })

        # Sort by date desc
        files.sort(key=lambda x: x['size_bytes'], reverse=True)
        files.sort(key=lambda x: x['created_at'], reverse=True)
        return success_response(data=files)
    except Exception as e:
        logger.error(f"Failed to list backups: {e}")
        return error_response("Failed to list backups")


@bp.route('/api/v2/system/backup/<filename>/download', methods=['GET'])
@require_auth(['read:settings'])
def download_backup(filename):
    """Download backup file"""
    backup_dir = "/opt/ucm/data/backups"
    filename = werkzeug.utils.secure_filename(filename)
    return send_from_directory(
        backup_dir,
        filename,
        as_attachment=True,
        mimetype='application/octet-stream'
    )


@bp.route('/api/v2/system/backup/<filename>', methods=['DELETE'])
@require_auth(['admin:system'])
def delete_backup(filename):
    """Delete a backup file"""
    try:
        backup_dir = "/opt/ucm/data/backups"
        filename = werkzeug.utils.secure_filename(filename)
        filepath = os.path.join(backup_dir, filename)

        if not os.path.exists(filepath):
            return error_response("Backup file not found", 404)

        os.remove(filepath)
        AuditService.log_action(
            action='backup_delete',
            resource_type='system',
            resource_name=filename,
            details=f'Deleted backup: {filename}',
            success=True
        )
        return success_response(message="Backup deleted successfully")
    except Exception as e:
        logger.error(f"Failed to delete backup: {e}")
        return error_response("Failed to delete backup", 500)


@bp.route('/api/v2/system/restore', methods=['POST'])
@bp.route('/api/v2/system/backup/restore', methods=['POST'])
@require_auth(['admin:system'])
def restore_backup():
    """Restore from backup file"""
    try:
        if 'file' not in request.files:
            return error_response("No backup file provided", 400)

        file = request.files['file']
        password = request.form.get('password')

        if not password:
            return error_response("Password required for decryption", 400)

        if len(password) < 12:
            return error_response("Password must be at least 12 characters", 400)

        # Read file content with size validation
        try:
            backup_bytes, _ = validate_upload(file, BACKUP_EXTENSIONS, max_size=100 * 1024 * 1024)
        except ValueError as e:
            logger.warning(f"Backup upload validation error: {e}")
            return error_response("Invalid backup file", 400)

        service = BackupService()
        results = service.restore_backup(backup_bytes, password)

        AuditService.log_action(
            action='system_restore',
            resource_type='system',
            resource_name='Backup Restore',
            details='Restored from backup file',
            success=True
        )

        return success_response(
            message="Backup restored successfully",
            data=results
        )
    except ValueError as e:
        logger.warning(f"Restore validation error: {e}")
        return error_response("Invalid restore parameters", 400)
    except Exception as e:
        logger.error(f"Restore failed: {e}")
        return error_response("Restore failed", 500)
