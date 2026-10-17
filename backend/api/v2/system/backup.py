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
from flask import request, send_file
from auth.unified import require_auth
from utils.response import success_response, error_response
from utils.pagination import parse_request_pagination
from services.audit_service import AuditService
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

_MAX_BACKUP_UPLOAD_SIZE = 100 * 1024 * 1024
_MAX_BULK_DELETE_FILES = 1000


def _human_size(size_bytes: int) -> str:
    """Format a byte count for API responses."""
    if size_bytes > 1024 * 1024:
        return f"{size_bytes / 1024 / 1024:.1f} MB"
    if size_bytes > 1024:
        return f"{size_bytes / 1024:.1f} KB"
    return f"{size_bytes} B"


# Both steps moved to `services/backup/restore_completion.py`, which the
# Settings route calls too: each of them was written on one route and not the
# other, and the difference showed up as a restore that behaved differently
# depending on which page had asked for it.
from services.backup.restore_completion import (
    record_restore as _safe_audit_log,
    request_restart as _request_restart_after_restore,
    restore_message,
)


@bp.route("/api/v2/system/backup", methods=["POST"])
@bp.route("/api/v2/system/backup/create", methods=["POST"])
@require_auth(["admin:system"])
def create_backup():
    """Create an encrypted backup and save it to the configured backup directory."""
    try:
        data = request.get_json(silent=True) or {}
        password = data.get("password")

        if not password:
            return error_response("Password required for encryption", 400)

        try:
            # The one rule, shared with the Settings route and with the
            # password stored for the unattended run (#346)
            validate_backup_password(password)
        except BackupSettingError as exc:
            return error_response(str(exc), 400)

        backup_bytes = BackupService().create_backup(password)

        # Naming, publication and the proof of what was written are the
        # storage module's, for every route that creates an archive.
        _filepath, filename = storage.create_archive(backup_bytes)

        _safe_audit_log(
            action="system_backup",
            resource_type="system",
            resource_name=filename,
            details=f"Created backup: {filename}",
            success=True,
        )

        return success_response(
            message="Backup created successfully",
            data={
                "filename": filename,
                "size": _human_size(len(backup_bytes)),
                "size_bytes": len(backup_bytes),
                "download_url": f"/api/v2/system/backup/{filename}/download",
            },
        )

    except BackupPasswordError as exc:
        return error_response(str(exc), 400)
    except BackupExportError as exc:
        logger.error("Backup aborted: %s", exc)
        return error_response(f"Backup aborted: {exc}", 500)
    except BackupValidationError as exc:
        logger.error("Backup written but not validated: %s", exc)
        return error_response(f"Backup could not be validated: {exc}", 500)
    except ValueError as exc:
        logger.warning("Backup validation error: %s", exc)
        return error_response("Invalid backup parameters", 400)
    except Exception:
        logger.exception("Backup failed")
        return error_response("Backup failed", 500)


