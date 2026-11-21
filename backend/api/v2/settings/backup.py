"""
Settings - Backup management + schedule + history routes
"""

from flask import request, send_file
from auth.unified import require_auth
from services import cluster_maintenance
from utils.sanitize import client_filename
from utils.pagination import parse_request_pagination
from utils.response import success_response, error_response, no_content_response
from models import db
from services.audit_service import AuditService
from services.backup import shared_store, storage
from fips_mode import FipsRestricted
from services.backup.decrypt_mixin import BackupDecryptionError
from services.backup.locking import BackupBusyError, backup_operation_lock
from services.backup.restore.plan import RestoreValidationError
from services.backup.restore_completion import (
    record_failure, record_request_refusal, preflight_v4, start_restore)
from services.database_admin.lock import (
    pending_switch_refusal,
)
from services.backup.settings_contract import (
    BackupSettingError,
    validate_backup_kdf,
    validate_backup_password,
    validate_frequency,
    validate_max_total_mb,
    validate_retention_days,
)
from services.backup.backup_service import check_backup_kdf
from services.backup_service import (
    BackupSchemaError,
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
    # The gate lets this start through: a maintenance refuses it before any check or audit write
    from api.v2.system.jobs import suspended_response
    from services.cluster_maintenance import blocks_writes
    if blocks_writes():
        return suspended_response()
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
        record_failure('system_backup', 'manual', 'Backup refused: password rejected')
        return error_response(str(e), 400)

    kdf = data.get('kdf')
    try:
        check_backup_kdf(kdf)
    except FipsRestricted:
        record_failure('system_backup', 'manual', 'Backup refused: not allowed in FIPS mode')
        raise
    except ValueError as e:
        record_failure('system_backup', 'manual', 'Backup refused: key derivation not accepted')
        return error_response(str(e), 400)

    # The generated password is given in this answer only: the job holds it encrypted
    from api.v2.system.backup import start_backup_job
    from services.jobs import backup as backup_job
    extra = {'password': password, 'password_generated': True} if generated_password else None
    return start_backup_job(backup_job.params_of(backup_job.ROUTE_SETTINGS, kdf, generated_password),
                            password, extra)


@bp.route('/api/v2/settings/backup/restore', methods=['POST'])
@require_auth(['admin:system'])
def restore_backup():
    """Restore from backup file.

    A restore replaces this instance with the archive: the rows a section held
    when the backup was taken are what it holds afterwards, users, private
    keys and secrets included. Only restore backups you produced yourself (see
    the Backup & Restore wiki page for the trust model). The system endpoint
    takes a `mode` for the rare case of merging an archive into a live
    instance; this one always replaces. It runs as a background job, like the system one.
    """
    # The gate lets this start through: a maintenance or a restore refuses it before any check
    from api.v2.system.jobs import suspended_response
    if cluster_maintenance.blocks_writes():
        return suspended_response()
    # Before anything reads the body: this route's ceiling, not the global one.
    # The archive's version decides the rest, once the upload is spooled.
    request.max_content_length = storage.restore_body_limit()
    if 'file' not in request.files:
        record_request_refusal('upload', 'no file provided')
        return error_response('No backup file provided', 400)

    file = request.files['file']
    if file.filename == '':
        record_request_refusal('upload', 'no file selected')
        return error_response('No file selected', 400)
    audited_name = client_filename(file.filename)  # the client's, never trusted as is

    password = request.form.get('password')
    if not password:
        record_request_refusal(audited_name, 'password missing')
        return error_response('Backup password required', 400)

    # This route always replaces, as the docstring says. Accepting a `mode`
    # and ignoring it meant the same request merged an archive into a live
    # instance from one page and overwrote the whole database from the other,
    # with nothing said either way.
    mode = (request.form.get('mode') or 'replace').strip().lower()
    if mode != 'replace':
        record_request_refusal(audited_name, 'mode not allowed here')
        return error_response(
            "This endpoint always replaces the instance with the archive. Use "
            "POST /api/v2/system/restore with mode=merge to add an archive's "
            "rows to a live instance.", 400)

    try:
        from utils.file_validation import validate_upload_name, BACKUP_EXTENSIONS

        # The upload is read from its spool, never whole into memory: a v4
        # archive is restored chunk by chunk, an older one is bounded first.
        try:
            validate_upload_name(file, BACKUP_EXTENSIONS)
        except ValueError as exc:
            logger.warning(f"Backup upload validation error: {exc}")
            record_request_refusal(audited_name, 'invalid file name')
            return error_response('Invalid backup file', 400)
        too_large = storage.restore_size_refusal(file.stream)
        if too_large:
            status, message = too_large
            logger.warning('Backup upload refused: %s', message)
            record_request_refusal(audited_name, 'file too large')
            return error_response(message, status)

        # Between a backend switch being written and the service restarting
        # onto it, this instance still runs on the backend being left behind:
        # a restore landing here is discarded by the restart. The system route
        # has always refused it; which of the two an operator reached decided
        # whether their restore survived.
        pending = pending_switch_refusal()
        if pending:
            record_request_refusal(audited_name, 'a backend switch is pending')
            return error_response(pending, 409)

        # A v4's password is checked here; the job, run by the scheduler process, does the rest
        preflight_v4(file.stream, password)
        return start_restore(file, password, audited_name, mode)
    except FipsRestricted:
        record_failure('system_restore', audited_name, 'Restore refused: not allowed in FIPS mode')
        raise  # the app maps it to its problem type, message unchanged
    except BackupDecryptionError:
        logger.warning("Settings restore refused: the backup could not be decrypted")
        record_failure('system_restore', audited_name, 'Restore refused: wrong password or invalid backup')
        return error_response(
            'Wrong backup password, or the file is not a valid backup', 400)
    except (ContainerError, BackupSchemaError, RestoreValidationError) as e:
        # The same refusals as the System route, answered the same way: a
        # malformed archive used to be a 400 on one and a 500 "Restore
        # failed" on the other, so which endpoint an operator had reached
        # decided what they were told about their own file.
        logger.warning(f"Settings restore refused: {e}")
        record_failure('system_restore', audited_name, 'Restore refused: the archive failed validation')
        return error_response(str(e), 400)
    except OverflowError as e:
        logger.warning(f"Settings restore refused: a value is out of range ({e})")
        record_failure('system_restore', audited_name, 'Restore refused: a value is out of range')
        return error_response(
            'The archive carries a numeric value this database cannot '
            'store; the file is not a valid backup', 400)
    except ValueError as e:
        logger.warning(f"Settings restore validation error: {e}")
        record_failure('system_restore', audited_name, 'Restore refused: the archive could not be read')
        return error_response(f'The archive could not be read: {e}', 400)
    except Exception as e:
        logger.error(f"Settings restore failed: {e}")
        record_failure('system_restore', audited_name, 'Restore failed: unexpected error')
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
        if shared_store.enabled():
            shared_store.delete_archives([safe_filename], wait=15, purpose='deleting a backup')
        else:
            with backup_operation_lock(timeout=15, purpose='deleting a backup'):
                if backup_file.is_file() and not backup_file.is_symlink():
                    backup_file.unlink()
    except BackupBusyError as busy:
        logger.info("Delete refused: %s", busy)
        return error_response(str(busy), 409)
    except OSError:
        logger.exception('Failed to delete backup: %s', safe_filename)
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
    retention_days→backup_retention_days, max_total_mb→backup_max_total_mb,
    kdf→backup_kdf.
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
        if 'max_total_mb' in data:
            data['max_total_mb'] = validate_max_total_mb(
                data['max_total_mb'], 'max_total_mb')
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
    if 'max_total_mb' in data:
        set_config('backup_max_total_mb', str(data['max_total_mb']))
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
        details="Backup schedule updated" + (
            f" (max_total_mb={data['max_total_mb']})" if 'max_total_mb' in data else ''),
        success=True,
    )
    return success_response(data=get_schedule(),
                            message='Backup schedule updated successfully')


@bp.route('/api/v2/settings/backup/history', methods=['GET'])
@require_auth(['admin:system'])
def get_backup_history():
    """Get backup history: the archives on disk, or in HA those of the database."""
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
