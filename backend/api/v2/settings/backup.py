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
        from services.backup_service import BackupService, BackupPasswordError
        data = request.json or {}
        password = data.get('password')
        generated_password = False

        # Generate secure random password if not provided
        if not password:
            password = secrets.token_urlsafe(16)  # 128-bit entropy
            generated_password = True
        else:
            # The same rule as the system backup route (#346)
            try:
                BackupService.validate_password(password)
            except BackupPasswordError as e:
                return error_response(str(e), 400)

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
    """Restore from backup file.

    A restore replaces users, private keys and secrets from the archive — only
    restore backups you produced yourself (see the Backup & Restore wiki page
    for the trust model).
    """
    if 'file' not in request.files:
        return error_response('No backup file provided', 400)

    file = request.files['file']
    if file.filename == '':
        return error_response('No file selected', 400)

    password = request.form.get('password')
    if not password:
        return error_response('Backup password required', 400)

    try:
        from services.backup_service import BackupService, BackupPasswordError
        from utils.file_validation import validate_upload, BACKUP_EXTENSIONS

        # Read + size-cap the upload as bytes (restore_backup expects bytes, not
        # a path). Reading in memory also avoids leaving the encrypted backup on
        # disk in /tmp, which the previous NamedTemporaryFile(delete=False) path
        # did on every failed attempt.
        try:
            backup_bytes, _ = validate_upload(
                file, BACKUP_EXTENSIONS, max_size=100 * 1024 * 1024
            )
        except ValueError as exc:
            logger.warning(f"Backup upload validation error: {exc}")
            return error_response('Invalid backup file', 400)

        service = BackupService()
        service.restore_backup(backup_bytes, password)

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
    """Get backup schedule configuration (derived from General settings)."""
    from services.backup.schedule import get_schedule
    return success_response(data=get_schedule())


@bp.route('/api/v2/settings/backup/schedule', methods=['PATCH'])
@require_auth(['admin:system'])
def update_backup_schedule():
    """Update backup schedule.

    Writes the same General-settings keys the UI uses, so both surfaces stay
    consistent: enabled→auto_backup_enabled, frequency→backup_frequency,
    retention_days→backup_retention_days.
    """
    from . import set_config
    from services.backup.schedule import get_schedule, _VALID_FREQUENCIES
    data = request.json
    if not data:
        return error_response('No data provided', 400)

    if 'enabled' in data:
        set_config('auto_backup_enabled', 'true' if data['enabled'] else 'false')
    if 'frequency' in data:
        if data['frequency'] not in _VALID_FREQUENCIES:
            return error_response(
                f"frequency must be one of {', '.join(_VALID_FREQUENCIES)}", 400)
        set_config('backup_frequency', data['frequency'])
    if 'retention_days' in data:
        try:
            rd = int(data['retention_days'])
        except (ValueError, TypeError):
            return error_response('retention_days must be an integer', 400)
        if rd < 1 or rd > 3650:
            return error_response('retention_days must be between 1 and 3650', 400)
        set_config('backup_retention_days', str(rd))

    try:
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        logger.error(f"Failed to update backup schedule: {e}")
        return error_response('Failed to persist schedule', 500)

    AuditService.log_action(
        action='backup_schedule_updated', resource_type='system',
        details="Backup schedule updated", success=True,
    )
    return success_response(data=get_schedule(),
                            message='Backup schedule updated successfully')


@bp.route('/api/v2/settings/backup/history', methods=['GET'])
@require_auth(['read:settings'])
def get_backup_history():
    """Get backup history (actual backup files on disk)"""
    from services.backup.schedule import list_backups
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 20, type=int)

    all_backups = list_backups()
    total = len(all_backups)
    start = (page - 1) * per_page
    items = all_backups[start:start + per_page]

    return success_response(
        data=items,
        meta={'total': total, 'page': page, 'per_page': per_page}
    )
