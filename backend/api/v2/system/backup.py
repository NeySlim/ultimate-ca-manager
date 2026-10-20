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
# PLANB-D.9: à implémenter selon SPEC (constantes de taille et de lot, mise en forme des tailles)
# PLANB-D.9: à implémenter selon SPEC
@bp.route('/api/v2/system/backup', methods=['POST'])
@bp.route('/api/v2/system/backup/create', methods=['POST'])
@require_auth(['admin:system'])
def create_backup():
    raise NotImplementedError('PLANB-D.9')
# PLANB-D.9: à implémenter selon SPEC
@bp.route('/api/v2/system/backups', methods=['GET'])
@bp.route('/api/v2/system/backup/list', methods=['GET'])
@require_auth(['admin:system'])
def list_backups():
    raise NotImplementedError('PLANB-D.9')
# PLANB-D.9: à implémenter selon SPEC
@bp.route('/api/v2/system/backup/<filename>/download', methods=['GET'])
@require_auth(['admin:system'])
def download_backup(filename):
    raise NotImplementedError('PLANB-D.9')
# PLANB-D.9: à implémenter selon SPEC
@bp.route('/api/v2/system/backup/<filename>', methods=['DELETE'])
@require_auth(['admin:system'])
def delete_backup(filename):
    raise NotImplementedError('PLANB-D.9')
# PLANB-D.9: à implémenter selon SPEC
@bp.route('/api/v2/system/backups/bulk-delete', methods=['POST'])
@require_auth(['admin:system'])
def bulk_delete_backups():
    raise NotImplementedError('PLANB-D.9')
# PLANB-D.9: à implémenter selon SPEC
@bp.route('/api/v2/system/backups/run-retention', methods=['POST'])
@require_auth(['admin:system'])
def run_retention_now():
    raise NotImplementedError('PLANB-D.9')
# PLANB-D.9: à implémenter selon SPEC
@bp.route('/api/v2/system/restore', methods=['POST'])
@bp.route('/api/v2/system/backup/restore', methods=['POST'])
@require_auth(['admin:system'])
def restore_backup():
    raise NotImplementedError('PLANB-D.9')