@bp.route("/api/v2/system/backups", methods=["GET"])
@bp.route("/api/v2/system/backup/list", methods=["GET"])
@require_auth(["admin:system"])
def list_backups():
    """
    List available backups with pagination, search, sorting, summary, and disk use.

    Query parameters:
      - page
      - per_page (maximum 100)
      - search
      - sort: created_desc, created_asc, size_desc, size_asc,
              name_asc, name_desc
    """
    try:
        backup_dir = storage.backup_directory()
        files = []

        if backup_dir.exists() and backup_dir.is_dir():
            for entry in backup_dir.iterdir():
                if (
                    not storage.is_archive_name(entry.name)
                    or entry.is_symlink()
                    or not entry.is_file()
                ):
                    continue

                try:
                    stat = entry.stat()
                except OSError:
                    continue

                files.append(
                    {
                        "filename": entry.name,
                        "size": _human_size(stat.st_size),
                        "size_bytes": stat.st_size,
                        "mtime": stat.st_mtime,
                        "created_at": datetime.fromtimestamp(
                            stat.st_mtime,
                            tz=timezone.utc,
                        ).strftime("%Y-%m-%d %H:%M:%S UTC"),
                    }
                )

        total_all = len(files)
        total_size_all = sum(item["size_bytes"] for item in files)

        search = (request.args.get("search") or "").strip().lower()
        if search:
            files = [
                item
                for item in files
                if search in item["filename"].lower()
            ]

        filtered_total = len(files)
        filtered_total_size = sum(item["size_bytes"] for item in files)

        sort = request.args.get("sort", "created_desc")
        sorters = {
            "created_desc": (lambda item: item["mtime"], True),
            "created_asc": (lambda item: item["mtime"], False),
            "size_desc": (lambda item: item["size_bytes"], True),
            "size_asc": (lambda item: item["size_bytes"], False),
            "name_asc": (lambda item: item["filename"].lower(), False),
            "name_desc": (lambda item: item["filename"].lower(), True),
        }
        key, reverse = sorters.get(sort, sorters["created_desc"])
        files.sort(key=key, reverse=reverse)

        page, per_page = parse_request_pagination(default_per_page=20)

        start = (page - 1) * per_page
        page_items = files[start:start + per_page]

        for item in page_items:
            item.pop("mtime", None)

        disk = {}
        try:
            import shutil

            disk_usage = shutil.disk_usage(
                backup_dir if backup_dir.exists() else backup_dir.parent
            )
            disk = {
                "disk_total_bytes": disk_usage.total,
                "disk_free_bytes": disk_usage.free,
                "disk_free": _human_size(disk_usage.free),
                "disk_used_pct": (
                    round(disk_usage.used / disk_usage.total * 100, 1)
                    if disk_usage.total
                    else None
                ),
            }
        except OSError:
            logger.warning("Unable to determine backup filesystem disk usage")

        meta = {
            "total": filtered_total,
            "total_all": total_all,
            "total_size_bytes": filtered_total_size,
            "total_size": _human_size(filtered_total_size),
            "total_size_all_bytes": total_size_all,
            "total_size_all": _human_size(total_size_all),
            "page": page,
            "per_page": per_page,
            "pages": max(1, (filtered_total + per_page - 1) // per_page),
            **disk,
        }

        return success_response(data={"items": page_items, "meta": meta})

    except Exception:
        logger.exception("Failed to list backups")
        return error_response("Failed to list backups", 500)


@bp.route("/api/v2/system/backup/<filename>/download", methods=["GET"])
@require_auth(["admin:system"])
def download_backup(filename):
    """Download an existing backup file."""
    try:
        backup_file, safe_filename = storage.resolve_archive(filename)
    except ValueError:
        return error_response("Invalid backup filename", 400)
    except PermissionError:
        return error_response("Access denied", 403)

    if not backup_file.is_file() or backup_file.is_symlink():
        return error_response("Backup file not found", 404)

    return send_file(
        backup_file,
        as_attachment=True,
        download_name=safe_filename,
        mimetype="application/octet-stream",
        conditional=True,
    )


@bp.route("/api/v2/system/backup/<filename>", methods=["DELETE"])
@require_auth(["admin:system"])
def delete_backup(filename):
    """Delete one backup file."""
    try:
        backup_file, safe_filename = storage.resolve_archive(filename)
    except ValueError:
        return error_response("Invalid backup filename", 400)
    except PermissionError:
        return error_response("Access denied", 403)

    try:
        if not backup_file.is_file() or backup_file.is_symlink():
            return error_response("Backup file not found", 404)

        with backup_operation_lock(timeout=15, purpose='deleting a backup'):
            backup_file.unlink()

        _safe_audit_log(
            action="backup_delete",
            resource_type="system",
            resource_name=safe_filename,
            details=f"Deleted backup: {safe_filename}",
            success=True,
        )

        return success_response(message="Backup deleted successfully")

    except OSError:
        logger.exception("Failed to delete backup: %s", safe_filename)
        return error_response("Failed to delete backup", 500)


@bp.route("/api/v2/system/backups/bulk-delete", methods=["POST"])
@require_auth(["admin:system"])
def bulk_delete_backups():
    """Delete several backups at once. Request body: `{"filenames": [...]}`."""
    data = request.get_json(silent=True) or {}
    names = data.get("filenames")

    if not isinstance(names, list) or not names:
        return error_response("filenames must be a non-empty list", 400)

    if len(names) > _MAX_BULK_DELETE_FILES:
        return error_response("Too many files in one request", 400)

    deleted = 0
    missing = 0
    invalid = 0
    failed = 0
    processed_names = set()

    # One lock for the whole batch: a backup being written while this runs is
    # not yet recorded, and retention deciding what to keep at the same moment
    # would be reading a directory changing under it.
    with backup_operation_lock(timeout=30, purpose='deleting backups'):
        for raw_name in names:
            try:
                backup_file, safe_filename = storage.resolve_archive(raw_name)
            except (ValueError, PermissionError):
                invalid += 1
                continue

            # Avoid counting or attempting the same file multiple times.
            if safe_filename in processed_names:
                continue
            processed_names.add(safe_filename)

            try:
                if not backup_file.is_file() or backup_file.is_symlink():
                    missing += 1
                    continue

                backup_file.unlink()
                deleted += 1

            except FileNotFoundError:
                missing += 1
            except OSError:
                logger.exception("Failed to bulk-delete backup: %s", safe_filename)
                failed += 1

    _safe_audit_log(
        action="backup_delete",
        resource_type="system",
        resource_name=f"{deleted} backup(s)",
        details=(
            f"Bulk-deleted {deleted} backup(s); "
            f"{missing} missing, {invalid} invalid, {failed} failed"
        ),
        success=(failed == 0),
    )

    return success_response(
        data={
            "deleted": deleted,
            "missing": missing,
            "invalid": invalid,
            "failed": failed,
        },
        message=f"Deleted {deleted} backup(s)",
    )


@bp.route("/api/v2/system/backups/run-retention", methods=["POST"])
@require_auth(["admin:system"])
def run_retention_now():
    """Apply the configured backup retention policy immediately."""
    try:
        from services.backup.schedule import run_backup_retention

        # Asked for by a person: wait a little for a backup in flight rather
        # than answering "nothing was removed" because something else held
        # the directory.
        removed = run_backup_retention(wait=30)

    except BackupBusyError as busy:
        logger.info("Run retention refused: %s", busy)
        return error_response(str(busy), 409)
    except Exception:
        logger.exception("Run retention failed")
        return error_response("Failed to apply retention", 500)

    _safe_audit_log(
        action="backup_delete",
        resource_type="system",
        resource_name=f"{removed} backup(s)",
        details=f"Applied retention, removed {removed} expired backup(s)",
        success=True,
    )

    return success_response(
        data={"removed": removed},
        message=f"Retention applied: removed {removed} backup(s)",
    )


@bp.route("/api/v2/system/restore", methods=["POST"])
@bp.route("/api/v2/system/backup/restore", methods=["POST"])
@require_auth(["admin:system"])
def restore_backup():
    """Restore system data from an encrypted backup upload."""
    try:
        if "file" not in request.files:
            return error_response("No backup file provided", 400)

        uploaded_file = request.files["file"]
        password = request.form.get("password")

        if not password:
            return error_response("Password required for decryption", 400)

        # No length rule here. This password has to match the one that
        # encrypted the archive, and refusing to try meant an archive made
        # before the rule existed, or by another installation, could not be
        # restored at all. Creating an archive still enforces it, which is
        # where a rule about password strength belongs. The Settings route
        # never had this check, so the same file restored from one page and
        # was refused from the other.
        try:
            backup_bytes, _ = validate_upload(
                uploaded_file,
                BACKUP_EXTENSIONS,
                max_size=_MAX_BACKUP_UPLOAD_SIZE,
            )
        except ValueError as exc:
            logger.warning("Backup upload validation error: %s", exc)
            return error_response("Invalid backup file", 400)

        # A restore replaces the instance with the archive, which is what the
        # documentation has always described; merge is available for the rare
        # case of pulling one archive's rows into a live instance.
        mode = (request.form.get('mode') or 'replace').strip().lower()
        if mode not in ('replace', 'merge'):
            return error_response(
                "mode must be 'replace' (the archive becomes this instance) or "
                "'merge' (the archive is added to it)", 400)

        # Between a backend switch being written and the service restarting
        # onto it, this instance still runs on the backend being left behind:
        # a restore landing here would be discarded by the restart.
        pending = pending_switch_refusal()
        if pending:
            return error_response(pending, 409)

        # A restore rewrites the whole database, which is the largest
        # concurrent write a migration could be reading through. They take
        # the same lock so one never sees the other half-done.
        service = BackupService()
        try:
            with database_migration_lock(purpose='the restore'):
                results = service.restore_backup(
                    backup_bytes, password, mode=mode)
        except MigrationBusyError as busy:
            # The lock is shared with the backend switch, so the holder may
            # be either; the message names what was refused, not what holds it.
            return error_response(
                f"{busy} A backend migration or another restore is still "
                "running.", 409)

        # Same entry as the settings page, down to the archive's name: that
        # name appeared in the ledger from one page and not the other, so
        # which page an operator happened to use decided whether the trail
        # could say which file had been restored. And it says which of the
        # two things happened, rather than announcing a restore beside a
        # response saying nothing was restored.
        _carried = bool((results or {}).get("sections_carried"))
        _safe_audit_log(
            action="system_restore",
            resource_type="system",
            resource_name=uploaded_file.filename,
            details=(f"Restored from backup: {uploaded_file.filename}"
                     if _carried else
                     f"Backup carried no data section, nothing was restored: "
                     f"{uploaded_file.filename}"),
            success=True,
        )

        # An archive that carried no section changed nothing, so there is
        # nothing to invalidate and no reason to sign everyone out and ask
        # for a restart: that used to happen for a file holding metadata
        # alone, announced as a successful restore.
        if not results.get('sections_carried'):
            logger.warning("Restore: the archive carried no data section")
            return success_response(
                data=results,
                message=("The archive carried no data: nothing was restored, "
                         "no session was revoked and no restart is needed."),
            )

        # The data is in. Now the consequences: every session from before the
        # restore is void (the identities are the archive's), the caches hold
        # the PKI that was just replaced, and the workers need to come back on
        # the restored state.
        from services.backup.restore.invalidate import invalidate_after_restore
        try:
            results['invalidated'] = invalidate_after_restore()
        except Exception:
            logger.exception("Restore: sessions could not be revoked")
            return error_response(
                "Backup restored, but the sessions opened before it could not "
                "be revoked. Restart UCM before using it.", 500)

        restart_ok, restart_message = _request_restart_after_restore()
        results['restart_requested'] = restart_ok
        results['restart_detail'] = restart_message

        return success_response(
            message=restore_message(results),
            data=results,
        )

    except FipsRestricted:
        raise  # the app maps it to its problem type, message unchanged
    except BackupDecryptionError:
        logger.warning("Restore refused: the backup could not be decrypted")
        return error_response("Wrong backup password, or the file is not a valid backup", 400)
    except (ContainerError, BackupSchemaError, RestoreValidationError) as exc:
        # These messages are ours, they name what the archive got wrong (an
        # unreadable schema, a KDF profile out of range, a section short of
        # its count, a section that is not the shape it should be) and say
        # nothing about its contents. Answering "invalid restore parameters"
        # left an administrator holding an archive from a newer UCM, or one
        # with a malformed section, no way to know which it was.
        logger.warning("Restore refused: %s", exc)
        return error_response(str(exc), 400)
    except OverflowError as exc:
        # A number the database cannot hold. It is the archive's fault, not
        # ours, and a 500 with a traceback is the wrong way to say so.
        logger.warning("Restore refused: a value is out of range (%s)", exc)
        return error_response(
            "The archive carries a numeric value this database cannot "
            "store; the file is not a valid backup", 400)
    except ValueError as exc:
        logger.warning("Restore validation error: %s", exc)
        return error_response(f"The archive could not be read: {exc}", 400)
    except Exception:
        logger.exception("Restore failed")
        return error_response("Restore failed", 500)