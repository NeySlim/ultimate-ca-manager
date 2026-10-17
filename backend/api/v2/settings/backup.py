"""
Settings - Backup management + schedule + history routes
"""

from flask import request, send_file
from auth.unified import require_auth
from utils.pagination import parse_request_pagination
from utils.response import success_response, error_response, no_content_response
from models import db, SystemConfig
from services.audit_service import AuditService
from services.backup import storage
from fips_mode import FipsRestricted
from services.backup.decrypt_mixin import BackupDecryptionError
from services.backup.locking import BackupBusyError, backup_operation_lock
from services.backup.restore.plan import RestoreValidationError
from services.backup.restore_completion import (
    record_restore, request_restart, restore_message)
from services.database_admin.lock import (
    MigrationBusyError,
    database_migration_lock,
    pending_switch_refusal,
)
from services.backup.settings_contract import (
    BackupSettingError,
    validate_backup_kdf,
    validate_backup_password,
    validate_frequency,
    validate_retention_days,
)
from services.backup.backup_service import check_backup_kdf
from services.backup_service import (
    BackupService,
    BackupExportError,
    BackupPasswordError,
    BackupSchemaError,
    BackupValidationError,
    ContainerError,
)
import logging
import secrets

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
    """Create backup now.

    The archive is produced, named, published and proven by the same code as
    POST /api/v2/system/backup: two entry points, one implementation, so an
    instance cannot end up with two sets of archives under two naming schemes.
    What is particular to this route is the password it generates for a caller
    that did not bring one, which it returns once.
    """
    data = request.json or {}
    password = data.get('password')
    generated_password = False

    # Generate secure random password if not provided
    if not password:
        password = secrets.token_urlsafe(16)  # 128-bit entropy
        generated_password = True

    # The generated password goes through the rule too: it is the password the
    # administrator will have to type back to restore.
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
    except BackupPasswordError as e:
        return error_response(str(e), 400)
    except BackupExportError as e:
        logger.error(f"Settings backup aborted: {e}")
        return error_response(f'Backup aborted: {e}', 500)
    except BackupValidationError as e:
        logger.error(f"Settings backup written but not validated: {e}")
        return error_response(f'Backup could not be validated: {e}', 500)
    except Exception as e:
        logger.error(f"Settings backup failed: {e}")
        return error_response('Backup failed', 500)

    AuditService.log_action(
        action='system_backup',
        resource_type='system',
        resource_name=filename,
        details=f'Created backup: {filename}',
        success=True
    )

    response_data = {
        'filename': filename,
        # `size` stays the byte count this route has always returned; both
        # families also answer `size_bytes`, which means the same thing on
        # either of them. The absolute path is gone: where the instance keeps
        # its archives is not the caller's business.
        'size': len(backup_bytes),
        'size_bytes': len(backup_bytes),
        'download_url': f'/api/v2/settings/backup/{filename}/download',
    }

    # Include generated password in response so user can save it
    if generated_password:
        response_data['password'] = password
        response_data['password_generated'] = True

    return success_response(
        data=response_data,
        message='Backup created successfully' + (' - SAVE THE PASSWORD!' if generated_password else '')
    )


