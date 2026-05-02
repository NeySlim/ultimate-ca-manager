"""
System Audit Operations
"""

from . import bp
from flask import request, current_app
from auth.unified import require_auth
from utils.response import success_response, error_response
from models import db
from services.audit_service import AuditService
from services.retention_service import RetentionPolicy, cleanup_audit_logs as do_cleanup
from services.syslog_service import syslog_forwarder
from api.v2.settings import set_config
import logging

logger = logging.getLogger(__name__)


@bp.route('/api/v2/system/audit/retention', methods=['GET'])
@require_auth(['read:settings'])
def get_audit_retention():
    """Get audit log retention settings and stats"""
    try:
        return success_response(data=RetentionPolicy.get_stats())
    except Exception as e:
        logger.error(f"Failed to get retention settings: {e}")
        return error_response("Failed to get retention settings", 500)


@bp.route('/api/v2/system/audit/retention', methods=['PUT'])
@require_auth(['admin:system'])
def update_audit_retention():
    """Update audit log retention settings"""
    try:
        data = request.get_json() or {}
        settings = RetentionPolicy.update_settings(**data)
        return success_response(
            message="Retention settings updated",
            data=settings
        )
    except Exception as e:
        logger.error(f"Failed to update retention settings: {e}")
        return error_response("Failed to update settings", 500)


@bp.route('/api/v2/system/audit/cleanup', methods=['POST'])
@require_auth(['admin:system'])
def cleanup_audit_logs():
    """Manually trigger audit log cleanup"""
    try:
        data = request.get_json() or {}
        result = do_cleanup(retention_days=data.get('retention_days'))
        return success_response(
            message=result.get('message', 'Cleanup complete'),
            data=result
        )
    except Exception as e:
        logger.error(f"Cleanup failed: {e}")
        return error_response("Cleanup failed", 500)


# ============ Syslog Forwarding ============

@bp.route('/api/v2/system/audit/syslog', methods=['GET'])
@require_auth(['read:settings'])
def get_syslog_config():
    """Get remote syslog configuration"""
    try:
        return success_response(data=syslog_forwarder.config)
    except Exception as e:
        logger.error(f"Failed to get syslog config: {e}")
        return error_response("Failed to get syslog config", 500)


@bp.route('/api/v2/system/audit/syslog', methods=['PUT'])
@require_auth(['admin:system'])
def update_syslog_config():
    """Update remote syslog configuration"""
    try:
        data = request.get_json()
        if not data:
            return error_response("No data provided", 400)

        # Validate
        host = data.get('host', '').strip()
        port = int(data.get('port', 514))
        protocol = data.get('protocol', 'udp').lower()
        enabled = bool(data.get('enabled', False))
        tls = bool(data.get('tls', False))
        categories = data.get('categories', list(syslog_forwarder.ALL_CATEGORIES))

        if protocol not in ('udp', 'tcp'):
            return error_response("Protocol must be 'udp' or 'tcp'", 400)
        if port < 1 or port > 65535:
            return error_response("Port must be between 1 and 65535", 400)
        if enabled and not host:
            return error_response("Host is required when syslog is enabled", 400)

        # Save to database
        set_config('syslog_enabled', str(enabled).lower())
        set_config('syslog_host', host)
        set_config('syslog_port', str(port))
        set_config('syslog_protocol', protocol)
        set_config('syslog_tls', str(tls).lower())
        set_config('syslog_categories', ','.join(categories) if categories else '')
        db.session.commit()

        # Reconfigure forwarder
        syslog_forwarder.configure(
            enabled=enabled, host=host, port=port,
            protocol=protocol, tls=tls, categories=categories
        )

        AuditService.log_system(
            'syslog_config_updated',
            f"Syslog {'enabled' if enabled else 'disabled'}: {protocol.upper()}://{host}:{port}"
        )

        return success_response(
            message='Syslog configuration updated',
            data=syslog_forwarder.config
        )
    except Exception as e:
        logger.error(f"Failed to update syslog config: {e}")
        return error_response("Failed to update syslog config", 500)


@bp.route('/api/v2/system/audit/syslog/test', methods=['POST'])
@require_auth(['admin:system'])
def test_syslog():
    """Send a test message to the configured syslog server"""
    try:
        result = syslog_forwarder.test_connection()
        if result['success']:
            return success_response(message=result['message'])
        else:
            return error_response(result['error'], 400)
    except Exception as e:
        logger.error(f"Syslog test failed: {e}")
        return error_response("Syslog test failed", 500)
