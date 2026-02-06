"""
Audit Log Retention Service
Configurable retention policy with scheduled cleanup
"""
import logging
from datetime import datetime, timedelta
from typing import Dict, Any, Optional
from models import db, AuditLog

logger = logging.getLogger(__name__)


class RetentionPolicy:
    """Configurable audit log retention policy"""
    
    # Default retention settings (days)
    DEFAULT_RETENTION_DAYS = 90
    MIN_RETENTION_DAYS = 7
    MAX_RETENTION_DAYS = 365 * 5  # 5 years
    
    # Singleton settings storage (in-memory, could be extended to DB)
    _settings: Dict[str, Any] = {
        'retention_days': 90,
        'auto_cleanup': True,
        'archive_before_delete': False,
        'last_cleanup': None,
        'total_deleted': 0
    }
    
    @classmethod
    def get_settings(cls) -> Dict[str, Any]:
        """Get current retention settings"""
        return cls._settings.copy()
    
    @classmethod
    def update_settings(cls, **kwargs) -> Dict[str, Any]:
        """
        Update retention settings
        
        Args:
            retention_days: Number of days to retain logs
            auto_cleanup: Enable automatic cleanup
            archive_before_delete: Archive logs before deletion
        """
        if 'retention_days' in kwargs:
            days = int(kwargs['retention_days'])
            if days < cls.MIN_RETENTION_DAYS:
                days = cls.MIN_RETENTION_DAYS
            elif days > cls.MAX_RETENTION_DAYS:
                days = cls.MAX_RETENTION_DAYS
            cls._settings['retention_days'] = days
        
        if 'auto_cleanup' in kwargs:
            cls._settings['auto_cleanup'] = bool(kwargs['auto_cleanup'])
        
        if 'archive_before_delete' in kwargs:
            cls._settings['archive_before_delete'] = bool(kwargs['archive_before_delete'])
        
        logger.info(f"Retention policy updated: {cls._settings}")
        return cls._settings.copy()
    
    @classmethod
    def get_stats(cls) -> Dict[str, Any]:
        """Get retention statistics"""
        cutoff = datetime.utcnow() - timedelta(days=cls._settings['retention_days'])
        
        total_logs = db.session.query(db.func.count(AuditLog.id)).scalar() or 0
        logs_to_delete = db.session.query(db.func.count(AuditLog.id)).filter(
            AuditLog.timestamp < cutoff
        ).scalar() or 0
        
        oldest_log = db.session.query(db.func.min(AuditLog.timestamp)).scalar()
        newest_log = db.session.query(db.func.max(AuditLog.timestamp)).scalar()
        
        return {
            'retention_days': cls._settings['retention_days'],
            'auto_cleanup': cls._settings['auto_cleanup'],
            'archive_before_delete': cls._settings['archive_before_delete'],
            'total_logs': total_logs,
            'logs_to_delete': logs_to_delete,
            'oldest_log': oldest_log.isoformat() if oldest_log else None,
            'newest_log': newest_log.isoformat() if newest_log else None,
            'last_cleanup': cls._settings['last_cleanup'],
            'total_deleted_lifetime': cls._settings['total_deleted'],
            'cutoff_date': cutoff.isoformat()
        }


def cleanup_audit_logs(retention_days: Optional[int] = None) -> Dict[str, Any]:
    """
    Clean up old audit logs based on retention policy
    
    Args:
        retention_days: Override retention days (uses policy default if None)
        
    Returns:
        Dict with cleanup results
    """
    if retention_days is None:
        retention_days = RetentionPolicy._settings['retention_days']
    
    cutoff = datetime.utcnow() - timedelta(days=retention_days)
    
    try:
        # Count logs to delete
        to_delete = db.session.query(db.func.count(AuditLog.id)).filter(
            AuditLog.timestamp < cutoff
        ).scalar() or 0
        
        if to_delete == 0:
            logger.info("No audit logs to clean up")
            return {
                'deleted': 0,
                'retention_days': retention_days,
                'cutoff_date': cutoff.isoformat(),
                'message': 'No logs older than retention period'
            }
        
        # Delete in batches to avoid long locks
        batch_size = 1000
        total_deleted = 0
        
        while True:
            deleted = db.session.query(AuditLog).filter(
                AuditLog.timestamp < cutoff
            ).limit(batch_size).delete(synchronize_session=False)
            
            db.session.commit()
            total_deleted += deleted
            
            if deleted < batch_size:
                break
        
        # Update stats
        RetentionPolicy._settings['last_cleanup'] = datetime.utcnow().isoformat()
        RetentionPolicy._settings['total_deleted'] += total_deleted
        
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
            'deleted': 0,
            'error': str(e),
            'message': 'Failed to clean up audit logs'
        }


def scheduled_audit_cleanup():
    """Scheduled task for automatic audit log cleanup"""
    if not RetentionPolicy._settings['auto_cleanup']:
        logger.debug("Auto cleanup disabled, skipping")
        return
    
    result = cleanup_audit_logs()
    logger.info(f"Scheduled audit cleanup: {result}")
