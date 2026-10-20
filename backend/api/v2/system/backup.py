"""
System Backup Operations
"""

from services.backup import storage
from services.backup.locking import BackupBusyError, backup_operation_lock
from services.backup.restore.plan import RestoreValidationError
from services.backup.restore_report import with_restore_warnings
from services.database_admin.lock import (
    MigrationBusyError,
    database_migration_lock,
    pending_switch_refusal,
)
from fips_mode import FipsRestricted
from services.backup.decrypt_mixin import BackupDecryptionError
from services.backup.settings_contract import (
    BackupSettingError,
    validate_backup_password,
)
from . import bp
from flask import send_file, request
from auth.unified import require_auth
from utils.response import success_response, error_response
from utils.pagination import parse_request_pagination
from services.audit_service import AuditService
from services.backup.backup_service import check_backup_kdf
from services.backup_service import (
    BackupService,
    BackupExportError,
    BackupPasswordError,
    BackupSchemaError,
    BackupValidationError,
    ContainerError,
)
from datetime import datetime, timezone
import logging
from utils.file_validation import validate_upload, BACKUP_EXTENSIONS

logger = logging.getLogger(__name__)

# Both steps moved to `services/backup/restore_completion.py`, which the
# Settings route calls too: each of them was written on one route and not the
# other, and the difference showed up as a restore that behaved differently
# depending on which page had asked for it.
from services.backup.restore_completion import (
    record_restore as _safe_audit_log,
    request_restart as _request_restart_after_restore,
    restore_message,
)
# Upload ceiling for a restore, and the bounds of a listing or a bulk request.
MAX_RESTORE_UPLOAD_BYTES = 100 * 1024 * 1024
LIST_DEFAULT_PER_PAGE = 20
LIST_MAX_PER_PAGE = 100
MAX_BULK_DELETE = 1000

# Seconds a deletion waits for the backup lock before answering 409.
DELETE_LOCK_WAIT = 15
BULK_DELETE_LOCK_WAIT = 30
# Positive so that a busy lock raises instead of reporting "0 removed".
RETENTION_LOCK_WAIT = 30

_SORT_KEYS = {
    'created_desc': (lambda item: (item['_mtime'], item['filename']), True),
    'created_asc': (lambda item: (item['_mtime'], item['filename']), False),
    'size_desc': (lambda item: (item['size_bytes'], item['filename']), True),
    'size_asc': (lambda item: (item['size_bytes'], item['filename']), False),
    'name_asc': (lambda item: (item['filename'].lower(), item['filename']), False),
    'name_desc': (lambda item: (item['filename'].lower(), item['filename']), True),
}
_DEFAULT_SORT = 'created_desc'


def _format_size(size_bytes: int) -> str:
    """`N B`, `N.N KB` or `N.N MB`."""
    if size_bytes < 1024:
        return f'{size_bytes} B'
    if size_bytes < 1024 * 1024:
        return f'{size_bytes / 1024:.1f} KB'
    return f'{size_bytes / (1024 * 1024):.1f} MB'


def _scan_archives(directory) -> list:
    """Regular archive files of the directory; links and foreign names are skipped."""
    items = []
    if not directory.is_dir():
        return items
    for entry in directory.iterdir():
        try:
            path, name = storage.resolve_archive(entry.name, directory)
            if entry.is_symlink() or not entry.is_file():
                continue
            st = entry.lstat()
        except (ValueError, PermissionError, OSError):
            continue
        items.append({
            'filename': name,
            'size_bytes': st.st_size,
            '_mtime': st.st_mtime,
        })
    return items


def _disk_meta(directory) -> dict:
    """Disk figures for the listing, empty when they cannot be read."""
    import shutil
    try:
        # Before the first archive the directory does not exist yet: measure
        # the nearest ancestor that does, which is the filesystem it will use.
        target = directory
        while not target.exists() and target.parent != target:
            target = target.parent
        usage = shutil.disk_usage(target)
        return {
            'disk_total_bytes': usage.total,
            'disk_free_bytes': usage.free,
            'disk_free': _format_size(usage.free),
            'disk_used_pct': (round(usage.used * 100 / usage.total, 1)
                              if usage.total else None),
        }
    except Exception:
        logger.warning('Backup listing: disk usage could not be read')
        return {}


