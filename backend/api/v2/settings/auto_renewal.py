"""
Settings - Generic certificate auto-renewal configuration.

Exposes the existing AutoRenewalService config (system_config keys
`auto_renewal_enabled`, `auto_renewal_days`, `auto_renewal_sources`,
`auto_renewal_notify_emails`, `auto_renewal_notify_on_renewal`,
`auto_renewal_notify_on_failure`) over the REST API so the Settings UI
can manage it without touching the database directly.
"""

from flask import request
from auth.unified import require_auth
from utils.response import success_response, error_response
from models import db, SystemConfig
from utils.db_transaction import safe_commit
from services.audit_service import AuditService
from services.auto_renewal_service import AutoRenewalService
import json
import logging

from . import bp, get_config, set_config

logger = logging.getLogger(__name__)

ALLOWED_SOURCES = {'scep', 'acme', 'est', 'manual', 'webui', 'api'}
MIN_DAYS = 1
MAX_DAYS = 365


def _bool(value, default=False):
    if isinstance(value, bool):
        return value
    if value is None:
        return default
    return str(value).strip().lower() in ('1', 'true', 'yes', 'on')


def _load():
    """Return current config in API shape (also fills defaults)."""
    cfg = AutoRenewalService.get_renewal_config()

    notify_on_renewal_raw = get_config('auto_renewal_notify_on_renewal', None)
    notify_on_failure_raw = get_config('auto_renewal_notify_on_failure', None)
    emails_raw = get_config('auto_renewal_notify_emails', '[]')

    try:
        emails = json.loads(emails_raw) if emails_raw else []
        if not isinstance(emails, list):
            emails = []
    except (TypeError, ValueError):
        emails = []

    return {
        'enabled': bool(cfg.get('enabled', False)),
        'days_before_expiry': int(cfg.get('days_before_expiry', 30)),
        'renewal_sources': list(cfg.get('renewal_sources', ['scep', 'acme', 'est'])),
        'notify_on_renewal': _bool(notify_on_renewal_raw, True),
        'notify_on_failure': _bool(notify_on_failure_raw, True),
        'notify_emails': [str(e).strip() for e in emails if str(e).strip()],
    }


@bp.route('/api/v2/settings/auto-renewal', methods=['GET'])
@require_auth(['read:settings'])
def get_auto_renewal_settings():
    """Return current generic auto-renewal configuration."""
    return success_response(data=_load())


@bp.route('/api/v2/settings/auto-renewal', methods=['PATCH'])
@require_auth(['write:settings'])
def update_auto_renewal_settings():
    """Update generic auto-renewal configuration."""
    data = request.get_json(silent=True) or {}

    # Validate
    if 'days_before_expiry' in data:
        try:
            days = int(data['days_before_expiry'])
        except (TypeError, ValueError):
            return error_response('days_before_expiry must be an integer', 400)
        if not (MIN_DAYS <= days <= MAX_DAYS):
            return error_response(
                f'days_before_expiry must be between {MIN_DAYS} and {MAX_DAYS}', 400
            )
        data['days_before_expiry'] = days

    if 'renewal_sources' in data:
        srcs = data['renewal_sources']
        if not isinstance(srcs, list):
            return error_response('renewal_sources must be a list', 400)
        normalized = []
        for s in srcs:
            s = str(s).strip().lower()
            if s and s in ALLOWED_SOURCES and s not in normalized:
                normalized.append(s)
        data['renewal_sources'] = normalized

    if 'notify_emails' in data:
        emails = data['notify_emails']
        if not isinstance(emails, list):
            return error_response('notify_emails must be a list', 400)
        cleaned = []
        for e in emails:
            e = str(e).strip()
            if not e:
                continue
            if '@' not in e or len(e) > 320:
                return error_response(f'Invalid email: {e}', 400)
            cleaned.append(e)
        data['notify_emails'] = cleaned

    # Persist
    if 'enabled' in data:
        set_config('auto_renewal_enabled', 'true' if _bool(data['enabled']) else 'false')
    if 'days_before_expiry' in data:
        set_config('auto_renewal_days', str(data['days_before_expiry']))
    if 'renewal_sources' in data:
        set_config('auto_renewal_sources', json.dumps(data['renewal_sources']))
    if 'notify_on_renewal' in data:
        set_config(
            'auto_renewal_notify_on_renewal',
            'true' if _bool(data['notify_on_renewal']) else 'false',
        )
    if 'notify_on_failure' in data:
        set_config(
            'auto_renewal_notify_on_failure',
            'true' if _bool(data['notify_on_failure']) else 'false',
        )
    if 'notify_emails' in data:
        set_config('auto_renewal_notify_emails', json.dumps(data['notify_emails']))

    ok, err = safe_commit(logger, "Failed to update auto-renewal settings")
    if not ok:
        return err

    AuditService.log_action(
        action='settings_update',
        resource_type='settings',
        resource_name='Auto-Renewal Settings',
        details='Updated certificate auto-renewal configuration',
        success=True,
    )

    return success_response(data=_load(), message='Auto-renewal settings updated')


@bp.route('/api/v2/settings/auto-renewal/run', methods=['POST'])
@require_auth(['admin:settings'])
def run_auto_renewal_now():
    """
    Trigger an immediate auto-renewal pass (manual run).

    Returns the same stats dict produced by the scheduled task:
        {renewed, failed, skipped, errors[]}
    """
    try:
        stats = AutoRenewalService.run_auto_renewal()
    except Exception as e:
        logger.error(f"Manual auto-renewal run failed: {e}")
        return error_response('Auto-renewal run failed', 500)

    AuditService.log_action(
        action='auto_renewal_manual_run',
        resource_type='settings',
        resource_name='Auto-Renewal',
        details=f'Manual run: {stats.get("renewed", 0)} renewed, '
                f'{stats.get("failed", 0)} failed, {stats.get("skipped", 0)} skipped',
        success=True,
    )

    return success_response(data=stats, message='Auto-renewal run completed')
