"""
Settings - Notification settings + audit logs routes
"""

from flask import request
from auth.unified import require_auth
from utils.response import success_response, error_response
from models import db
from services.audit_service import AuditService
from utils.datetime_utils import utc_isoformat
import json
import logging

from . import bp

logger = logging.getLogger(__name__)


# ============================================================================
# Notification Settings
# ============================================================================

@bp.route('/api/v2/settings/notifications', methods=['GET'])
@require_auth(['read:settings'])
def get_notification_settings():
    """Get notification configurations"""
    from models.email_notification import NotificationConfig

    configs = NotificationConfig.query.all()
    return success_response(data={
        'configs': [{
            'id': c.id,
            'notification_type': c.type,  # Model uses 'type'
            'enabled': c.enabled,
            'recipients': json.loads(c.recipients) if c.recipients else [],
            'threshold_days': c.days_before,  # Model uses 'days_before'
            'cooldown_hours': c.cooldown_hours,
            'description': c.description
        } for c in configs]
    })


@bp.route('/api/v2/settings/notifications', methods=['PATCH'])
@require_auth(['write:settings'])
def update_notification_settings():
    """Update notification configuration"""
    from models.email_notification import NotificationConfig

    data = request.json
    if not data:
        return error_response('No data provided', 400)

    config_id = data.get('id')
    if config_id:
        config = NotificationConfig.query.get(config_id)
        if not config:
            return error_response('Configuration not found', 404)
    else:
        notification_type = data.get('notification_type')
        if not notification_type:
            return error_response('notification_type required', 400)
        config = NotificationConfig.query.filter_by(type=notification_type).first()  # Model uses 'type'
        if not config:
            config = NotificationConfig(type=notification_type)
            db.session.add(config)

    # Update fields
    if 'enabled' in data:
        config.enabled = bool(data['enabled'])
    if 'recipients' in data:
        # Store as JSON string
        recipients = data['recipients']
        config.recipients = json.dumps(recipients) if isinstance(recipients, list) else recipients
    if 'threshold_days' in data:
        config.days_before = int(data['threshold_days'])  # Model uses 'days_before'
    if 'cooldown_hours' in data:
        config.cooldown_hours = int(data['cooldown_hours'])

    try:
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        logger.error(f"Failed to update notification settings: {e}")
        return error_response('Failed to update notification settings', 500)

    AuditService.log_action(
        action='settings_update',
        resource_type='settings',
        resource_name='Notification Settings',
        details='Updated notification settings',
        success=True
    )

    return success_response(
        data={'id': config.id},
        message='Notification settings updated'
    )


@bp.route('/api/v2/settings/notifications/logs', methods=['GET'])
@require_auth(['read:settings'])
def get_notification_logs():
    """Get notification logs"""
    from models.email_notification import NotificationLog

    page = request.args.get('page', 1, type=int)
    per_page = min(request.args.get('per_page', 50, type=int), 100)
    notification_type = request.args.get('type')

    query = NotificationLog.query.order_by(NotificationLog.sent_at.desc())

    if notification_type:
        query = query.filter_by(type=notification_type)  # Model uses 'type'

    pagination = query.paginate(page=page, per_page=per_page, error_out=False)

    return success_response(data={
        'logs': [{
            'id': log.id,
            'notification_type': log.type,  # Model uses 'type'
            'recipient': log.recipient,
            'subject': log.subject,
            'sent_at': utc_isoformat(log.sent_at),
            'status': log.status,  # Model uses 'status' not 'success'
            'error_message': log.error_message,
            'retry_count': log.retry_count
        } for log in pagination.items],
        'pagination': {
            'page': page,
            'per_page': per_page,
            'total': pagination.total,
            'pages': pagination.pages
        }
    })


# ============================================================================
# Audit Logs
# ============================================================================

@bp.route('/api/v2/settings/audit-logs', methods=['GET'])
@require_auth(['admin:system'])
def get_audit_logs():
    """Get system audit logs"""
    from models import AuditLog
    from datetime import datetime

    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 50, type=int)
    user_id = request.args.get('user_id', type=int)
    action = request.args.get('action')
    start_date = request.args.get('start_date')
    end_date = request.args.get('end_date')

    query = AuditLog.query

    if user_id:
        query = query.filter_by(user_id=user_id)
    if action:
        query = query.filter_by(action=action)
    if start_date:
        try:
            start = datetime.fromisoformat(start_date.replace('Z', '+00:00'))
            query = query.filter(AuditLog.timestamp >= start)
        except ValueError:
            pass
    if end_date:
        try:
            end = datetime.fromisoformat(end_date.replace('Z', '+00:00'))
            query = query.filter(AuditLog.timestamp <= end)
        except ValueError:
            pass

    query = query.order_by(AuditLog.timestamp.desc())
    pagination = query.paginate(page=page, per_page=per_page, error_out=False)

    return success_response(
        data=[log.to_dict() for log in pagination.items],
        meta={'total': pagination.total, 'page': page, 'per_page': per_page}
    )
