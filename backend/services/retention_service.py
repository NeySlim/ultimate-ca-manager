"""
Audit Log Retention Service
Configurable retention policy with scheduled cleanup
"""
import logging
from datetime import datetime, timedelta
from typing import Dict, Any, Optional
from models import db, AuditLog
from utils.datetime_utils import utc_now

logger = logging.getLogger(__name__)

CLEANUP_BATCH_SIZE = 1000


class RetentionSettingError(ValueError):
    """A retention value the policy refuses."""


class RetentionPolicy:
    """Audit log retention, stored in SystemConfig.

    No stored value (or 0) keeps every log: the purge only runs once an
    administrator has chosen a retention.
    """

    CONFIG_KEY = 'audit_retention_days'
    MIN_RETENTION_DAYS = 7
    MAX_RETENTION_DAYS = 365 * 5  # 5 years

    # Run statistics only; the policy itself lives in the database.
    _stats: Dict[str, Any] = {
        'last_cleanup': None,
        'total_deleted': 0
    }

    @classmethod
    def validate_days(cls, value, allow_zero=True, field='retention_days') -> int:
        """Return `value` as a retention in days, or raise RetentionSettingError."""
        try:
            days = int(value)
        except (TypeError, ValueError):
            raise RetentionSettingError(f'{field} must be an integer')
        if days == 0 and allow_zero:
            return 0
        if not cls.MIN_RETENTION_DAYS <= days <= cls.MAX_RETENTION_DAYS:
            raise RetentionSettingError(
                f'{field} must be between {cls.MIN_RETENTION_DAYS} and '
                f'{cls.MAX_RETENTION_DAYS}' + (' (0 keeps logs forever)' if allow_zero else ''))
        return days

    @classmethod
    def get_retention_days(cls) -> int:
        """Configured retention in days, 0 when logs are kept forever."""
        from models import SystemConfig
        row = SystemConfig.query.filter_by(key=cls.CONFIG_KEY).first()
        try:
            return cls.validate_days(row.value) if row and row.value else 0
        except RetentionSettingError:
            logger.warning(f"Ignoring invalid {cls.CONFIG_KEY}={row.value!r}; keeping audit logs")
            return 0

    @classmethod
    def get_settings(cls) -> Dict[str, Any]:
        """Get current retention settings"""
        days = cls.get_retention_days()
        return {
            'retention_days': days,
            'auto_cleanup': days > 0,
            'archive_before_delete': False,
            'last_cleanup': cls._stats['last_cleanup'],
            'total_deleted': cls._stats['total_deleted'],
        }

    @classmethod
    def update_settings(cls, **kwargs) -> Dict[str, Any]:
        """Update the stored retention (`retention_days`, 0 = keep forever).

        `auto_cleanup: false` is the same as 0. Archiving before deletion is
        not implemented and is refused rather than silently ignored.
        """
        from api.v2.settings import set_config
        if kwargs.get('archive_before_delete'):
            raise RetentionSettingError('archive_before_delete is not supported')
        if 'retention_days' in kwargs:
            days = cls.validate_days(kwargs['retention_days'])
        else:
            days = cls.get_retention_days()
        if 'auto_cleanup' in kwargs and not kwargs['auto_cleanup']:
            days = 0
        elif kwargs.get('auto_cleanup') and not days:
            raise RetentionSettingError('auto_cleanup needs a retention_days greater than 0')
        try:
            set_config(cls.CONFIG_KEY, str(days))
            db.session.commit()
        except Exception:
            db.session.rollback()
            raise
        logger.info(f"Audit log retention set to {f'{days} days' if days else 'forever'}")
        return cls.get_settings()

    @classmethod
    def get_stats(cls) -> Dict[str, Any]:
        """Get retention statistics"""
        days = cls.get_retention_days()
        cutoff = utc_now() - timedelta(days=days) if days else None

        total_logs = db.session.query(db.func.count(AuditLog.id)).scalar() or 0
        logs_to_delete = 0
        if cutoff is not None:
            logs_to_delete = db.session.query(db.func.count(AuditLog.id)).filter(
                AuditLog.id < _purge_boundary(cutoff)
            ).scalar() or 0

        oldest_log = db.session.query(db.func.min(AuditLog.timestamp)).scalar()
        newest_log = db.session.query(db.func.max(AuditLog.timestamp)).scalar()

        return {
            'retention_days': days,
            'auto_cleanup': days > 0,
            'archive_before_delete': False,
            'total_logs': total_logs,
            'logs_to_delete': logs_to_delete,
            'oldest_log': oldest_log.isoformat() if oldest_log else None,
            'newest_log': newest_log.isoformat() if newest_log else None,
            'last_cleanup': cls._stats['last_cleanup'],
            'total_deleted_lifetime': cls._stats['total_deleted'],
            'cutoff_date': cutoff.isoformat() if cutoff else None
        }


