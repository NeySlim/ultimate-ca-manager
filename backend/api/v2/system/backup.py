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


def _backup_dir() -> str:
    """Backup directory (honours DATA_DIR for RPM/Docker layouts)."""
    try:
        from config.settings import Config
        return str(Config.BACKUP_DIR)
    except Exception:
        return "/opt/ucm/data/backups"


def _human_size(n: int) -> str:
    if n > 1024 * 1024:
        return f"{n/1024/1024:.1f} MB"
    if n > 1024:
        return f"{n/1024:.1f} KB"
    return f"{n} B"


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
    """List available backups (paginated, searchable, sortable) with a summary.

    Query params: page, per_page (≤100), search, sort
    (created_desc|created_asc|size_desc|size_asc|name_asc|name_desc).
    Returns {items, meta} where meta carries total count/size and disk usage so
    the UI can warn before the disk fills.
    """
    try:
        backup_dir = _backup_dir()
        files = []
        if os.path.exists(backup_dir):
            for f in os.listdir(backup_dir):
                if f.endswith('.ucmbkp') or f.endswith('.json.enc'):
                    try:
                        st = os.stat(os.path.join(backup_dir, f))
                    except OSError:
                        continue
                    files.append({
                        'filename': f,
                        'size': _human_size(st.st_size),
                        'size_bytes': st.st_size,
                        'mtime': st.st_mtime,
                        'created_at': datetime.fromtimestamp(
                            st.st_mtime, tz=timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC'),
                    })

        total_size = sum(f['size_bytes'] for f in files)

        # Search (filename substring, case-insensitive)
        search = (request.args.get('search') or '').strip().lower()
        if search:
            files = [f for f in files if search in f['filename'].lower()]

        # Sort
        sort = request.args.get('sort', 'created_desc')
        sorters = {
            'created_desc': (lambda x: x['mtime'], True),
            'created_asc': (lambda x: x['mtime'], False),
            'size_desc': (lambda x: x['size_bytes'], True),
            'size_asc': (lambda x: x['size_bytes'], False),
            'name_asc': (lambda x: x['filename'].lower(), False),
            'name_desc': (lambda x: x['filename'].lower(), True),
        }
        key, reverse = sorters.get(sort, sorters['created_desc'])
        files.sort(key=key, reverse=reverse)

        filtered_total = len(files)

        # Pagination
        try:
            page = max(1, int(request.args.get('page', 1)))
        except (ValueError, TypeError):
            page = 1
        try:
            per_page = min(100, max(1, int(request.args.get('per_page', 20))))
        except (ValueError, TypeError):
            per_page = 20
        start = (page - 1) * per_page
        page_items = files[start:start + per_page]
        for f in page_items:
            f.pop('mtime', None)

        # Disk usage of the filesystem holding the backups
        disk = {}
        try:
            import shutil as _sh
            du = _sh.disk_usage(backup_dir if os.path.exists(backup_dir) else '/')
            disk = {
                'disk_total_bytes': du.total,
                'disk_free_bytes': du.free,
                'disk_free': _human_size(du.free),
                'disk_used_pct': round(du.used / du.total * 100, 1) if du.total else None,
            }
        except OSError:
            pass

        meta = {
            'total': filtered_total,
            'total_all': len(files) if not search else None,
            'total_size_bytes': total_size,
            'total_size': _human_size(total_size),
            'page': page,
            'per_page': per_page,
            'pages': max(1, (filtered_total + per_page - 1) // per_page),
            **disk,
        }
        return success_response(data={'items': page_items, 'meta': meta})
    except Exception as e:
        logger.error(f"Failed to list backups: {e}")
        return error_response("Failed to list backups")


@bp.route('/api/v2/system/backup/<filename>/download', methods=['GET'])
@require_auth(['read:settings'])
def download_backup(filename):
    """Download backup file"""
    backup_dir = _backup_dir()
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
        backup_dir = _backup_dir()
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


@bp.route('/api/v2/system/backups/bulk-delete', methods=['POST'])
@require_auth(['admin:system'])
def bulk_delete_backups():
    """Delete several backups at once. Body: {"filenames": [...]}."""
    data = request.get_json(silent=True) or {}
    names = data.get('filenames')
    if not isinstance(names, list) or not names:
        return error_response("filenames must be a non-empty list", 400)
    if len(names) > 1000:
        return error_response("Too many files in one request", 400)

    backup_dir = _backup_dir()
    deleted, missing = 0, 0
    for raw in names:
        safe = werkzeug.utils.secure_filename(str(raw))
        if not safe or not (safe.endswith('.ucmbkp') or safe.endswith('.json.enc')):
            continue
        path = os.path.join(backup_dir, safe)
        if not os.path.exists(path):
            missing += 1
            continue
        try:
            os.remove(path)
            deleted += 1
        except OSError:
            continue

    AuditService.log_action(
        action='backup_delete', resource_type='system',
        resource_name=f'{deleted} backup(s)',
        details=f'Bulk-deleted {deleted} backup(s)', success=True)
    return success_response(
        data={'deleted': deleted, 'missing': missing},
        message=f'Deleted {deleted} backup(s)')


@bp.route('/api/v2/system/backups/run-retention', methods=['POST'])
@require_auth(['admin:system'])
def run_retention_now():
    """Apply the configured backup retention immediately."""
    try:
        from services.backup.schedule import run_backup_retention
        removed = run_backup_retention()
    except Exception as e:
        logger.error(f"Run retention failed: {e}")
        return error_response("Failed to apply retention", 500)
    AuditService.log_action(
        action='backup_delete', resource_type='system',
        resource_name=f'{removed} backup(s)',
        details=f'Applied retention, removed {removed} expired backup(s)', success=True)
    return success_response(
        data={'removed': removed},
        message=f'Retention applied — removed {removed} backup(s)')


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
