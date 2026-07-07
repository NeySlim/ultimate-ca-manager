"""
Settings - General settings + Certificate Transparency routes
"""

from flask import request
from auth.unified import require_auth
from utils.response import success_response, error_response
from models import db, Certificate
from services.audit_service import AuditService
from api.v2.key_recovery import _dual_control_enabled, _dual_control_env
import json
import logging
import re

from . import bp, get_config, set_config
from utils.hsts import hsts_env_locked

logger = logging.getLogger(__name__)


@bp.route('/api/v2/settings/general', methods=['GET'])
@require_auth(['read:settings'])
def get_general_settings():
    """Get general settings from database"""
    return success_response(data={
        'site_name': get_config('site_name', 'UCM'),
        'system_name': get_config('system_name', get_config('site_name', 'UCM')),
        'timezone': get_config('timezone', 'UTC'),
        'auto_backup_enabled': get_config('auto_backup_enabled', 'false') == 'true',
        'backup_frequency': get_config('backup_frequency', 'daily'),
        'backup_retention_days': int(get_config('backup_retention_days', '30')),
        'backup_password': '',  # Never return password
        'metrics_token': '',  # Never return the token
        'metrics_enabled': bool(get_config('metrics_token', '')),
        'session_timeout': int(get_config('session_timeout', '28800')),
        'session_max_lifetime': int(get_config('session_max_lifetime', '86400')),
        'max_login_attempts': int(get_config('max_login_attempts', '5')),
        'lockout_duration': int(get_config('lockout_duration', '300')),
        'protocol_base_url': get_config('protocol_base_url', ''),
        'http_protocol_port': int(get_config('http_protocol_port', '8080')),
        'base_url': get_config('base_url', ''),
        # ACME public endpoint (local server + proxy directory URLs behind reverse proxy)
        'acme_public_vhost': get_config('acme_public_vhost', ''),
        'acme_public_port': int(get_config('acme_public_port', '443')),
        'acme_public_tls_cert_id': int(get_config('acme_public_tls_cert_id', '0') or 0) or None,
        'date_format': get_config('date_format', 'short'),
        'show_time': get_config('show_time', 'true') == 'true',
        # Password policy
        'min_password_length': int(get_config('min_password_length', '8')),
        'max_password_length': int(get_config('max_password_length', '128')),
        'password_require_uppercase': get_config('password_require_uppercase', 'true') == 'true',
        'password_require_lowercase': get_config('password_require_lowercase', 'true') == 'true',
        'password_require_numbers': get_config('password_require_numbers', 'true') == 'true',
        'password_require_special': get_config('password_require_special', 'true') == 'true',
        # Security toggles
        'enforce_2fa': get_config('enforce_2fa', 'false') == 'true',
        # HSTS (HTTP Strict-Transport-Security) — issue #154.
        # Defaults match the previous hardcoded header (on + includeSubDomains, 1y).
        # `_locked` lists the keys forced by env vars (read-only toggle in UI).
        'hsts_enabled': get_config('hsts_enabled', 'true') == 'true',
        'hsts_include_subdomains': get_config('hsts_include_subdomains', 'true') == 'true',
        'hsts_max_age': int(get_config('hsts_max_age', '31536000')),
        'hsts_env_locked': hsts_env_locked(),
        # Key recovery dual control (four-eyes). Reports the *effective* value
        # (env override > DB > default ON); `_locked` is true when an env var
        # forces it, in which case the Settings toggle is read-only.
        'key_recovery_dual_control': _dual_control_enabled(),
        'key_recovery_dual_control_locked': _dual_control_env() is not None,
    })


