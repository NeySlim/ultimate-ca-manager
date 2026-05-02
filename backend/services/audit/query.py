import json
import logging
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List
from models import db, AuditLog
from utils.datetime_utils import utc_now
from ._constants import CATEGORIES

logger = logging.getLogger(__name__)


class AuditQueryMixin:

    @staticmethod
    def get_logs(
        page: int = 1,
        per_page: int = 50,
        username: Optional[str] = None,
        action=None,
        resource_type=None,
        success: Optional[bool] = None,
        date_from: Optional[datetime] = None,
        date_to: Optional[datetime] = None,
        search: Optional[str] = None,
        category: Optional[str] = None
    ) -> tuple:
        query = AuditLog.query

        if username:
            query = query.filter(AuditLog.username.ilike(f'%{username}%'))

        if action:
            if isinstance(action, list):
                query = query.filter(AuditLog.action.in_(action))
            else:
                query = query.filter(AuditLog.action == action)

        if category and category in CATEGORIES:
            query = query.filter(AuditLog.action.in_(CATEGORIES[category]))

        if resource_type:
            if isinstance(resource_type, list):
                query = query.filter(AuditLog.resource_type.in_(resource_type))
            else:
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

        query = query.order_by(AuditLog.timestamp.desc())

        total = query.count()
        total_pages = (total + per_page - 1) // per_page
        logs = query.offset((page - 1) * per_page).limit(per_page).all()

        return logs, total, total_pages

    @staticmethod
    def get_log_by_id(log_id: int) -> Optional[AuditLog]:
        return AuditLog.query.get(log_id)

    @staticmethod
    def get_actions_list() -> List[str]:
        result = db.session.query(AuditLog.action).distinct().all()
        return sorted([r[0] for r in result if r[0]])

    @staticmethod
    def get_stats(days: int = 30) -> Dict[str, Any]:
        since = utc_now() - timedelta(days=days)

        total = AuditLog.query.filter(AuditLog.timestamp >= since).count()

        success_count = AuditLog.query.filter(
            AuditLog.timestamp >= since,
            AuditLog.success == True
        ).count()
        failure_count = total - success_count

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
        cutoff = utc_now() - timedelta(days=retention_days)
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
            writer.writerow(['id', 'timestamp', 'username', 'action', 'resource_type',
                             'resource_id', 'details', 'ip_address', 'success'])
            for log in logs:
                writer.writerow([
                    log.id, log.timestamp, log.username, log.action,
                    log.resource_type, log.resource_id, log.details,
                    log.ip_address, log.success
                ])
            return output.getvalue()

        return ''