@bp.route('/api/v2/system/backup', methods=['POST'])
@bp.route('/api/v2/system/backup/create', methods=['POST'])
@require_auth(['admin:system'])
def create_backup():
    """Create an encrypted archive in the backup directory."""
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        data = {}

    password = data.get('password')
    if not password:
        return error_response('Backup password required', 400)
    try:
        validate_backup_password(password)
    except BackupSettingError as e:
        return error_response(str(e), 400)

    kdf = data.get('kdf')
    try:
        check_backup_kdf(kdf)
    except FipsRestricted:
        raise
    except ValueError as e:
        return error_response(str(e), 400)

    try:
        backup_bytes = BackupService().create_backup(password, kdf=kdf)
        _filepath, filename = storage.create_archive(backup_bytes)
    except FipsRestricted:
        raise  # the application maps it to its problem type
    except BackupPasswordError as e:
        return error_response(str(e), 400)
    except BackupExportError as e:
        logger.error('Backup aborted: %s', e)
        return error_response(f'Backup aborted: {e}', 500)
    except BackupValidationError as e:
        logger.error('Backup written but not validated: %s', e)
        return error_response(f'Backup could not be validated: {e}', 500)
    except ValueError:
        logger.exception('Backup refused: invalid parameters')
        return error_response('Invalid backup parameters', 400)
    except Exception:
        logger.exception('Backup failed')
        return error_response('Backup failed', 500)

    _safe_audit_log(
        action='system_backup',
        resource_type='system',
        resource_name=filename,
        details=f'Created backup: {filename}',
        success=True,
    )

    size = len(backup_bytes)
    return success_response(
        data={
            'filename': filename,
            'size': _format_size(size),
            'size_bytes': size,
            'download_url': f'/api/v2/system/backup/{filename}/download',
        },
        message='Backup created successfully',
    )


