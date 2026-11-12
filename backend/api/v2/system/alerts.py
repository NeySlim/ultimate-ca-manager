"""
System Alerts Operations
"""

from . import bp
from flask import request
from auth.unified import require_auth
from utils.response import success_response, error_response
from utils.db_transaction import safe_commit
from models import db
from services.audit_service import AuditService
from services.notification_service import NotificationService
import logging
import json as _json

logger = logging.getLogger(__name__)


_MAX_ALERT_DAYS = 3650  # mirrors NotificationConfig.MAX_ALERT_DAYS


def _alert_payload(config):
    from models.email_notification import NotificationConfig
    return {
        'enabled': bool(config.enabled) if config else False,
        'alert_days': config.get_alert_days() if config else list(NotificationConfig.DEFAULT_ALERT_DAYS),
        'include_revoked': bool(config.include_revoked) if config else False,
        'exclude_acme': bool(config.exclude_acme) if config else False,
        'recipients': _json.loads(config.recipients) if config and config.recipients else [],
    }


def _validate_alert_days(days):
    """Return a cleaned threshold list or raise ValueError (#323)."""
    if not isinstance(days, list) or not days:
        raise ValueError('alert_days must be a non-empty list of day counts')
    cleaned = []
    for d in days:
        if isinstance(d, bool) or not isinstance(d, int):
            raise ValueError('alert_days entries must be integers')
        if d < 1 or d > _MAX_ALERT_DAYS:
            raise ValueError(f'alert_days entries must be between 1 and {_MAX_ALERT_DAYS}')
        cleaned.append(d)
    return sorted(set(cleaned), reverse=True)


@bp.route('/api/v2/system/alerts/expiry', methods=['GET'])
@require_auth(['read:settings'])
def get_expiry_alert_settings():
    """Get certificate expiry alert settings from database"""
    try:
        from models.email_notification import NotificationConfig
        config = NotificationConfig.query.filter_by(type='cert_expiring').first()
        return success_response(data=_alert_payload(config))
    except Exception as e:
        logger.error(f"Failed to get expiry alert settings: {e}")
        return error_response("Failed to get settings", 500)


@bp.route('/api/v2/system/alerts/expiry', methods=['PUT'])
@require_auth(['admin:system'])
def update_expiry_alert_settings():
    """Update certificate expiry alert settings in database.

    Every selected threshold is stored (#323); the scheduled check reads the
    same row, so the selection, the recipients and the toggle are what the
    job actually uses (#324).
    """
    try:
        from models.email_notification import NotificationConfig
        data = request.get_json() or {}

        for flag in ('enabled', 'include_revoked', 'exclude_acme'):
            if flag in data and not isinstance(data[flag], bool):
                return error_response(f'{flag} must be a boolean', 400)
        if 'alert_days' in data:
            try:
                alert_days = _validate_alert_days(data['alert_days'])
            except ValueError as exc:
                return error_response(str(exc), 400)
        else:
            alert_days = None
        if 'recipients' in data:
            raw = data['recipients']
            if not isinstance(raw, list) or any(not isinstance(r, str) for r in raw):
                return error_response('recipients must be a list of e-mail addresses', 400)
            recipients = [r.strip() for r in raw if r.strip()]
        else:
            recipients = None

        config = NotificationConfig.query.filter_by(type='cert_expiring').first()
        if not config:
            config = NotificationConfig(type='cert_expiring')
            db.session.add(config)

        if 'enabled' in data:
            config.enabled = data['enabled']
        if alert_days is not None:
            config.set_alert_days(alert_days)
        if 'include_revoked' in data:
            config.include_revoked = data['include_revoked']
        if 'exclude_acme' in data:
            config.exclude_acme = data['exclude_acme']
        if recipients is not None:
            config.recipients = _json.dumps(recipients)

        ok, err = safe_commit(logger, "Failed to update expiry alert settings")
        if not ok:
            return err

        return success_response(message="Expiry alert settings updated", data=_alert_payload(config))
    except Exception as e:
        logger.error(f"Failed to update expiry alert settings: {e}")
        return error_response("Failed to update settings", 500)


@bp.route('/api/v2/system/alerts/expiry/check', methods=['POST'])
@require_auth(['admin:system'])
def trigger_expiry_check():
    """Manually trigger expiry check using NotificationService"""
    try:
        result = NotificationService.run_scheduled_checks()
        if result.get('status') == 'skipped':
            return success_response(message="Check not run: another node is running it", data=result)
        total_sent = sum(v.get('notified', 0) for v in result.values() if isinstance(v, dict))
        return success_response(
            message=f"Check complete: {total_sent} alerts sent",
            data=result
        )
    except Exception as e:
        logger.error(f"Expiry check failed: {e}")
        return error_response("Expiry check failed", 500)
