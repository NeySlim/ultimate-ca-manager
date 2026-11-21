import json
import logging
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List
from models import db, AuditLog
from utils.datetime_utils import utc_now
from utils.sqlite_hints import indexed_by
from ._constants import CATEGORIES

TIMESTAMP_INDEX = 'ix_audit_logs_timestamp'

logger = logging.getLogger(__name__)


def _like_literal(term: str) -> str:
    """A typed `_` or `%` matches itself under `escape='\\'`."""
    return term.replace('\\', '\\\\').replace('%', '\\%').replace('_', '\\_')


class AuditQueryMixin:

    @staticmethod
    def _filtered_query(
        username: Optional[str] = None,
        action=None,
        resource_type=None,
        success: Optional[bool] = None,
        date_from: Optional[datetime] = None,
        date_to: Optional[datetime] = None,
        search: Optional[str] = None,
        category: Optional[str] = None
    ):
        """The filters of the list, shared with the export so both select the same rows."""
        query = AuditLog.query

        if username:
            query = query.filter(AuditLog.username.ilike(f'%{_like_literal(username)}%', escape='\\'))

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
            search_filter = f'%{_like_literal(search)}%'
            query = query.filter(
                db.or_(*(column.ilike(search_filter, escape='\\') for column in (
                    AuditLog.username, AuditLog.action, AuditLog.details,
                    AuditLog.resource_type, AuditLog.ip_address)))
            )

        return query

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
        query = AuditQueryMixin._filtered_query(
            username=username, action=action, resource_type=resource_type, success=success,
            date_from=date_from, date_to=date_to, search=search, category=category)
        query = query.order_by(AuditLog.timestamp.desc())

        total = query.count()
        total_pages = (total + per_page - 1) // per_page
        logs = query.offset((page - 1) * per_page).limit(per_page).all()

        return logs, total, total_pages

    @staticmethod
    def get_log_by_id(log_id: int) -> Optional[AuditLog]:
        return db.session.get(AuditLog, log_id)

    @staticmethod
    def get_actions_list() -> List[str]:
        result = db.session.query(AuditLog.action).distinct().all()
        return sorted([r[0] for r in result if r[0]])

    @staticmethod
    def get_stats(days: int = 30) -> Dict[str, Any]:
        since = utc_now() - timedelta(days=days)

        # Every statement walks the period on the timestamp index, whatever sqlite_stat1 says
        def period(query):
            return indexed_by(query.filter(AuditLog.timestamp >= since), AuditLog, TIMESTAMP_INDEX)

        total = period(AuditLog.query).count()

        success_count = period(AuditLog.query).filter(AuditLog.success == True).count()
        failure_count = total - success_count

        top_actions = period(db.session.query(
            AuditLog.action,
            db.func.count(AuditLog.id).label('count')
        )).group_by(
            AuditLog.action
        ).order_by(
            db.desc('count')
        ).limit(10).all()

        # OFFSET 0 keeps SQLite from flattening the period into a walk of the username index
        period_rows = indexed_by(db.select(AuditLog.username).where(AuditLog.timestamp >= since),
                                 AuditLog, TIMESTAMP_INDEX).offset(0).subquery()
        count = db.func.count().label('count')
        top_users = db.session.execute(
            db.select(period_rows.c.username, count).group_by(period_rows.c.username)
            .order_by(db.desc(count), period_rows.c.username).limit(10)).all()

        # top_users is capped at 10, so it cannot stand in for the total.
        unique_users = db.session.execute(
            db.select(db.func.count(db.distinct(period_rows.c.username)))).scalar() or 0

        recent_failures = period(AuditLog.query).filter(
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
            'unique_users': unique_users,
            'recent_failures': [f.to_dict() for f in recent_failures]
        }

    @staticmethod
    def cleanup_old_logs(retention_days: int = 90) -> int:
        # The retention purge: a prefix of the chain and a sealed record of it.
        from services.retention_service import purge_older_than
        cutoff = utc_now() - timedelta(days=retention_days)
        try:
            deleted = purge_older_than(cutoff, retention_days)
        except Exception as e:
            db.session.rollback()
            logger.error(f"Audit log cleanup failed: {e}", exc_info=True)
            raise
        logger.info(f"Cleaned up {deleted} audit logs older than {retention_days} days")
        return deleted

    @staticmethod
    def export_logs(
        format: str = 'json',
        date_from: Optional[datetime] = None,
        date_to: Optional[datetime] = None,
        limit: int = 10000,
        **filters
    ) -> str:
        """*filters* are those of get_logs: username, action, resource_type, success, search, category."""
        query = AuditQueryMixin._filtered_query(date_from=date_from, date_to=date_to, **filters)

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