@bp.route('/api/v2/settings/backup/restore', methods=['POST'])
@require_auth(['admin:system'])
def restore_backup():
    """Restore from backup file.

    A restore replaces this instance with the archive: the rows a section held
    when the backup was taken are what it holds afterwards, users, private
    keys and secrets included. Only restore backups you produced yourself (see
    the Backup & Restore wiki page for the trust model). The system endpoint
    takes a `mode` for the rare case of merging an archive into a live
    instance; this one always replaces.
    """
    if 'file' not in request.files:
        return error_response('No backup file provided', 400)

    file = request.files['file']
    if file.filename == '':
        return error_response('No file selected', 400)

    password = request.form.get('password')
    if not password:
        return error_response('Backup password required', 400)

    # This route always replaces, as the docstring says. Accepting a `mode`
    # and ignoring it meant the same request merged an archive into a live
    # instance from one page and overwrote the whole database from the other,
    # with nothing said either way.
    mode = (request.form.get('mode') or 'replace').strip().lower()
    if mode != 'replace':
        return error_response(
            "This endpoint always replaces the instance with the archive. Use "
            "POST /api/v2/system/restore with mode=merge to add an archive's "
            "rows to a live instance.", 400)

    try:
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

        # Between a backend switch being written and the service restarting
        # onto it, this instance still runs on the backend being left behind:
        # a restore landing here is discarded by the restart. The system route
        # has always refused it; which of the two an operator reached decided
        # whether their restore survived.
        pending = pending_switch_refusal()
        if pending:
            return error_response(pending, 409)

        # A restore rewrites the whole database, which is the largest
        # concurrent write a migration could be reading through. Both take the
        # same lock so one never sees the other half-done.
        service = BackupService()
        try:
            with database_migration_lock(purpose='the restore'):
                results = service.restore_backup(backup_bytes, password)
        except MigrationBusyError as busy:
            return error_response(
                f"{busy} A backend migration or another restore is still "
                "running.", 409)

        # Recorded before the archive is judged empty or not, as the system
        # route does: a file that restored nothing was still uploaded and
        # still deserves a line, and returning first meant it left no trace
        # on one page and a trace on the other. What the line says depends on
        # which of the two happened, because an entry reading "Restored from
        # backup" beside a response reading "nothing was restored" is a trail
        # that has to be argued with.
        _carried = bool((results or {}).get('sections_carried'))
        record_restore(
            action='system_restore',
            resource_type='system',
            resource_name=file.filename,
            details=(f'Restored from backup: {file.filename}' if _carried else
                     f'Backup carried no data section, nothing was restored: '
                     f'{file.filename}'),
            success=True
        )

        # An archive that carried no section changed nothing, so there is
        # nothing to invalidate and no reason to sign everyone out and ask for
        # a restart. Announced as a restore, it revoked every session that was
        # open, the caller's included, for a file that touched not one row.
        if not _carried:
            logger.warning('Restore: the archive carried no data section')
            return success_response(
                data=results,
                message=('The archive carried no data: nothing was restored, '
                         'no session was revoked and no restart is needed.'),
            )

        from services.backup.restore.invalidate import invalidate_after_restore
        try:
            invalidate_after_restore()
        except Exception:
            logger.exception("Restore: sessions could not be revoked")
            return error_response(
                'Backup restored, but the sessions opened before it could not '
                'be revoked. Restart the application before using it.', 500)

        # The restart is part of the restore, not homework for the operator:
        # the workers hold the authorities, the keys and the identities the
        # restore has just replaced. The System route had always asked for it
        # while this one told the operator to do it themselves, so the same
        # archive left the service running or not depending on the page.
        restart_ok, restart_detail = request_restart()
        results['restart_requested'] = restart_ok
        results['restart_detail'] = restart_detail

        # And the whole of `results`, not a two-key summary: what the archive
        # said about itself, the sections this version does not restore
        # included, reached a client from one page and not the other.
        results['filename'] = file.filename
        return success_response(
            data=results,
            message=restore_message(results),
        )
    except FipsRestricted:
        raise  # the app maps it to its problem type, message unchanged
    except BackupDecryptionError:
        logger.warning("Settings restore refused: the backup could not be decrypted")
        return error_response(
            'Wrong backup password, or the file is not a valid backup', 400)
    except (ContainerError, BackupSchemaError, RestoreValidationError) as e:
        # The same refusals as the System route, answered the same way: a
        # malformed archive used to be a 400 on one and a 500 "Restore
        # failed" on the other, so which endpoint an operator had reached
        # decided what they were told about their own file.
        logger.warning(f"Settings restore refused: {e}")
        return error_response(str(e), 400)
    except OverflowError as e:
        logger.warning(f"Settings restore refused: a value is out of range ({e})")
        return error_response(
            'The archive carries a numeric value this database cannot '
            'store; the file is not a valid backup', 400)
    except ValueError as e:
        logger.warning(f"Settings restore validation error: {e}")
        return error_response(f'The archive could not be read: {e}', 400)
    except Exception as e:
        logger.error(f"Settings restore failed: {e}")
        return error_response('Restore failed', 500)