@bp.route('/api/v2/system/backups', methods=['GET'])
@bp.route('/api/v2/system/backup/list', methods=['GET'])
@require_auth(['admin:system'])
def list_backups():
    """Paginated, searchable, sortable listing of the archives."""
    page, per_page = parse_request_pagination(
        default_per_page=LIST_DEFAULT_PER_PAGE, max_per_page=LIST_MAX_PER_PAGE)
    search = (request.args.get('search') or '').strip().lower()
    sort = request.args.get('sort') or _DEFAULT_SORT
    if sort not in _SORT_KEYS:
        sort = _DEFAULT_SORT

    try:
        directory = storage.backup_directory()
        everything = _scan_archives(directory)
        matching = ([item for item in everything
                     if search in item['filename'].lower()]
                    if search else list(everything))
        key, reverse = _SORT_KEYS[sort]
        matching.sort(key=key, reverse=reverse)

        total = len(matching)
        start = (page - 1) * per_page
        items = [{
            'filename': item['filename'],
            'size': _format_size(item['size_bytes']),
            'size_bytes': item['size_bytes'],
            'created_at': datetime.fromtimestamp(
                item['_mtime'], timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC'),
        } for item in matching[start:start + per_page]]

        total_size = sum(item['size_bytes'] for item in matching)
        total_size_all = sum(item['size_bytes'] for item in everything)
        meta = {
            'total': total,
            'total_all': len(everything),
            'total_size_bytes': total_size,
            'total_size': _format_size(total_size),
            'total_size_all_bytes': total_size_all,
            'total_size_all': _format_size(total_size_all),
            'page': page,
            'per_page': per_page,
            'pages': max(1, -(-total // per_page)),
        }
    except Exception:
        logger.exception('Failed to list backups')
        return error_response('Failed to list backups', 500)

    meta.update(_disk_meta(directory))
    return success_response(data={'items': items, 'meta': meta})


@bp.route('/api/v2/system/backup/<filename>/download', methods=['GET'])
@require_auth(['admin:system'])
def download_backup(filename):
    """Serve one archive as an attachment."""
    try:
        backup_file, safe_filename = storage.resolve_archive(filename)
    except ValueError:
        return error_response('Invalid backup filename', 400)
    except PermissionError:
        return error_response('Access denied', 403)

    if backup_file.is_symlink() or not backup_file.is_file():
        return error_response('Backup file not found', 404)

    return send_file(
        backup_file,
        as_attachment=True,
        download_name=safe_filename,
        mimetype='application/octet-stream',
        conditional=True,
    )


@bp.route('/api/v2/system/backup/<filename>', methods=['DELETE'])
@require_auth(['admin:system'])
def delete_backup(filename):
    """Delete one archive, under the backup lock."""
    try:
        backup_file, safe_filename = storage.resolve_archive(filename)
    except ValueError:
        return error_response('Invalid backup filename', 400)
    except PermissionError:
        return error_response('Access denied', 403)

    if backup_file.is_symlink() or not backup_file.is_file():
        return error_response('Backup file not found', 404)

    try:
        with backup_operation_lock(timeout=DELETE_LOCK_WAIT,
                                   purpose='deleting a backup'):
            # Checked again under the lock: another deletion may have won.
            if backup_file.is_symlink() or not backup_file.is_file():
                return error_response('Backup file not found', 404)
            backup_file.unlink()
    except BackupBusyError as busy:
        logger.info('Backup deletion refused: %s', busy)
        return error_response(str(busy), 409)
    except OSError:
        logger.exception('Failed to delete backup %s', safe_filename)
        return error_response('Failed to delete backup', 500)

    _safe_audit_log(
        action='backup_delete',
        resource_type='system',
        resource_name=safe_filename,
        details=f'Deleted backup: {safe_filename}',
        success=True,
    )
    return success_response(message='Backup deleted successfully')


@bp.route('/api/v2/system/backups/bulk-delete', methods=['POST'])
@require_auth(['admin:system'])
def bulk_delete_backups():
    """Delete several archives under one hold of the backup lock."""
    data = request.get_json(silent=True)
    filenames = data.get('filenames') if isinstance(data, dict) else None
    if not isinstance(filenames, list) or not filenames:
        return error_response('filenames must be a non-empty list', 400)
    if len(filenames) > MAX_BULK_DELETE:
        return error_response(
            f'At most {MAX_BULK_DELETE} backups can be deleted at once', 400)

    counts = {'deleted': 0, 'missing': 0, 'invalid': 0, 'failed': 0}
    deleted_names = []
    seen = set()
    try:
        with backup_operation_lock(timeout=BULK_DELETE_LOCK_WAIT,
                                   purpose='deleting backups'):
            for raw in filenames:
                # A name that cannot be resolved is counted, never fatal.
                try:
                    path, name = storage.resolve_archive(raw)
                except Exception:
                    counts['invalid'] += 1
                    continue
                if path in seen:
                    continue
                seen.add(path)
                if path.is_symlink() or not path.is_file():
                    counts['missing'] += 1
                    continue
                try:
                    path.unlink()
                except OSError:
                    logger.exception('Bulk delete: could not remove %s', name)
                    counts['failed'] += 1
                    continue
                counts['deleted'] += 1
                deleted_names.append(name)
    except BackupBusyError as busy:
        logger.info('Bulk backup deletion refused: %s', busy)
        return error_response(str(busy), 409)

    _safe_audit_log(
        action='backup_delete',
        resource_type='system',
        resource_name=f"{counts['deleted']} backup(s)",
        details=(f"Bulk deleted {counts['deleted']} backup(s) "
                 f"(missing {counts['missing']}, invalid {counts['invalid']}, "
                 f"failed {counts['failed']}): {', '.join(deleted_names)}"),
        success=counts['failed'] == 0,
    )
    return success_response(
        data=counts, message=f"Deleted {counts['deleted']} backup(s)")


@bp.route('/api/v2/system/backups/run-retention', methods=['POST'])
@require_auth(['admin:system'])
def run_retention_now():
    """Apply the retention policy now."""
    from services.backup.schedule import run_backup_retention

    try:
        removed = run_backup_retention(wait=RETENTION_LOCK_WAIT)
    except BackupBusyError as busy:
        logger.info('Retention refused: %s', busy)
        return error_response(str(busy), 409)
    except Exception:
        logger.exception('Failed to apply backup retention')
        return error_response('Failed to apply retention', 500)

    _safe_audit_log(
        action='backup_delete',
        resource_type='system',
        details=f'Retention applied on demand: removed {removed} backup(s)',
        success=True,
    )
    return success_response(
        data={'removed': removed},
        message=f'Retention applied: removed {removed} backup(s)')


@bp.route('/api/v2/system/restore', methods=['POST'])
@bp.route('/api/v2/system/backup/restore', methods=['POST'])
@require_auth(['admin:system'])
def restore_backup():
    """Restore an uploaded archive, replacing (default) or merging.

    Only restore archives you produced yourself: a replacing restore puts back
    users, private keys and secrets exactly as the archive holds them.
    """
    if 'file' not in request.files:
        return error_response('No backup file provided', 400)
    file = request.files['file']
    if not file.filename:
        return error_response('No file selected', 400)

    password = request.form.get('password')
    if not password:
        return error_response('Backup password required', 400)

    mode = (request.form.get('mode') or 'replace').strip().lower()
    if mode not in ('replace', 'merge'):
        return error_response("mode must be 'replace' or 'merge'", 400)

    try:
        try:
            backup_bytes, _ = validate_upload(
                file, BACKUP_EXTENSIONS, max_size=MAX_RESTORE_UPLOAD_BYTES)
        except ValueError as exc:
            logger.warning('Backup upload refused: %s', exc)
            return error_response('Invalid backup file', 400)

        # A restore landing before a pending backend switch is lost at restart.
        pending = pending_switch_refusal()
        if pending:
            return error_response(pending, 409)

        try:
            with database_migration_lock(purpose='the restore'):
                results = BackupService().restore_backup(
                    backup_bytes, password, mode=mode)
        except MigrationBusyError as busy:
            return error_response(
                f'{busy} A backend migration or another restore is still '
                'running.', 409)

        carried = bool((results or {}).get('sections_carried'))
        _safe_audit_log(
            action='system_restore',
            resource_type='system',
            resource_name=file.filename,
            details=(f'Restored from backup: {file.filename}' if carried else
                     f'Backup carried no data section, nothing was restored: '
                     f'{file.filename}'),
            success=True,
        )

        # Nothing changed, so no session is revoked and no restart is asked.
        if not carried:
            logger.warning('Restore: the archive carried no data section')
            return success_response(
                data=results,
                message=('The archive carried no data: nothing was restored, '
                         'no session was revoked and no restart is needed.'),
            )

        from services.backup.restore.invalidate import invalidate_after_restore
        try:
            results['invalidated'] = invalidate_after_restore()
        except Exception:
            logger.exception('Restore: sessions could not be revoked')
            return error_response(
                'Backup restored, but the sessions opened before it could not '
                'be revoked. Restart the application before using it.', 500)

        restart_ok, restart_detail = _request_restart_after_restore()
        results['restart_requested'] = restart_ok
        results['restart_detail'] = restart_detail
        results['filename'] = file.filename
        return success_response(data=results, message=restore_message(results))
    except FipsRestricted:
        raise  # the application maps it to its problem type, message unchanged
    except BackupDecryptionError:
        logger.warning('Restore refused: the backup could not be decrypted')
        return error_response(
            'Wrong backup password, or the file is not a valid backup', 400)
    except (ContainerError, BackupSchemaError, RestoreValidationError) as e:
        logger.warning('Restore refused: %s', e)
        return error_response(str(e), 400)
    except OverflowError as e:
        logger.warning('Restore refused: a value is out of range (%s)', e)
        return error_response(
            'The archive carries a numeric value this database cannot '
            'store; the file is not a valid backup', 400)
    except ValueError as e:
        logger.warning('Restore refused: %s', e)
        return error_response(f'The archive could not be read: {e}', 400)
    except Exception:
        logger.exception('Restore failed')
        return error_response('Restore failed', 500)
