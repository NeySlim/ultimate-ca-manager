"""
System Backup Operations
"""

from services.backup import shared_store, storage
from services.backup.locking import BackupBusyError, backup_operation_lock
from services.backup.restore.plan import RestoreValidationError
from services.backup.restore_report import safe_restore_audit_details, with_restore_warnings
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
from utils.ha import reject_in_ha
from utils.sanitize import client_filename
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
from utils.file_validation import validate_upload_name, BACKUP_EXTENSIONS

logger = logging.getLogger(__name__)

# Both steps moved to `services/backup/restore_completion.py`, which the
# Settings route calls too: each of them was written on one route and not the
# other, and the difference showed up as a restore that behaved differently
# depending on which page had asked for it.
from services.backup.restore_completion import (
    record_failure as _audit_failure,
    record_request_refusal,
    record_restore as _safe_audit_log,
    request_restart as _request_restart_after_restore,
    restore_message,
)
# Bounds of a listing or a bulk request; a restore's upload ceiling is
# `storage.restore_upload_limit()`.
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


def _stored_archives() -> list:
    """HA: the archives of the database, the same set from every node."""
    return [{
        'filename': a['filename'],
        'size_bytes': a['size'],
        '_mtime': shared_store.timestamp(a['created_at']),
        'node': a['node'],
        'sha256': a['sha256'],
    } for a in shared_store.list_archives()]


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
        _audit_failure('system_backup', 'manual', 'Backup refused: password missing')
        return error_response('Backup password required', 400)
    try:
        validate_backup_password(password)
    except BackupSettingError as e:
        _audit_failure('system_backup', 'manual', 'Backup refused: password rejected')
        return error_response(str(e), 400)

    kdf = data.get('kdf')
    try:
        check_backup_kdf(kdf)
    except FipsRestricted:
        _audit_failure('system_backup', 'manual', 'Backup refused: not allowed in FIPS mode')
        raise
    except ValueError as e:
        _audit_failure('system_backup', 'manual', 'Backup refused: key derivation not accepted')
        return error_response(str(e), 400)

    try:
        service = BackupService()
        size, _filepath, filename = storage.export_archive(service, password, kdf=kdf)
    except FipsRestricted:
        _audit_failure('system_backup', 'manual', 'Backup refused: not allowed in FIPS mode')
        raise  # the application maps it to its problem type
    except BackupBusyError as busy:
        logger.info('Backup refused: %s', busy)
        _audit_failure('system_backup', 'manual', 'Backup refused: another backup or restore is running')
        return error_response(str(busy), 409)
    except BackupPasswordError as e:
        _audit_failure('system_backup', 'manual', 'Backup refused: password rejected')
        return error_response(str(e), 400)
    except BackupExportError as e:
        logger.error('Backup aborted: %s', e)
        _audit_failure('system_backup', 'manual', 'Backup failed: export aborted')
        return error_response(f'Backup aborted: {e}', 500)
    except BackupValidationError as e:
        logger.error('Backup written but not validated: %s', e)
        _audit_failure('system_backup', 'manual', 'Backup failed: archive could not be validated')
        return error_response(f'Backup could not be validated: {e}', 500)
    except ValueError:
        logger.exception('Backup refused: invalid parameters')
        _audit_failure('system_backup', 'manual', 'Backup refused: invalid parameters')
        return error_response('Invalid backup parameters', 400)
    except Exception:
        logger.exception('Backup failed')
        _audit_failure('system_backup', 'manual', 'Backup failed: unexpected error')
        return error_response('Backup failed', 500)

    _safe_audit_log(
        action='system_backup',
        resource_type='system',
        resource_name=filename,
        details=f'Created backup: {filename}',
        success=True,
    )

    data = {
        'filename': filename,
        'size': _format_size(size),
        'size_bytes': size,
        'download_url': f'/api/v2/system/backup/{filename}/download',
    }
    message = 'Backup created successfully'
    if service.last_export_warnings:
        data['export_warnings'] = list(service.last_export_warnings)
        message = f"{message}. {'; '.join(service.last_export_warnings)}"
    return success_response(data=data, message=message)


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
        shared = shared_store.enabled()
        directory = storage.backup_directory()
        everything = _stored_archives() if shared else _scan_archives(directory)
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
            **({'node': item['node'], 'sha256': item['sha256']} if shared else {}),
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
            'storage': 'database' if shared else 'disk',
        }
    except Exception:
        logger.exception('Failed to list backups')
        return error_response('Failed to list backups', 500)

    if not shared:
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

    if shared_store.enabled():
        response = shared_store.download_response(safe_filename)
        return response if response is not None else error_response('Backup file not found', 404)

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

    if shared_store.enabled():
        try:
            if not shared_store.delete_archives([safe_filename], wait=DELETE_LOCK_WAIT,
                                                purpose='deleting a backup'):
                return error_response('Backup file not found', 404)
        except BackupBusyError as busy:
            logger.info('Backup deletion refused: %s', busy)
            return error_response(str(busy), 409)
    elif backup_file.is_symlink() or not backup_file.is_file():
        return error_response('Backup file not found', 404)
    else:
        failure = _delete_local(backup_file, safe_filename)
        if failure is not None:
            return failure

    _safe_audit_log(
        action='backup_delete',
        resource_type='system',
        resource_name=safe_filename,
        details=f'Deleted backup: {safe_filename}',
        success=True,
    )
    return success_response(message='Backup deleted successfully')


