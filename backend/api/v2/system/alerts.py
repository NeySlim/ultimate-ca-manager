"""
System Alerts Operations
"""

from . import bp
from flask import request
from auth.unified import require_auth
from utils.response import success_response, error_response
from models import db
from services.audit_service import AuditService
from services.notification_service import NotificationService
import logging
import json as _json

logger = logging.getLogger(__name__)


@bp.route('/api/v2/system/alerts/expiry', methods=['GET'])
@require_auth(['read:settings'])
def get_expiry_alert_settings():
    """Get certificate expiry alert settings from database"""
    try:
        from models.email_notification import NotificationConfig
        config = NotificationConfig.query.filter_by(type='cert_expiring').first()
        data = {
            'enabled': config.enabled if config else False,
            'alert_days': [config.days_before] if config and config.days_before else [30, 14, 7, 1],
            'include_revoked': False,
            'recipients': _json.loads(config.recipients) if config and config.recipients else [],
        }
        return success_response(data=data)
    except Exception as e:
        logger.error(f"Failed to get expiry alert settings: {e}")
        return error_response("Failed to get settings", 500)


@bp.route('/api/v2/system/alerts/expiry', methods=['PUT'])
@require_auth(['admin:system'])
def update_expiry_alert_settings():
    """Update certificate expiry alert settings in database"""
    try:
        from models.email_notification import NotificationConfig
        data = request.get_json() or {}

        config = NotificationConfig.query.filter_by(type='cert_expiring').first()
        if not config:
            config = NotificationConfig(type='cert_expiring')
            db.session.add(config)

        if 'enabled' in data:
            config.enabled = bool(data['enabled'])
        if 'alert_days' in data:
            days = data['alert_days']
            if isinstance(days, list) and days:
                config.days_before = max(int(d) for d in days if d > 0)
        if 'recipients' in data:
            config.recipients = _json.dumps(list(data['recipients']))

        db.session.commit()

        result = {
            'enabled': config.enabled,
            'alert_days': [config.days_before] if config.days_before else [30],
            'include_revoked': False,
            'recipients': _json.loads(config.recipients) if config.recipients else [],
        }
        return success_response(message="Expiry alert settings updated", data=result)
    except Exception as e:
        db.session.rollback()
        logger.error(f"Failed to update expiry alert settings: {e}")
        return error_response("Failed to update settings", 500)


@bp.route('/api/v2/system/alerts/expiry/check', methods=['POST'])
@require_auth(['admin:system'])
def trigger_expiry_check():
    """Manually trigger expiry check using NotificationService"""
    try:
        result = NotificationService.run_scheduled_checks()
        total_sent = sum(v.get('notified', 0) for v in result.values())
        return success_response(
            message=f"Check complete: {total_sent} alerts sent",
            data=result
        )
    except Exception as e:
        logger.error(f"Expiry check failed: {e}")
        return error_response("Expiry check failed", 500)
