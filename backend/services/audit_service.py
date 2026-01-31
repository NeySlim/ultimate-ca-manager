"""
Audit Logging Service
Centralized audit logging for all user actions
"""
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List
from flask import request, g
from models import db, AuditLog
import logging
import json

logger = logging.getLogger(__name__)


class AuditService:
    """Centralized audit logging service"""
    
    # Action categories for filtering
    CATEGORIES = {
        'auth': ['login_success', 'login_failure', 'logout', 'session_expired', 'mfa_enable', 'mfa_disable', 'password_change'],
        'users': ['user_create', 'user_update', 'user_delete', 'role_change', 'user_activate', 'user_deactivate'],
        'certificates': ['cert_issue', 'cert_revoke', 'cert_renew', 'cert_export', 'cert_delete'],
        'cas': ['ca_create', 'ca_update', 'ca_delete', 'ca_import', 'ca_export'],
        'csrs': ['csr_upload', 'csr_sign', 'csr_reject', 'csr_delete'],
        'settings': ['settings_update', 'backup_create', 'backup_restore', 'backup_delete'],
        'api_keys': ['api_key_create', 'api_key_revoke', 'api_key_delete'],
        'security': ['permission_denied', 'invalid_token', 'rate_limited', 'suspicious_activity'],
    }
    
    @staticmethod
    def log_action(
        action: str,
        resource_type: Optional[str] = None,
        resource_id: Optional[str] = None,
        resource_name: Optional[str] = None,
        details: Optional[str] = None,
        success: bool = True,
        username: Optional[str] = None,
        user_id: Optional[int] = None
    ) -> AuditLog:
        """
        Log an audit action
        
        Args:
            action: Action type (e.g., 'login_success', 'cert_issue')
            resource_type: Type of resource (e.g., 'certificate', 'user')
            resource_id: ID of affected resource
            resource_name: Human-readable name (e.g., cert CN, user name, CA name)
            details: Human-readable description
            success: Whether action succeeded
            username: Username (auto-detected if not provided)
            user_id: User ID (auto-detected if not provided)
            
        Returns:
            Created AuditLog entry
        """
        try:
            # Auto-detect user info from Flask context
            if username is None and hasattr(g, 'current_user') and g.current_user:
                username = g.current_user.username
            if user_id is None and hasattr(g, 'user_id'):
                user_id = g.user_id
            
            # Get request context
            ip_address = None
            user_agent = None
            if request:
                ip_address = request.headers.get('X-Forwarded-For', request.remote_addr)
                if ip_address and ',' in ip_address:
                    ip_address = ip_address.split(',')[0].strip()
                user_agent = request.headers.get('User-Agent', '')[:500]  # Limit length
            
            # Create audit log entry
            audit_log = AuditLog(
                timestamp=datetime.utcnow(),
                username=username or 'anonymous',
                action=action,
                resource_type=resource_type,
                resource_id=str(resource_id) if resource_id else None,
                resource_name=resource_name,
                details=details,
                ip_address=ip_address,
                user_agent=user_agent,
                success=success
            )
            
            db.session.add(audit_log)
            db.session.commit()
            
            # Also log to file/console for debugging
            log_msg = f"AUDIT: {action} by {username} - {details}"
            if success:
                logger.info(log_msg)
            else:
                logger.warning(log_msg)
            
            return audit_log
            
        except Exception as e:
            logger.error(f"Failed to create audit log: {e}")
            db.session.rollback()
            return None
    
    @staticmethod
    def get_logs(
        page: int = 1,
        per_page: int = 50,
        username: Optional[str] = None,
        action: Optional[str] = None,
        resource_type: Optional[str] = None,
        success: Optional[bool] = None,
        date_from: Optional[datetime] = None,
        date_to: Optional[datetime] = None,
        search: Optional[str] = None,
        category: Optional[str] = None
    ) -> tuple:
        """
        Get audit logs with filtering and pagination
        
        Returns:
            (logs, total_count, total_pages)
        """
        query = AuditLog.query
        
        # Apply filters
        if username:
            query = query.filter(AuditLog.username.ilike(f'%{username}%'))
        
        if action:
            query = query.filter(AuditLog.action == action)
        
        if category and category in AuditService.CATEGORIES:
            query = query.filter(AuditLog.action.in_(AuditService.CATEGORIES[category]))
        
        if resource_type:
            query = query.filter(AuditLog.resource_type == resource_type)
        
        if success is not None:
            query = query.filter(AuditLog.success == success)
        
        if date_from:
            query = query.filter(AuditLog.timestamp >= date_from)
        
        if date_to:
            query = query.filter(AuditLog.timestamp <= date_to)
        
        if search:
            search_filter = f'%{search}%'
            query = query.filter(
                db.or_(
                    AuditLog.username.ilike(search_filter),
                    AuditLog.action.ilike(search_filter),
                    AuditLog.details.ilike(search_filter),
                    AuditLog.resource_type.ilike(search_filter),
                    AuditLog.ip_address.ilike(search_filter)
                )
            )
        
        # Order by most recent first
        query = query.order_by(AuditLog.timestamp.desc())
        
        # Get total count
        total = query.count()
        total_pages = (total + per_page - 1) // per_page
        
        # Paginate
        logs = query.offset((page - 1) * per_page).limit(per_page).all()
        
        return logs, total, total_pages
    
    @staticmethod
    def get_log_by_id(log_id: int) -> Optional[AuditLog]:
        """Get a single audit log by ID"""
        return AuditLog.query.get(log_id)
    
    @staticmethod
    def get_actions_list() -> List[str]:
        """Get list of all unique actions in the database"""
        result = db.session.query(AuditLog.action).distinct().all()
        return sorted([r[0] for r in result if r[0]])
    
    @staticmethod
    def get_stats(days: int = 30) -> Dict[str, Any]:
        """Get audit log statistics"""
        since = datetime.utcnow() - timedelta(days=days)
        
        # Total logs in period
        total = AuditLog.query.filter(AuditLog.timestamp >= since).count()
        
        # Success vs failure
        success_count = AuditLog.query.filter(
            AuditLog.timestamp >= since,
            AuditLog.success == True
        ).count()
        failure_count = total - success_count
        
        # Top actions
        top_actions = db.session.query(
            AuditLog.action,
            db.func.count(AuditLog.id).label('count')
        ).filter(
            AuditLog.timestamp >= since
        ).group_by(
            AuditLog.action
        ).order_by(
            db.desc('count')
        ).limit(10).all()
        
        # Top users
        top_users = db.session.query(
            AuditLog.username,
            db.func.count(AuditLog.id).label('count')
        ).filter(
            AuditLog.timestamp >= since
        ).group_by(
            AuditLog.username
        ).order_by(
            db.desc('count')
        ).limit(10).all()
        
        # Recent failures
        recent_failures = AuditLog.query.filter(
            AuditLog.timestamp >= since,
            AuditLog.success == False
        ).order_by(AuditLog.timestamp.desc()).limit(10).all()
        
        return {
            'period_days': days,
            'total_logs': total,
            'success_count': success_count,
            'failure_count': failure_count,
            'success_rate': round(success_count / total * 100, 1) if total > 0 else 100,
            'top_actions': [{'action': a, 'count': c} for a, c in top_actions],
            'top_users': [{'username': u, 'count': c} for u, c in top_users],
            'recent_failures': [f.to_dict() for f in recent_failures]
        }
    
    @staticmethod
    def cleanup_old_logs(retention_days: int = 90) -> int:
        """Delete logs older than retention period"""
        cutoff = datetime.utcnow() - timedelta(days=retention_days)
        deleted = AuditLog.query.filter(AuditLog.timestamp < cutoff).delete()
        db.session.commit()
        logger.info(f"Cleaned up {deleted} audit logs older than {retention_days} days")
        return deleted
    
    @staticmethod
    def export_logs(
        format: str = 'json',
        date_from: Optional[datetime] = None,
        date_to: Optional[datetime] = None,
        limit: int = 10000
    ) -> str:
        """Export logs to JSON or CSV format"""
        query = AuditLog.query
        
        if date_from:
            query = query.filter(AuditLog.timestamp >= date_from)
        if date_to:
            query = query.filter(AuditLog.timestamp <= date_to)
        
        query = query.order_by(AuditLog.timestamp.desc()).limit(limit)
        logs = query.all()
        
        if format == 'json':
            return json.dumps([log.to_dict() for log in logs], indent=2, default=str)
        elif format == 'csv':
            import csv
            import io
            output = io.StringIO()
            writer = csv.writer(output)
            writer.writerow(['id', 'timestamp', 'username', 'action', 'resource_type', 'resource_id', 'details', 'ip_address', 'success'])
            for log in logs:
                writer.writerow([
                    log.id, log.timestamp, log.username, log.action,
                    log.resource_type, log.resource_id, log.details,
                    log.ip_address, log.success
                ])
            return output.getvalue()
        
        return ''


# Decorator for automatic audit logging
def audit_log(action: str, resource_type: str = None):
    """
    Decorator to automatically log actions
    
    Usage:
        @audit_log('cert_issue', 'certificate')
        def issue_certificate(...):
            ...
    """
    from functools import wraps
    
    def decorator(f):
        @wraps(f)
        def wrapper(*args, **kwargs):
            try:
                result = f(*args, **kwargs)
                
                # Try to extract resource_id from result or kwargs
                res_id = None
                if isinstance(result, tuple) and len(result) >= 2:
                    # Flask response tuple
                    pass
                elif hasattr(result, 'id'):
                    res_id = result.id
                elif 'id' in kwargs:
                    res_id = kwargs['id']
                
                AuditService.log_action(
                    action=action,
                    resource_type=resource_type,
                    resource_id=res_id,
                    details=f"Action {action} completed successfully",
                    success=True
                )
                return result
                
            except Exception as e:
                AuditService.log_action(
                    action=action,
                    resource_type=resource_type,
                    details=f"Action {action} failed: {str(e)}",
                    success=False
                )
                raise
        
        return wrapper
    return decorator