def _purge_boundary(cutoff) -> int:
    """First id to keep: the oldest row still inside the retention window.

    Purging only ids below it removes a contiguous prefix of the hash chain,
    so what remains still verifies.
    """
    first_kept = db.session.query(db.func.min(AuditLog.id)).filter(
        AuditLog.timestamp >= cutoff
    ).scalar()
    if first_kept is not None:
        return first_kept
    return (db.session.query(db.func.max(AuditLog.id)).scalar() or 0) + 1


def cleanup_audit_logs(retention_days: Optional[int] = None) -> Dict[str, Any]:
    """
    Delete audit logs older than the retention, oldest first, in batches.

    Args:
        retention_days: Override (7 to 1825); the stored policy when None

    Returns:
        Dict with cleanup results
    """
    if retention_days is None:
        retention_days = RetentionPolicy.get_retention_days()
        if not retention_days:
            return {
                'deleted': 0,
                'retention_days': 0,
                'message': 'No audit log retention configured; logs are kept'
            }
    else:
        retention_days = RetentionPolicy.validate_days(retention_days, allow_zero=False)

    cutoff = utc_now() - timedelta(days=retention_days)
    total_deleted = 0

    try:
        boundary = _purge_boundary(cutoff)
        batch_size = CLEANUP_BATCH_SIZE

        while True:
            ids = [row_id for (row_id,) in db.session.query(AuditLog.id).filter(
                AuditLog.id < boundary
            ).order_by(AuditLog.id).limit(batch_size).all()]
            if not ids:
                break
            total_deleted += db.session.query(AuditLog).filter(
                AuditLog.id.in_(ids)
            ).delete(synchronize_session=False)
            db.session.commit()
            if len(ids) < batch_size:
                break

        RetentionPolicy._stats['last_cleanup'] = utc_now().isoformat()
        if total_deleted == 0:
            logger.info("No audit logs to clean up")
        else:
            logger.info(f"Cleaned up {total_deleted} audit logs older than {retention_days} days")

        return {
            'deleted': total_deleted,
            'retention_days': retention_days,
            'cutoff_date': cutoff.isoformat(),
            'message': f'Successfully deleted {total_deleted} old audit logs'
        }

    except Exception as e:
        db.session.rollback()
        logger.error(f"Failed to clean up audit logs: {e}")
        return {
            # Batches committed before the failure are gone for good.
            'deleted': total_deleted,
            'error': str(e),
            'message': 'Failed to clean up audit logs'
        }
    finally:
        RetentionPolicy._stats['total_deleted'] += total_deleted


def scheduled_audit_cleanup():
    """Scheduled task for automatic audit log cleanup (no-op without a retention)"""
    result = cleanup_audit_logs()
    logger.info(f"Scheduled audit cleanup: {result}")
    if result.get('deleted'):
        from services.audit_service import AuditService
        AuditService.log_action(
            action='audit_cleanup',
            resource_type='audit_log',
            details=f"Deleted {result['deleted']} audit logs older than "
                    f"{result.get('retention_days')} days",
            success='error' not in result,
            username='system',
        )
    if 'error' in result:
        # Reported to the scheduler, which otherwise records the run as ok.
        return {'status': 'failed', 'reason': result['error']}
