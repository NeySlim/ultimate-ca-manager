"""Scheduled backup support.

Runs unattended encrypted backups when due, applies retention, and lists
backup history from disk.

The source of truth is the General-settings keys the UI actually writes:
``auto_backup_enabled``, ``backup_frequency`` (daily/weekly/monthly),
``backup_retention_days`` and ``backup_password``. There is no time-of-day in
the UI, so cadence is driven by a stored ``backup.last_run`` timestamp.
"""
import os
import glob
import logging
from datetime import datetime, timezone

from models import db, SystemConfig
from config.settings import Config
from utils.datetime_utils import utc_now, utc_isoformat

logger = logging.getLogger(__name__)

_BACKUP_GLOB = 'ucm_backup_*.ucmbkp'
_LAST_RUN_KEY = 'backup.last_run'
_VALID_FREQUENCIES = ('daily', 'weekly', 'monthly')
_PERIOD_SECONDS = {'daily': 86400, 'weekly': 604800, 'monthly': 2592000}


def _get(key, default=None):
    cfg = SystemConfig.query.filter_by(key=key).first()
    return cfg.value if cfg and cfg.value is not None else default


def get_schedule() -> dict:
    """Return the effective backup schedule (from General settings)."""
    freq = _get('backup_frequency', 'daily')
    if freq not in _VALID_FREQUENCIES:
        freq = 'daily'
    try:
        retention = int(_get('backup_retention_days', '30'))
    except (ValueError, TypeError):
        retention = 30
    return {
        'enabled': _get('auto_backup_enabled', 'false') == 'true',
        'frequency': freq,
        'retention_days': retention,
        'last_run': _get(_LAST_RUN_KEY),
        'password_set': bool(_get('backup_password')),
    }


def _get_backup_password() -> str:
    """Return the decrypted configured backup password, or '' if unset."""
    val = _get('backup_password')
    if not val:
        return ''
    try:
        from utils.encryption import decrypt_if_needed
        return decrypt_if_needed(val)
    except Exception:
        return val


def list_backups() -> list[dict]:
    """List backup files on disk, newest first."""
    backups = []
    try:
        for path in glob.glob(os.path.join(str(Config.BACKUP_DIR), _BACKUP_GLOB)):
            try:
                st = os.stat(path)
            except OSError:
                continue
            backups.append({
                'filename': os.path.basename(path),
                'size': st.st_size,
                'created_at': utc_isoformat(datetime.fromtimestamp(st.st_mtime, timezone.utc)),
            })
    except Exception as e:
        logger.error(f"Failed to list backups: {e}")
    backups.sort(key=lambda b: b['created_at'] or '', reverse=True)
    return backups


def _apply_retention(retention_days: int) -> int:
    """Delete backup files older than retention_days. Returns count removed."""
    if not retention_days or retention_days < 1:
        return 0
    cutoff = utc_now().timestamp() - retention_days * 86400
    removed = 0
    for path in glob.glob(os.path.join(str(Config.BACKUP_DIR), _BACKUP_GLOB)):
        try:
            if os.stat(path).st_mtime < cutoff:
                os.unlink(path)
                removed += 1
        except OSError:
            continue
    if removed:
        logger.info(f"Backup retention removed {removed} expired backup(s)")
    return removed


def run_backup_retention() -> int:
    """Apply backup retention independently of the scheduled-backup run.

    Registered as its own daily scheduler task so retention is enforced even when
    automatic backups are disabled (manual backups would otherwise accumulate
    forever). Honours `backup_retention_days` (0 / unset → no pruning).
    """
    try:
        retention = int(_get('backup_retention_days', '30'))
    except (ValueError, TypeError):
        retention = 30
    return _apply_retention(retention)


def _record_last_run(ts: datetime) -> None:
    cfg = SystemConfig.query.filter_by(key=_LAST_RUN_KEY).first()
    if cfg:
        cfg.value = utc_isoformat(ts)
    else:
        db.session.add(SystemConfig(key=_LAST_RUN_KEY, value=utc_isoformat(ts)))
    try:
        db.session.commit()
    except Exception:
        db.session.rollback()


def _is_due(sched: dict, now: datetime) -> bool:
    last_run = sched.get('last_run')
    if not last_run:
        return True  # never run → run now
    try:
        prev = datetime.fromisoformat(last_run.replace('Z', '+00:00'))
    except (ValueError, AttributeError):
        return True
    # Normalise to naive UTC to match utc_now() (which is naive UTC)
    if prev.tzinfo is not None:
        prev = prev.astimezone(timezone.utc).replace(tzinfo=None)
    now_naive = now.replace(tzinfo=None) if now.tzinfo is not None else now
    period = _PERIOD_SECONDS.get(sched.get('frequency', 'daily'), 86400)
    # small slack so a ~daily timer doesn't drift a day each run
    return (now_naive - prev).total_seconds() >= period - 300


def run_scheduled_backup():
    """Scheduler task — creates an encrypted backup when one is due."""
    sched = get_schedule()
    if not sched.get('enabled'):
        return

    now = utc_now()
    if not _is_due(sched, now):
        return

    password = _get_backup_password()
    if not password or len(password) < 12:
        logger.warning(
            "Scheduled backup skipped: no valid backup password configured "
            "(set a 12+ char password under Settings > Backup)."
        )
        return

    try:
        from services.backup_service import BackupService
        backup_bytes = BackupService().create_backup(password)

        os.makedirs(str(Config.BACKUP_DIR), exist_ok=True)
        filename = f"ucm_backup_{now.strftime('%Y%m%d_%H%M%S')}.ucmbkp"
        filepath = os.path.join(str(Config.BACKUP_DIR), filename)
        with open(filepath, 'wb') as f:
            f.write(backup_bytes)
        try:
            os.chmod(filepath, 0o600)
        except OSError:
            pass

        logger.info(f"Scheduled backup created: {filename} ({len(backup_bytes)} bytes)")
        try:
            from services.audit_service import AuditService
            AuditService.log_action(
                action='system_backup', resource_type='system',
                resource_name=filename, details=f'Scheduled backup: {filename}',
                success=True, username='system',
            )
        except Exception:
            pass

        _apply_retention(sched.get('retention_days', 30))
        _record_last_run(now)
    except Exception as e:
        logger.error(f"Scheduled backup failed: {e}", exc_info=True)
        # A failure that only a log line reports is a backup nobody has:
        # the audit trail records it, as the successes are recorded
        try:
            from services.audit_service import AuditService
            AuditService.log_action(
                action='system_backup', resource_type='system',
                resource_name='scheduled', details=f'Scheduled backup failed: {e}',
                success=False, username='system',
            )
        except Exception:
            pass