@bp.route('/api/v2/settings/general', methods=['PATCH'])
@require_auth(['write:settings'])
def update_general_settings():
    """Update general settings in database"""
    data = request.json or {}

    # List of allowed settings
    allowed_keys = [
        'site_name', 'system_name', 'timezone', 'auto_backup_enabled', 'backup_frequency',
        'backup_retention_days', 'backup_password', 'session_timeout',
        'session_max_lifetime', 'max_login_attempts', 'lockout_duration',
        'protocol_base_url', 'http_protocol_port', 'base_url', 'date_format', 'show_time',
        'acme_public_vhost', 'acme_public_port', 'acme_public_tls_cert_id',
        # Password policy
        'min_password_length', 'max_password_length',
        'password_require_uppercase', 'password_require_lowercase',
        'password_require_numbers', 'password_require_special',
        # Security toggles
        'enforce_2fa',
        # HSTS (operator-configurable, issue #154)
        'hsts_enabled',
        'hsts_include_subdomains',
        'hsts_max_age',
        # Key recovery four-eyes control (env var, when set, overrides this)
        'key_recovery_dual_control',
        # Prometheus metrics bearer token (empty = disabled)
        'metrics_token',
    ]

    # Validate http_protocol_port if provided
    if 'http_protocol_port' in data:
        try:
            port = int(data['http_protocol_port'])
        except (ValueError, TypeError):
            return error_response("Invalid port number", 400)
        if port != 0 and (port < 1024 or port > 65535):
            return error_response("Port must be 0 (disabled) or between 1024-65535", 400)
        from config.settings import Config
        if port == Config.HTTPS_PORT:
            return error_response("HTTP protocol port cannot be the same as HTTPS port", 400)
        data['http_protocol_port'] = str(port)

    if 'acme_public_vhost' in data:
        host = (data.get('acme_public_vhost') or '').strip().lower()
        if host:
            if host.startswith('*.'):
                return error_response(
                    'acme_public_vhost must be a concrete hostname (wildcard is TLS SAN only, not an advertised URL)',
                    400,
                )
            if (
                '://' in host
                or '/' in host
                or ':' in host
                or not re.fullmatch(r'[a-z0-9.-]+', host)
            ):
                return error_response('acme_public_vhost must be a hostname only', 400)
        data['acme_public_vhost'] = host

    if 'acme_public_port' in data:
        try:
            acme_port = int(data['acme_public_port'])
        except (ValueError, TypeError):
            return error_response('acme_public_port must be an integer', 400)
        if acme_port < 1 or acme_port > 65535:
            return error_response('acme_public_port must be between 1 and 65535', 400)
        data['acme_public_port'] = str(acme_port)

    if 'acme_public_tls_cert_id' in data:
        cert_id_raw = data.get('acme_public_tls_cert_id')
        if cert_id_raw in (None, '', 0, '0'):
            data['acme_public_tls_cert_id'] = ''
        else:
            try:
                cert_id = int(cert_id_raw)
            except (ValueError, TypeError):
                return error_response('acme_public_tls_cert_id must be an integer', 400)
            cert = db.session.get(Certificate, cert_id)
            if not cert:
                return error_response('ACME public TLS certificate not found', 404)
            if not cert.prv:
                return error_response('ACME public TLS certificate must include a private key', 400)
            data['acme_public_tls_cert_id'] = str(cert_id)

    # Validate HSTS max-age (non-negative int) when provided
    if 'hsts_max_age' in data:
        try:
            data['hsts_max_age'] = str(int(data['hsts_max_age']))
        except (ValueError, TypeError):
            return error_response('hsts_max_age must be an integer', 400)
        if int(data['hsts_max_age']) < 0:
            return error_response('hsts_max_age must be >= 0', 400)

    for key in allowed_keys:
        if key in data:
            value = data[key]
            # Prometheus metrics token: the API never returns the current token,
            # so a blank value means "keep current" (avoids wiping it when other
            # general settings are saved). A sentinel disables it explicitly.
            if key == 'metrics_token':
                if not value:
                    continue
                if value == '__disable__':
                    value = ''
            # Convert booleans to string
            if isinstance(value, bool):
                value = 'true' if value else 'false'
            # Backup password is used for unattended scheduled backups, so it
            # must be stored — but encrypted at rest, never plaintext.
            if key == 'backup_password' and value:
                from utils.encryption import encrypt_if_needed
                value = encrypt_if_needed(value)
            set_config(key, value)

    try:
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        logger.error(f"Failed to update general settings: {e}")
        return error_response('Failed to update settings', 500)

    AuditService.log_action(
        action='settings_update',
        resource_type='settings',
        resource_name='General Settings',
        details='Updated general settings',
        success=True
    )

    return success_response(message='Settings saved successfully')


# --- Certificate Transparency (CT) ---

@bp.route('/api/v2/settings/ct', methods=['GET'])
@require_auth(['read:settings'])
def get_ct_settings():
    """Get Certificate Transparency configuration."""
    return success_response(data={
        'enabled': get_config('ct_enabled', 'false') == 'true',
        'log_urls': json.loads(get_config('ct_log_urls', '[]')),
        'auto_submit': get_config('ct_auto_submit', 'false') == 'true',
    })


@bp.route('/api/v2/settings/ct', methods=['PATCH'])
@require_auth(['admin:settings'])
def update_ct_settings():
    """Update Certificate Transparency configuration."""
    data = request.get_json()

    if 'enabled' in data:
        set_config('ct_enabled', 'true' if data['enabled'] else 'false')
    if 'log_urls' in data:
        if not isinstance(data['log_urls'], list):
            return error_response('log_urls must be a list', 400)
        set_config('ct_log_urls', json.dumps(data['log_urls']))
    if 'auto_submit' in data:
        set_config('ct_auto_submit', 'true' if data['auto_submit'] else 'false')

    try:
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        logger.error(f"Failed to update CT settings: {e}")
        return error_response('Failed to update CT settings', 500)

    AuditService.log_action(
        'ct_settings_updated',
        resource_type='settings',
        details='Certificate Transparency settings updated'
    )

    return success_response(message='CT settings updated')