@bp.route('/api/v2/settings/backup/<filename>/download', methods=['GET'])
@require_auth(['admin:system'])
def download_backup(filename):
    """Download backup file.

    The name is resolved by the storage module, the one implementation the
    System route uses as well: a traversal, a name secure_filename() would
    have quietly turned into a different valid one, an extension this service
    never writes and a symlink are refused the same way on both.
    """
    try:
        backup_file, safe_filename = storage.resolve_archive(filename)
    except ValueError:
        return error_response('Invalid backup filename', 400)
    except PermissionError:
        return error_response('Access denied', 403)

    if not backup_file.is_file() or backup_file.is_symlink():
        return error_response('Backup file not found', 404)

    return send_file(
        backup_file,
        as_attachment=True,
        download_name=safe_filename,
        mimetype='application/octet-stream',
        conditional=True,
    )


@bp.route('/api/v2/settings/backup/<filename>', methods=['DELETE'])
@require_auth(['admin:system'])
def delete_backup(filename):
    """Delete backup file.

    Same resolution as the System route. Deleting stays idempotent here — a
    name that is already gone answers 204 — which is the contract this route's
    callers have always had.
    """
    try:
        backup_file, safe_filename = storage.resolve_archive(filename)
    except ValueError:
        return error_response('Invalid backup filename', 400)
    except PermissionError:
        return error_response('Access denied', 403)

    try:
        # Same lock as every other operation on this directory: a deletion
        # while an archive is being written would race the catalogue that
        # vouches for it.
        with backup_operation_lock(timeout=15, purpose='deleting a backup'):
            if backup_file.is_file() and not backup_file.is_symlink():
                backup_file.unlink()
    except BackupBusyError as busy:
        logger.info("Delete refused: %s", busy)
        return error_response(str(busy), 409)
    except OSError:
        logger.exception("Failed to delete backup: %s", safe_filename)
        return error_response('Failed to delete backup', 500)

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
    retention_days→backup_retention_days, kdf→backup_kdf.
    """
    from . import set_config
    from services.backup.schedule import get_schedule
    data = request.json
    if not data:
        return error_response('No data provided', 400)

    # One contract, shared with PATCH /api/v2/settings/general: the two routes
    # write the same three rows, so a value one of them refuses cannot be
    # stored through the other.
    try:
        if 'frequency' in data:
            data['frequency'] = validate_frequency(data['frequency'], 'frequency')
        if 'retention_days' in data:
            data['retention_days'] = validate_retention_days(
                data['retention_days'], 'retention_days')
        if 'kdf' in data:
            data['kdf'] = validate_backup_kdf(data['kdf'], 'kdf')
    except BackupSettingError as e:
        return error_response(str(e), 400)

    if 'enabled' in data:
        set_config('auto_backup_enabled', 'true' if data['enabled'] else 'false')
    if 'frequency' in data:
        set_config('backup_frequency', data['frequency'])
    if 'retention_days' in data:
        set_config('backup_retention_days', str(data['retention_days']))
    if 'kdf' in data:
        set_config('backup_kdf', data['kdf'])

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
@require_auth(['admin:system'])
def get_backup_history():
    """Get backup history (actual backup files on disk)"""
    from services.backup.schedule import list_backups
    page, per_page = parse_request_pagination(default_per_page=20)

    all_backups = list_backups()
    total = len(all_backups)
    start = (page - 1) * per_page
    items = all_backups[start:start + per_page]

    return success_response(
        data=items,
        meta={'total': total, 'page': page, 'per_page': per_page}
    )