def _delete_local(backup_file, safe_filename):
    """Remove one archive from this node's disk; an error response, or None once it is gone."""
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
    return None


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
        if shared_store.enabled():
            deleted_names = _bulk_delete_stored(filenames, counts)
        else:
            _bulk_delete_local(filenames, counts, deleted_names, seen)
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


def _bulk_delete_stored(filenames, counts) -> list:
    """HA: delete the named archives of the database in one transaction; returns the names deleted."""
    names = []
    for raw in filenames:
        try:
            _path, name = storage.resolve_archive(raw)
        except Exception:
            counts['invalid'] += 1
            continue
        if name not in names:
            names.append(name)
    deleted = shared_store.delete_archives(names, wait=BULK_DELETE_LOCK_WAIT,
                                           purpose='deleting backups')
    counts['deleted'] = len(deleted)
    counts['missing'] = len(names) - len(deleted)
    return [name for name in names if name in set(deleted)]


def _bulk_delete_local(filenames, counts, deleted_names, seen) -> None:
    """Delete local archives under one hold of the backup lock."""
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
@reject_in_ha()
def restore_backup():
    """Restore an uploaded archive, replacing (default) or merging.

    Only restore archives you produced yourself: a replacing restore puts back
    users, private keys and secrets exactly as the archive holds them.
    """
    # Before anything reads the body: this route's ceiling, not the global one.
    # The archive's version decides the rest, once the upload is spooled.
    request.max_content_length = storage.restore_body_limit()
    if 'file' not in request.files:
        record_request_refusal('upload', 'no file provided')
        return error_response('No backup file provided', 400)
    file = request.files['file']
    if not file.filename:
        record_request_refusal('upload', 'no file selected')
        return error_response('No file selected', 400)
    audited_name = client_filename(file.filename)  # the client's, never trusted as is

    password = request.form.get('password')
    if not password:
        record_request_refusal(audited_name, 'password missing')
        return error_response('Backup password required', 400)

    mode = (request.form.get('mode') or 'replace').strip().lower()
    if mode not in ('replace', 'merge'):
        record_request_refusal(audited_name, 'unknown mode')
        return error_response("mode must be 'replace' or 'merge'", 400)

    try:
        try:
            validate_upload_name(file, BACKUP_EXTENSIONS)
        except ValueError as exc:
            logger.warning('Backup upload refused: %s', exc)
            record_request_refusal(audited_name, 'invalid file name')
            return error_response('Invalid backup file', 400)
        too_large = storage.restore_size_refusal(file.stream)
        if too_large:
            status, message = too_large
            logger.warning('Backup upload refused: %s', message)
            record_request_refusal(audited_name, 'file too large')
            return error_response(message, status)

        # A restore landing before a pending backend switch is lost at restart.
        pending = pending_switch_refusal()
        if pending:
            record_request_refusal(audited_name, 'a backend switch is pending')
            return error_response(pending, 409)

        try:
            # The backup lock too: an archive written meanwhile would read half of the restore
            with database_migration_lock(purpose='the restore'), \
                    backup_operation_lock(purpose='the restore'):
                results = BackupService().restore_backup_from_stream(
                    file.stream, password, mode=mode)
        except MigrationBusyError as busy:
            record_request_refusal(audited_name, 'a backend migration or another restore is running')
            return error_response(
                f'{busy} A backend migration or another restore is still '
                'running.', 409)
        except BackupBusyError as busy:
            record_request_refusal(audited_name, 'a backup or another restore is running')
            return error_response(f'{busy} Retry once it has finished.', 409)

        try:
            carried = bool((results or {}).get('sections_carried'))
            _safe_audit_log(
                action='system_restore',
                resource_type='system',
                resource_name=audited_name,
                details=safe_restore_audit_details(audited_name, results),
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
        except Exception:
            # The restore is committed and already audited as a success: no second, contradicting line
            logger.exception('Restore: finishing after the restore failed')
            return error_response(
                'Backup restored, but finishing the restore failed. '
                'Restart the application before using it.', 500)
    except FipsRestricted:
        _audit_failure('system_restore', audited_name, 'Restore refused: not allowed in FIPS mode')
        raise  # the application maps it to its problem type, message unchanged
    except BackupDecryptionError:
        logger.warning('Restore refused: the backup could not be decrypted')
        _audit_failure('system_restore', audited_name, 'Restore refused: wrong password or invalid backup')
        return error_response(
            'Wrong backup password, or the file is not a valid backup', 400)
    except (ContainerError, BackupSchemaError, RestoreValidationError) as e:
        logger.warning('Restore refused: %s', e)
        _audit_failure('system_restore', audited_name, 'Restore refused: the archive failed validation')
        return error_response(str(e), 400)
    except OverflowError as e:
        logger.warning('Restore refused: a value is out of range (%s)', e)
        _audit_failure('system_restore', audited_name, 'Restore refused: a value is out of range')
        return error_response(
            'The archive carries a numeric value this database cannot '
            'store; the file is not a valid backup', 400)
    except ValueError as e:
        logger.warning('Restore refused: %s', e)
        _audit_failure('system_restore', audited_name, 'Restore refused: the archive could not be read')
        return error_response(f'The archive could not be read: {e}', 400)
    except Exception:
        logger.exception('Restore failed')
        _audit_failure('system_restore', audited_name, 'Restore failed: unexpected error')
        return error_response('Restore failed', 500)
