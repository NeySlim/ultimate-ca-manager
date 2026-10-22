"""
Settings - General settings + Certificate Transparency routes
"""

from flask import g, request
from auth.unified import has_permission, require_auth
from services.settings_registry import DATE_FORMATS, as_boolean_word, effective
from utils.response import success_response, error_response
from models import db, Certificate
from services.audit_service import AuditService
from services.retention_service import RetentionPolicy, RetentionSettingError
from api.v2.key_recovery import _dual_control_enabled, _dual_control_env
import json
import logging

from . import bp, get_config, set_config
from services.backup.settings_contract import (
    BackupSettingError,
    validate_backup_kdf,
    validate_backup_password,
    validate_frequency,
    validate_retention_days,
)
from utils.hsts import hsts_env_locked
from utils import admin_allowlist
import compliance_profiles
from utils.public_endpoints import validate_admin_base_url, validate_protocol_base_url

logger = logging.getLogger(__name__)


def _int_config(key, default):
    """Read an int SystemConfig value, tolerating empty/garbage stored values."""
    try:
        return int(get_config(key, str(default)) or default)
    except (TypeError, ValueError):
        return default


# Writable with admin:settings only; write:settings alone has them dropped.
_ADMIN_ONLY_SETTINGS = frozenset([
    # Sign-in and session policy
    'enforce_2fa',
    'session_timeout',
    'session_max_lifetime',
    'max_login_attempts',
    'lockout_duration',
    'metrics_token',
    'key_recovery_dual_control',
    'min_password_length',
    'max_password_length',
    'password_require_uppercase',
    'password_require_lowercase',
    'password_require_numbers',
    'password_require_special',
    'hsts_enabled',
    'hsts_include_subdomains',
    'hsts_max_age',
    # Public addresses the service advertises and redirects to
    'base_url',
    'protocol_base_url',
    'acme_public_vhost',
    'acme_public_port',
    'acme_public_tls_cert_id',
    # The whole backup schedule is admin-only, not just its password: an
    # operator who can shorten retention can have the daily task delete the
    # archives, which the dedicated admin:system route never allowed.
    'auto_backup_enabled',
    'backup_frequency',
    'backup_retention_days',
    'backup_password',
    'backup_kdf',
    'clear_backup_password',
    'ocsp_responder_auto_renew',
    'ocsp_responder_renew_days',
    # CRL housekeeping deletes certificates and revoked serials
    'crl_auto_delete_expired_revoked',
    'crl_auto_purge_stale_serials',
    # Shortening it has the daily task delete audit history.
    'audit_retention_days',
    # Who may reach the admin UI at all (#402)
    'admin_allowed_networks',
    # Profile new CAs receive when the request names none
    'compliance_profile_default',
])


@bp.route('/api/v2/settings/general', methods=['GET'])
@require_auth(['read:settings'])
def get_general_settings():
    """Get general settings from database"""
    return success_response(data={
        'system_name': get_config('system_name', ''),
        'timezone': get_config('timezone', 'UTC'),
        'auto_backup_enabled': get_config('auto_backup_enabled', 'false') == 'true',
        'backup_frequency': get_config('backup_frequency', 'daily'),
        'backup_retention_days': int(get_config('backup_retention_days', '30')),
        'backup_kdf': get_config('backup_kdf', '') or 'auto',
        'audit_retention_days': RetentionPolicy.get_retention_days(),
        'backup_password': '',  # Never return password
        # Whether one is stored, so the screen can say so without the value
        'backup_password_set': bool(get_config('backup_password', '')),
        'metrics_token': '',  # Never return the token
        'metrics_enabled': bool(get_config('metrics_token', '')),
        'session_timeout': int(get_config('session_timeout', '28800')),
        'session_max_lifetime': int(get_config('session_max_lifetime', '86400')),
        'max_login_attempts': int(get_config('max_login_attempts', '5')),
        'lockout_duration': effective('lockout_duration'),
        'protocol_base_url': get_config('protocol_base_url', ''),
        'http_protocol_port': int(get_config('http_protocol_port', '8080')),
        'base_url': get_config('base_url', ''),
        # ACME public endpoint (local server + proxy directory URLs behind reverse proxy)
        'acme_public_vhost': get_config('acme_public_vhost', ''),
        'acme_public_port': effective('acme_public_port'),
        'acme_public_tls_cert_id': int(get_config('acme_public_tls_cert_id', '0') or 0) or None,
        'date_format': effective('date_format'),
        'show_time': effective('show_time'),
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
        'hsts_enabled': effective('hsts_enabled'),
        'hsts_include_subdomains': effective('hsts_include_subdomains'),
        'hsts_max_age': int(get_config('hsts_max_age', '31536000')),
        'hsts_env_locked': hsts_env_locked(),
        # Key recovery dual control (four-eyes). Reports the *effective* value
        # (env override > DB > default ON); `_locked` is true when an env var
        # forces it, in which case the Settings toggle is read-only.
        'key_recovery_dual_control': _dual_control_enabled(),
        'key_recovery_dual_control_locked': _dual_control_env() is not None,
        # OCSP responder: signed response validity window (hours, 1..168)
        'ocsp_response_validity_hours': int(get_config('ocsp_response_validity_hours', '24') or 24),
        # Delegated OCSP responder certificates: daily renewal before expiry
        'ocsp_responder_auto_renew': get_config('ocsp_responder_auto_renew', 'true') == 'true',
        'ocsp_responder_renew_days': int(get_config('ocsp_responder_renew_days', '30') or 30),
        # CRL housekeeping, read exactly as CRL generation reads it
        'crl_auto_delete_expired_revoked': effective('crl_auto_delete_expired_revoked'),
        'crl_auto_purge_stale_serials': effective('crl_auto_purge_stale_serials'),
        # Admin source-address allowlist (#402); the env var, when set, locks it.
        'admin_allowed_networks': admin_allowlist.configured_entries(),
        'admin_allowed_networks_env_locked': admin_allowlist.env_locked(),
        'admin_allowlist_disabled': admin_allowlist.disabled_by_env(),
        'admin_client_ip': request.remote_addr or '',
        'compliance_profile_default': compliance_profiles.default_profile() or '',
    })


@bp.route('/api/v2/settings/general', methods=['PATCH'])
@require_auth(['write:settings'])
def update_general_settings():
    """Update general settings in database"""
    data = request.json or {}
    if not isinstance(data, dict):
        return error_response('Request body must be a JSON object', 400)

    # Reserved keys are dropped before any validation; a body holding nothing
    # else is refused, so a mixed card still saves its other fields.
    if not has_permission('admin:settings', getattr(g, 'permissions', None) or []):
        reserved = sorted(_ADMIN_ONLY_SETTINGS.intersection(data))
        if reserved and len(reserved) == len(data):
            return error_response(
                'These settings require the admin:settings permission: '
                + ', '.join(reserved), 403)
        if reserved:
            logger.info('Ignored admin-only settings without admin:settings: %s',
                        ', '.join(reserved))
            data = {k: v for k, v in data.items() if k not in _ADMIN_ONLY_SETTINGS}

    # List of allowed settings
    allowed_keys = [
        'system_name', 'timezone', 'auto_backup_enabled', 'backup_frequency',
        'backup_retention_days', 'backup_password', 'backup_kdf', 'session_timeout',
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
        # OCSP responder response validity window
        'ocsp_response_validity_hours',
        'ocsp_responder_auto_renew',
        'ocsp_responder_renew_days',
        # CRL housekeeping flags, stored 'true' or 'false'
        'crl_auto_delete_expired_revoked',
        'crl_auto_purge_stale_serials',
        # Audit log retention in days, 0 keeps every log
        'audit_retention_days',
        'compliance_profile_default',
    ]

    if 'ocsp_response_validity_hours' in data:
        try:
            hours = int(data['ocsp_response_validity_hours'])
        except (TypeError, ValueError):
            return error_response('ocsp_response_validity_hours must be an integer', 400)
        if hours < 1 or hours > 168:
            return error_response('ocsp_response_validity_hours must be between 1 and 168', 400)
        data['ocsp_response_validity_hours'] = str(hours)

    if 'ocsp_responder_renew_days' in data:
        try:
            days = int(data['ocsp_responder_renew_days'])
        except (TypeError, ValueError):
            return error_response('ocsp_responder_renew_days must be an integer', 400)
        if days < 1 or days > 365:
            return error_response('ocsp_responder_renew_days must be between 1 and 365', 400)
        data['ocsp_responder_renew_days'] = str(days)
    if 'ocsp_responder_auto_renew' in data:
        data['ocsp_responder_auto_renew'] = bool(data['ocsp_responder_auto_renew'])

    if 'base_url' in data:
        normalized, err = validate_admin_base_url(data.get('base_url') or '')
        if err:
            return error_response(err, 400)
        # Reachability guard (#303): a wrong base_url redirects the whole
        # admin UI (IP access included) to a dead hostname. Refuse unless the
        # operator explicitly overrides with {"force": true} (e.g. DNS not
        # published yet). UCM_DISABLE_CANONICAL_REDIRECT=1 is the recovery
        # escape hatch for an already locked-out instance.
        if normalized and not data.get('force'):
            from utils.public_endpoints import probe_admin_base_url
            probe_err = probe_admin_base_url(normalized)
            if probe_err:
                return error_response(
                    f'base_url looks unreachable: {probe_err}. Fix it, or '
                    'resend with "force": true to apply anyway. If the UI '
                    'ever becomes unreachable because of this setting, start '
                    'the service with UCM_DISABLE_CANONICAL_REDIRECT=1.', 400)
        data.pop('force', None)
        data['base_url'] = normalized or ''

    if 'protocol_base_url' in data:
        normalized, err = validate_protocol_base_url(data.get('protocol_base_url') or '')
        if err:
            return error_response(err, 400)
        data['protocol_base_url'] = normalized or ''

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
        raw_vhost = data.get('acme_public_vhost')
        if raw_vhost is not None and not isinstance(raw_vhost, str):
            return error_response('acme_public_vhost must be a string', 400)
        host = (raw_vhost or '').strip().lower()
        if host:
            if host.startswith('*.'):
                return error_response(
                    'acme_public_vhost must be a concrete hostname (wildcard is TLS SAN only, not an advertised URL)',
                    400,
                )
            from utils.acme_public_url import is_valid_public_vhost
            if not is_valid_public_vhost(host):
                return error_response(
                    'acme_public_vhost must be a valid FQDN (no scheme, port, or path)',
                    400,
                )
            from utils.public_endpoints import validate_acme_public_vhost_host
            ssrf_err = validate_acme_public_vhost_host(host)
            if ssrf_err:
                return error_response(ssrf_err, 400)
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
            # Clearing removes the row entirely (no dead empty-string config)
            from models import SystemConfig
            SystemConfig.query.filter_by(key='acme_public_tls_cert_id').delete()
            data.pop('acme_public_tls_cert_id')
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

    # The backup schedule is validated by the same contract as PATCH
    # /api/v2/settings/backup/schedule. This route used to take any string as
    # a cadence and any value at all as a retention, and the scheduler
    # substituted a default when it read them back: a frequency nobody ran and
    # a retention nobody applied, both saved without a word.
    if 'backup_frequency' in data:
        try:
            data['backup_frequency'] = validate_frequency(data['backup_frequency'])
        except BackupSettingError as e:
            return error_response(str(e), 400)

    if 'backup_retention_days' in data:
        try:
            data['backup_retention_days'] = validate_retention_days(
                data['backup_retention_days'])
        except BackupSettingError as e:
            return error_response(str(e), 400)

    # The screen sends every setting back: an unchanged KDF must not block an
    # unrelated save once FIPS mode refuses it
    if 'backup_kdf' in data and data['backup_kdf'] != (get_config('backup_kdf', '') or 'auto'):
        try:
            data['backup_kdf'] = validate_backup_kdf(data['backup_kdf'])
        except BackupSettingError as e:
            return error_response(str(e), 400)

    if 'audit_retention_days' in data:
        try:
            data['audit_retention_days'] = str(
                RetentionPolicy.validate_days(
                    data['audit_retention_days'], field='audit_retention_days'))
        except RetentionSettingError as e:
            return error_response(str(e), 400)

    # Validate HSTS max-age (non-negative int) when provided
    if 'hsts_max_age' in data:
        try:
            data['hsts_max_age'] = str(int(data['hsts_max_age']))
        except (ValueError, TypeError):
            return error_response('hsts_max_age must be an integer', 400)
        if int(data['hsts_max_age']) < 0:
            return error_response('hsts_max_age must be >= 0', 400)

    # The screen offers a tick box and a five-option dropdown; the row took
    # any string at all, and the readers were then left to guess. `show_time`
    # is settled before it is stored, `date_format` is refused when it is not
    # one the SPA can render.
    if 'show_time' in data:
        word = as_boolean_word(data['show_time'])
        if word is None:
            return error_response(
                'show_time must be a boolean', 400)
        data['show_time'] = word
    if 'date_format' in data:
        if data['date_format'] not in DATE_FORMATS:
            return error_response(
                'date_format must be one of: ' + ', '.join(DATE_FORMATS), 400)

    profile_change = None
    if 'compliance_profile_default' in data:
        profile, err = compliance_profiles.normalize(data['compliance_profile_default'])
        if err:
            return error_response(err.replace('complianceProfile', 'compliance_profile_default'), 400)
        before = compliance_profiles.default_profile()
        data['compliance_profile_default'] = profile or ''
        if profile != before:
            profile_change = (before, profile)

    # Saved only when it changed, and never to a list that would refuse the
    # caller's own address, unless the check is switched off for recovery.
    # The screen sends it back with every save.
    allowlist_change = None
    if 'admin_allowed_networks' in data:
        raw_networks = data.pop('admin_allowed_networks')
        if not admin_allowlist.env_locked():
            try:
                entries = admin_allowlist.parse_entries(raw_networks)
            except ValueError as e:
                return error_response(str(e), 400)
            current = admin_allowlist.split_entries(get_config(admin_allowlist.CONFIG_KEY, '') or '')
            if entries != current:
                client = request.remote_addr or ''
                if (entries and not admin_allowlist.disabled_by_env()
                        and not admin_allowlist.address_allowed_by(client, entries)):
                    return error_response(
                        f'The admin allowlist must include your own address ({client or "unknown"}), '
                        'otherwise this session would be locked out', 400)
                set_config(admin_allowlist.CONFIG_KEY, ','.join(entries))
                allowlist_change = (current, entries)

    # The password is never sent back, so a blank one keeps the stored value;
    # clearing it takes this explicit flag.
    clear_backup_password = data.pop('clear_backup_password', False)
    if not isinstance(clear_backup_password, bool):
        return error_response('clear_backup_password must be a boolean', 400)
    if clear_backup_password:
        if data.get('backup_password'):
            return error_response(
                'Send either a new backup_password or clear_backup_password, '
                'not both', 400)
        data.pop('backup_password', None)
        set_config('backup_password', '')

    for key in allowed_keys:
        if key in data:
            value = data[key]
            if key == 'backup_password' and not value:
                continue
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
                # The rule the backup itself applies: a password refused at
                # backup time would fail every scheduled backup in silence
                try:
                    validate_backup_password(value)
                except BackupSettingError as e:
                    return error_response(str(e), 400)
                from utils.encryption import encrypt_if_needed
                value = encrypt_if_needed(value)
            set_config(key, value)

    try:
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        logger.error(f"Failed to update general settings: {e}")
        return error_response('Failed to update settings', 500)

    if allowlist_change is not None:
        admin_allowlist.invalidate_cache()
        before, after = allowlist_change
        AuditService.log_action(
            action='admin_allowlist_update',
            resource_type='settings',
            resource_name='Admin allowlist',
            details=f"Admin allowlist changed from [{', '.join(before) or 'none'}] "
                    f"to [{', '.join(after) or 'none'}]",
            success=True,
        )

    if profile_change is not None:
        AuditService.log_action(
            action='compliance_profile_default_update',
            resource_type='settings',
            resource_name='Default compliance profile',
            details=f"Default compliance profile changed from {profile_change[0] or 'none'} "
                    f"to {profile_change[1] or 'none'}",
            success=True,
        )

    AuditService.log_action(
        action='settings_update',
        resource_type='settings',
        resource_name='General Settings',
        details='Updated general settings'
        + ('; backup password cleared' if clear_backup_password else ''),
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
        # None means "use the built-in log list"; an empty list here
        # used to read as "no logs configured".
        'log_urls': effective('ct_log_urls'),
        'auto_submit': get_config('ct_auto_submit', 'false') == 'true',
        'embed_sct': get_config('ct_embed_sct', 'false') == 'true',
        'required': get_config('ct_required', 'false') == 'true',
    })


@bp.route('/api/v2/settings/ct', methods=['PATCH'])
@require_auth(['admin:settings'])
def update_ct_settings():
    """Update Certificate Transparency configuration."""
    data = request.get_json()

    if 'enabled' in data:
        set_config('ct_enabled', 'true' if data['enabled'] else 'false')
    if 'log_urls' in data:
        # null is what GET answers when no list is set: it keeps the built-in logs.
        if data['log_urls'] is None:
            set_config('ct_log_urls', None)
        elif not isinstance(data['log_urls'], list):
            return error_response('log_urls must be a list or null', 400)
        else:
            set_config('ct_log_urls', json.dumps(data['log_urls']))
    if 'auto_submit' in data:
        set_config('ct_auto_submit', 'true' if data['auto_submit'] else 'false')
    if 'embed_sct' in data:
        set_config('ct_embed_sct', 'true' if data['embed_sct'] else 'false')
    if 'required' in data:
        set_config('ct_required', 'true' if data['required'] else 'false')

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
