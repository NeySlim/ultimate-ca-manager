"""
Settings Routes v2.0
/api/settings/* - System settings (general, users, backup, email, etc.)
"""

from flask import Blueprint, request, g
from auth.unified import require_auth
from utils.response import success_response, error_response, created_response
from utils.ssrf_protection import validate_url_not_cloud_metadata
from models import db, SystemConfig
from services.audit_service import AuditService
from datetime import datetime, timezone
import json
import logging
from utils.datetime_utils import utc_now
logger = logging.getLogger(__name__)

bp = Blueprint('settings_v2', __name__)


def get_config(key, default=None):
    """Get config value from database"""
    config = SystemConfig.query.filter_by(key=key).first()
    return config.value if config else default


def set_config(key, value):
    """Set config value in database"""
    config = SystemConfig.query.filter_by(key=key).first()
    if config:
        config.value = str(value) if value is not None else None
    else:
        config = SystemConfig(key=key, value=str(value) if value is not None else None)
        db.session.add(config)


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
        'session_timeout': int(get_config('session_timeout', '28800')),
        'session_max_lifetime': int(get_config('session_max_lifetime', '86400')),
        'max_login_attempts': int(get_config('max_login_attempts', '5')),
        'lockout_duration': int(get_config('lockout_duration', '300')),
        'protocol_base_url': get_config('protocol_base_url', ''),
        'http_protocol_port': int(get_config('http_protocol_port', '8080')),
        'base_url': get_config('base_url', ''),
        'date_format': get_config('date_format', 'short'),
        'show_time': get_config('show_time', 'true') == 'true',
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
        'protocol_base_url', 'http_protocol_port', 'base_url', 'date_format', 'show_time'
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
    
    for key in allowed_keys:
        if key in data:
            value = data[key]
            # Convert booleans to string
            if isinstance(value, bool):
                value = 'true' if value else 'false'
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


# NOTE: User management moved to /api/v2/users (users.py)
# The /api/v2/settings/users routes were removed to avoid duplication


@bp.route('/api/v2/settings/backup', methods=['GET'])
@require_auth(['read:settings'])
def get_backup_settings():
    """Get backup configuration"""
    return success_response(data={
        'enabled': False,
        'schedule': None
    })


@bp.route('/api/v2/settings/backup/create', methods=['POST'])
@require_auth(['admin:system'])
def create_backup():
    """Create backup now"""
    from datetime import datetime
    import os
    import secrets
    
    try:
        from services.backup_service import BackupService
        data = request.json or {}
        password = data.get('password')
        generated_password = False
        
        # Generate secure random password if not provided
        if not password:
            password = secrets.token_urlsafe(16)  # 128-bit entropy
            generated_password = True
        elif len(password) < 8:
            return error_response('Password must be at least 8 characters', 400)
        
        service = BackupService()
        backup_bytes = service.create_backup(password)
        
        # Save to disk
        filename = f"ucm_backup_{utc_now().strftime('%Y%m%d_%H%M%S')}.ucmbkp"
        backup_dir = "/opt/ucm/data/backups"
        os.makedirs(backup_dir, exist_ok=True)
        
        filepath = os.path.join(backup_dir, filename)
        with open(filepath, 'wb') as f:
            f.write(backup_bytes)
        
        AuditService.log_action(
            action='system_backup',
            resource_type='system',
            resource_name=filename,
            details=f'Created backup: {filename}',
            success=True
        )
        
        response_data = {
            'filename': filename,
            'size': len(backup_bytes),
            'path': filepath
        }
        
        # Include generated password in response so user can save it
        if generated_password:
            response_data['password'] = password
            response_data['password_generated'] = True
        
        return success_response(
            data=response_data,
            message='Backup created successfully' + (' - SAVE THE PASSWORD!' if generated_password else '')
        )
    except Exception as e:
        logger.error(f"Settings backup failed: {e}")
        return error_response('Backup failed', 500)


@bp.route('/api/v2/settings/backup/restore', methods=['POST'])
@require_auth(['admin:system'])
def restore_backup():
    """Restore from backup file"""
    import tempfile
    import os
    
    if 'file' not in request.files:
        return error_response('No backup file provided', 400)
    
    file = request.files['file']
    if file.filename == '':
        return error_response('No file selected', 400)
    
    password = request.form.get('password')
    
    # Security: Require password for restore
    if not password:
        return error_response('Backup password required', 400)
    
    try:
        from services.backup_service import BackupService
        
        # Save uploaded file temporarily
        with tempfile.NamedTemporaryFile(delete=False, suffix='.ucmbkp') as tmp:
            file.save(tmp.name)
            tmp_path = tmp.name
        
        service = BackupService()
        service.restore_backup(tmp_path, password)
        
        os.unlink(tmp_path)
        
        AuditService.log_action(
            action='system_restore',
            resource_type='system',
            resource_name=file.filename,
            details=f'Restored from backup: {file.filename}',
            success=True
        )
        
        return success_response(
            data={'filename': file.filename, 'restored': True},
            message='Backup restored successfully. Please restart the application.'
        )
    except Exception as e:
        logger.error(f"Settings restore failed: {e}")
        return error_response('Restore failed', 500)


@bp.route('/api/v2/settings/backup/<path:filename>/download', methods=['GET'])
@require_auth(['read:settings'])
def download_backup(filename):
    """Download backup file"""
    from flask import send_file
    from werkzeug.utils import secure_filename
    from pathlib import Path
    import os
    
    backup_dir = Path("/opt/ucm/data/backups")
    
    # SECURITY: Sanitize filename to prevent path traversal
    safe_filename = secure_filename(os.path.basename(filename))
    if not safe_filename:
        return error_response('Invalid filename', 400)
    
    backup_file = backup_dir / safe_filename
    
    # SECURITY: Verify the resolved path is within backup directory
    try:
        backup_file = backup_file.resolve()
        if not backup_file.is_relative_to(backup_dir.resolve()):
            return error_response('Access denied', 403)
    except (ValueError, RuntimeError):
        return error_response('Invalid path', 400)
    
    if not backup_file.exists():
        return error_response('Backup file not found', 404)
    
    return send_file(
        str(backup_file),
        as_attachment=True,
        download_name=safe_filename,
        mimetype='application/octet-stream'
    )


@bp.route('/api/v2/settings/backup/<path:filename>', methods=['DELETE'])
@require_auth(['admin:system'])
def delete_backup(filename):
    """Delete backup file"""
    from werkzeug.utils import secure_filename
    from pathlib import Path
    from utils.response import no_content_response
    import os
    
    backup_dir = Path("/opt/ucm/data/backups")
    
    # SECURITY: Sanitize filename to prevent path traversal
    safe_filename = secure_filename(os.path.basename(filename))
    if not safe_filename:
        return error_response('Invalid filename', 400)
    
    backup_file = backup_dir / safe_filename
    
    # SECURITY: Verify the resolved path is within backup directory
    try:
        backup_file = backup_file.resolve()
        if not backup_file.is_relative_to(backup_dir.resolve()):
            return error_response('Access denied', 403)
    except (ValueError, RuntimeError):
        return error_response('Invalid path', 400)
    
    if backup_file.exists():
        backup_file.unlink()
    
    AuditService.log_action(
        action='backup_delete',
        resource_type='system',
        resource_name=safe_filename,
        details=f'Deleted backup: {safe_filename}',
        success=True
    )
    
    return no_content_response()


@bp.route('/api/v2/settings/email', methods=['GET'])
@require_auth(['read:settings'])
def get_email_settings():
    """Get email/SMTP settings"""
    from models.email_notification import SMTPConfig
    
    smtp = SMTPConfig.query.first()
    if not smtp:
        return success_response(data={
            'enabled': False,
            'smtp_host': '',
            'smtp_port': 587,
            'smtp_username': '',
            'smtp_password': '',
            'smtp_tls': True,
            'smtp_auth': True,
            'smtp_content_type': 'html',
            'from_name': 'UCM Certificate Manager',
            'from_email': ''
        })
    
    return success_response(data={
        'id': smtp.id,
        'enabled': smtp.enabled,
        'smtp_host': smtp.smtp_host or '',
        'smtp_port': smtp.smtp_port or 587,
        'smtp_username': smtp.smtp_user or '',  # Model uses smtp_user
        'smtp_password': '********' if smtp._smtp_password else '',  # Masked
        'smtp_tls': smtp.smtp_use_tls,  # Model uses smtp_use_tls
        'smtp_auth': smtp.smtp_auth if smtp.smtp_auth is not None else True,
        'smtp_content_type': smtp.smtp_content_type or 'html',
        'from_name': smtp.smtp_from_name or 'UCM Certificate Manager',
        'from_email': smtp.smtp_from or '',
        # OAuth2 (XOAUTH2) fields — secrets/tokens never returned, only flags
        'smtp_auth_method': smtp.smtp_auth_method or 'password',
        'smtp_oauth_provider': smtp.smtp_oauth_provider or '',
        'smtp_oauth_tenant_id': smtp.smtp_oauth_tenant_id or '',
        'smtp_oauth_client_id': smtp.smtp_oauth_client_id or '',
        'smtp_oauth_authorize_url': smtp.smtp_oauth_authorize_url or '',
        'smtp_oauth_token_url': smtp.smtp_oauth_token_url or '',
        'smtp_oauth_scope': smtp.smtp_oauth_scope or '',
        'smtp_oauth_redirect_uri': smtp.smtp_oauth_redirect_uri or '',
        'has_oauth_client_secret': bool(smtp._smtp_oauth_client_secret),
        'has_oauth_refresh_token': bool(smtp._smtp_oauth_refresh_token),
    })


@bp.route('/api/v2/settings/email', methods=['PATCH'])
@require_auth(['write:settings'])
def update_email_settings():
    """Update email/SMTP settings"""
    from models.email_notification import SMTPConfig
    
    data = request.json
    if not data:
        return error_response('No data provided', 400)
    
    smtp = SMTPConfig.query.first()
    if not smtp:
        smtp = SMTPConfig()
        db.session.add(smtp)
    
    # Update fields (map frontend names to model column names)
    if 'enabled' in data:
        smtp.enabled = bool(data['enabled'])
    if 'smtp_host' in data:
        smtp.smtp_host = data['smtp_host']
    if 'smtp_port' in data:
        smtp.smtp_port = int(data['smtp_port'])
    if 'smtp_username' in data:
        smtp.smtp_user = data['smtp_username']  # Model uses smtp_user
    if 'smtp_password' in data and data['smtp_password'] and data['smtp_password'] != '********':
        smtp.smtp_password = data['smtp_password']  # Uses encrypted setter
    if 'smtp_tls' in data:
        smtp.smtp_use_tls = bool(data['smtp_tls'])  # Model uses smtp_use_tls
    if 'smtp_auth' in data:
        smtp.smtp_auth = bool(data['smtp_auth'])
    if 'smtp_content_type' in data and data['smtp_content_type'] in ('html', 'text', 'both'):
        smtp.smtp_content_type = data['smtp_content_type']
    if 'from_name' in data:
        smtp.smtp_from_name = data['from_name']  # Model uses smtp_from_name
    if 'from_email' in data:
        smtp.smtp_from = data['from_email']  # Model uses smtp_from

    # OAuth2 fields — admin-supplied client_id / urls / etc.
    # Secrets are only written when explicitly provided (avoids wiping on save).
    if 'smtp_auth_method' in data and data['smtp_auth_method'] in ('password', 'oauth2'):
        smtp.smtp_auth_method = data['smtp_auth_method']
    if 'smtp_oauth_provider' in data:
        smtp.smtp_oauth_provider = (data['smtp_oauth_provider'] or '').lower() or None
    if 'smtp_oauth_tenant_id' in data:
        smtp.smtp_oauth_tenant_id = data['smtp_oauth_tenant_id'] or None
    if 'smtp_oauth_client_id' in data:
        smtp.smtp_oauth_client_id = data['smtp_oauth_client_id'] or None
    if 'smtp_oauth_client_secret' in data and data['smtp_oauth_client_secret'] and data['smtp_oauth_client_secret'] != '********':
        smtp.smtp_oauth_client_secret = data['smtp_oauth_client_secret']
    if 'smtp_oauth_authorize_url' in data:
        url = data['smtp_oauth_authorize_url'] or None
        if url:
            validate_url_not_cloud_metadata(url)
        smtp.smtp_oauth_authorize_url = url
    if 'smtp_oauth_token_url' in data:
        url = data['smtp_oauth_token_url'] or None
        if url:
            validate_url_not_cloud_metadata(url)
        smtp.smtp_oauth_token_url = url
    if 'smtp_oauth_scope' in data:
        smtp.smtp_oauth_scope = data['smtp_oauth_scope'] or None
    if 'smtp_oauth_redirect_uri' in data:
        smtp.smtp_oauth_redirect_uri = data['smtp_oauth_redirect_uri'] or None
    
    try:
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        logger.error(f"Failed to update email settings: {e}")
        return error_response('Failed to update email settings', 500)
    
    AuditService.log_action(
        action='settings_update',
        resource_type='settings',
        resource_name='Email/SMTP Settings',
        details='Updated email/SMTP settings',
        success=True
    )
    
    return success_response(
        data={'id': smtp.id},
        message='Email settings updated successfully'
    )


@bp.route('/api/v2/settings/email/test', methods=['POST'])
@require_auth(['write:settings'])
def test_email():
    """Send test email"""
    from services.notification_service import NotificationService
    
    data = request.json
    email = data.get('email') if data else None
    
    if not email:
        return error_response('Email address required', 400)
    
    # Try to send test email
    success, message = NotificationService.send_test_email_with_detail(email)
    
    if success:
        return success_response(
            data={'sent': True, 'to': email},
            message='Test email sent successfully'
        )
    else:
        return error_response(message or 'Failed to send test email', 500)


# -----------------------------------------------------------------------------
# SMTP OAuth2 (XOAUTH2) — Authorization Code + Refresh Token flow
# -----------------------------------------------------------------------------

def _default_oauth_redirect_uri() -> str:
    """Compute the default redirect URI from the current request host."""
    # request.host_url ends with '/'
    return f"{request.host_url}api/v2/settings/email/oauth/callback"


@bp.route('/api/v2/settings/email/oauth/providers', methods=['GET'])
@require_auth(['read:settings'])
def smtp_oauth_providers():
    """Return the static OAuth provider presets (host/port/tenant defaults).

    Used by the frontend to auto-fill SMTP host/port/TLS when the admin picks
    Gmail / Outlook personal / Microsoft 365. Public to authenticated admins;
    no secrets exposed.
    """
    from services.smtp_oauth import PROVIDERS
    presets = {}
    for key, p in PROVIDERS.items():
        presets[key] = {
            'smtp_host': p.smtp_host,
            'smtp_port': p.smtp_port,
            'smtp_use_tls': p.smtp_use_tls,
            'smtp_use_ssl': p.smtp_use_ssl,
            'needs_tenant': p.needs_tenant,
            'default_tenant': 'common' if key == 'microsoft365' else ('consumers' if key == 'microsoft' else None),
        }
    return success_response(data={'providers': presets})


@bp.route('/api/v2/settings/email/oauth/authorize-url', methods=['POST'])
@require_auth(['write:settings'])
def smtp_oauth_authorize_url():
    """Build the OAuth consent URL and stash ``state`` in the user session.

    Body (optional): {"redirect_uri": "https://..."} to override default.
    Returns: {"authorize_url": "...", "redirect_uri": "..."}
    """
    from flask import session
    from models.email_notification import SMTPConfig
    from services import smtp_oauth as oauth_helper

    smtp = SMTPConfig.query.first()
    if not smtp:
        return error_response('SMTP configuration not found — save settings first', 404)

    data = request.json or {}
    redirect_uri = (
        data.get('redirect_uri')
        or smtp.smtp_oauth_redirect_uri
        or _default_oauth_redirect_uri()
    )

    try:
        url, state = oauth_helper.build_authorize_url(smtp, redirect_uri)
    except ValueError as e:
        return error_response(str(e), 400)
    except Exception as e:
        logger.error(f"Failed to build OAuth authorize URL: {e}")
        return error_response('Failed to build authorize URL', 500)

    # Persist state + redirect_uri so the callback can verify them.
    session['smtp_oauth_state'] = state
    session['smtp_oauth_redirect_uri'] = redirect_uri

    AuditService.log_action(
        action='smtp_oauth_authorize_init',
        resource_type='settings',
        resource_name='SMTP OAuth',
        details=f'Initiated OAuth consent for provider {smtp.smtp_oauth_provider}',
        success=True,
    )
    return success_response(data={'authorize_url': url, 'redirect_uri': redirect_uri})


@bp.route('/api/v2/settings/email/oauth/callback', methods=['GET'])
@require_auth(['write:settings'])
def smtp_oauth_callback():
    """Receive the OAuth redirect, exchange ``code`` for tokens, persist refresh_token.

    Renders a tiny HTML page (popup-friendly) instead of JSON so the
    provider redirect lands cleanly in the browser.
    """
    from flask import session, make_response
    from models.email_notification import SMTPConfig
    from services import smtp_oauth as oauth_helper

    code = request.args.get('code')
    state = request.args.get('state')
    err = request.args.get('error')

    def _html(title: str, message: str, ok: bool = True) -> 'flask.Response':
        body = f"""<!doctype html><html><head><meta charset=utf-8>
<title>{title}</title><style>body{{font-family:system-ui,sans-serif;padding:2rem;text-align:center}}
.ok{{color:#16a34a}}.err{{color:#dc2626}}</style></head>
<body><h2 class="{'ok' if ok else 'err'}">{title}</h2><p>{message}</p>
<p><small>You can close this window.</small></p>
<script>(function(){{var ok={str(ok).lower()};var msg={{type:'smtp-oauth',ok:ok}};try{{window.opener&&window.opener.postMessage(msg,'*');}}catch(e){{}}try{{var bc=new BroadcastChannel('smtp-oauth');bc.postMessage(msg);bc.close();}}catch(e){{}}setTimeout(function(){{try{{window.close();}}catch(e){{}}}},1200);}})();</script>
</body></html>"""
        resp = make_response(body, 200 if ok else 400)
        resp.headers['Content-Type'] = 'text/html; charset=utf-8'
        return resp

    if err:
        logger.warning(f"OAuth callback returned error: {err}")
        return _html('Authorization failed', f'Provider error: {err}', ok=False)

    if not code or not state:
        return _html('Authorization failed', 'Missing code or state parameter', ok=False)

    expected_state = session.pop('smtp_oauth_state', None)
    redirect_uri = session.pop('smtp_oauth_redirect_uri', None)
    if not expected_state or state != expected_state:
        logger.warning('OAuth callback state mismatch — possible CSRF')
        return _html('Authorization failed', 'State mismatch — please retry', ok=False)
    if not redirect_uri:
        return _html('Authorization failed', 'Missing redirect URI in session', ok=False)

    smtp = SMTPConfig.query.first()
    if not smtp:
        return _html('Authorization failed', 'SMTP configuration not found', ok=False)

    try:
        payload = oauth_helper.exchange_code_for_tokens(smtp, code, redirect_uri)
    except Exception as e:
        logger.error(f"OAuth code exchange failed: {e}")
        return _html('Authorization failed', 'Token exchange failed — see server logs', ok=False)

    refresh_token = payload.get('refresh_token')
    if not refresh_token:
        # Provider didn't issue one — usually means user already consented and
        # we forgot prompt=consent, or it's a non-offline scope.
        return _html(
            'Authorization incomplete',
            'No refresh_token received — revoke prior consent in your provider account and retry.',
            ok=False,
        )

    smtp.smtp_oauth_refresh_token = refresh_token
    try:
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        logger.error(f"Failed to persist OAuth refresh_token: {e}")
        return _html('Authorization failed', 'Database error', ok=False)

    # Drop any stale cached access_token from before the new consent.
    oauth_helper.invalidate_cache(smtp.id)

    AuditService.log_action(
        action='smtp_oauth_authorize_complete',
        resource_type='settings',
        resource_name='SMTP OAuth',
        details=f'OAuth consent completed for provider {smtp.smtp_oauth_provider}',
        success=True,
    )
    return _html('Authorization successful', 'SMTP OAuth refresh token stored.', ok=True)


@bp.route('/api/v2/settings/email/oauth/revoke', methods=['POST'])
@require_auth(['write:settings'])
def smtp_oauth_revoke():
    """Drop the stored refresh_token and cached access_token."""
    from models.email_notification import SMTPConfig
    from services import smtp_oauth as oauth_helper

    smtp = SMTPConfig.query.first()
    if not smtp:
        return error_response('SMTP configuration not found', 404)

    smtp.smtp_oauth_refresh_token = None
    try:
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        logger.error(f"Failed to revoke OAuth refresh_token: {e}")
        return error_response('Failed to revoke', 500)

    oauth_helper.invalidate_cache(smtp.id)

    AuditService.log_action(
        action='smtp_oauth_revoke',
        resource_type='settings',
        resource_name='SMTP OAuth',
        details='Revoked stored OAuth refresh token',
        success=True,
    )
    return success_response(message='OAuth credentials revoked')


@bp.route('/api/v2/settings/email/template', methods=['GET'])
@require_auth(['read:settings'])
def get_email_template():
    """Get email template (custom or default)"""
    from models.email_notification import SMTPConfig
    from services.email_templates import get_default_template, get_default_text_template
    
    smtp = SMTPConfig.query.first()
    custom_html = smtp.email_template if smtp else None
    custom_text = smtp.email_text_template if smtp else None
    
    return success_response(data={
        'template': custom_html or get_default_template(),
        'text_template': custom_text or get_default_text_template(),
        'is_custom': bool(custom_html),
        'is_text_custom': bool(custom_text),
        'default_template': get_default_template(),
        'default_text_template': get_default_text_template()
    })


@bp.route('/api/v2/settings/email/template', methods=['PATCH'])
@require_auth(['write:settings'])
def update_email_template():
    """Update email template (HTML and/or text)"""
    from models.email_notification import SMTPConfig
    
    data = request.json
    if not data:
        return error_response('No data provided', 400)
    
    smtp = SMTPConfig.query.first()
    if not smtp:
        smtp = SMTPConfig()
        db.session.add(smtp)
    
    if 'template' in data:
        smtp.email_template = data['template']
    if 'text_template' in data:
        smtp.email_text_template = data['text_template']
    try:
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        logger.error(f"Failed to update email template: {e}")
        return error_response('Failed to update email template', 500)
    
    AuditService.log_action(
        action='settings_update',
        resource_type='settings',
        resource_name='Email Template',
        details='Updated email template',
        success=True
    )
    
    return success_response(message='Email template updated')


@bp.route('/api/v2/settings/email/template/reset', methods=['POST'])
@require_auth(['write:settings'])
def reset_email_template():
    """Reset email template to default (HTML and text)"""
    from models.email_notification import SMTPConfig
    
    smtp = SMTPConfig.query.first()
    if smtp:
        smtp.email_template = None
        smtp.email_text_template = None
        try:
            db.session.commit()
        except Exception as e:
            db.session.rollback()
            logger.error(f"Failed to reset email template: {e}")
            return error_response('Failed to reset email template', 500)
    
    AuditService.log_action(
        action='settings_update',
        resource_type='settings',
        resource_name='Email Template',
        details='Reset email template to default',
        success=True
    )
    
    return success_response(message='Email template reset to default')


@bp.route('/api/v2/settings/email/template/preview', methods=['POST'])
@require_auth(['read:settings'])
def preview_email_template():
    """Preview email template with sample data"""
    from services.email_templates import render_template, render_text_template
    
    data = request.json
    template = data.get('template', '') if data else ''
    template_type = data.get('type', 'html') if data else 'html'
    
    sample_content = """
    <p style="font-size:15px;color:#374151;line-height:1.7;margin:0 0 16px;">This is a <strong>preview</strong> of your email template.</p>
    <p style="font-size:15px;color:#374151;line-height:1.7;margin:0 0 16px;">Variables like <code>{{title}}</code>, <code>{{content}}</code>, and <code>{{logo}}</code> are replaced automatically.</p>
    <div style="background-color:#f0f9ff;border:1px solid #bae6fd;border-radius:8px;padding:16px;margin:20px 0;">
        <p style="margin:0;font-size:14px;color:#0369a1;font-weight:500;">📋 Sample notification content would appear here.</p>
    </div>
    """
    
    if template_type == 'text':
        text = render_text_template(template, "Template Preview", sample_content)
        return success_response(data={'text': text})
    else:
        html = render_template(template, "Template Preview", "#3b82f6", sample_content)
        return success_response(data={'html': html})


# ============================================================================
# Notification Settings
# ============================================================================

@bp.route('/api/v2/settings/notifications', methods=['GET'])
@require_auth(['read:settings'])
def get_notification_settings():
    """Get notification configurations"""
    from models.email_notification import NotificationConfig
    import json
    
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
    import json
    
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
            'sent_at': log.sent_at.isoformat() if log.sent_at else None,
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


# ============================================================================
# LDAP Integration
# ============================================================================

@bp.route('/api/v2/settings/ldap', methods=['GET'])
@require_auth(['read:settings'])
def get_ldap_settings():
    """Get LDAP configuration"""
    return success_response(
        data={
            'enabled': False,
            'server': None,
            'port': 389,
            'use_ssl': False,
            'base_dn': None,
            'bind_dn': None,
            'user_filter': '(uid={username})',
            'sync_enabled': False
        }
    )


@bp.route('/api/v2/settings/ldap', methods=['PATCH'])
@require_auth(['write:settings'])
def update_ldap_settings():
    """Update LDAP configuration"""
    from models import SystemConfig, db
    
    data = request.json
    
    if not data:
        return error_response('No data provided', 400)
    
    # Save each LDAP setting — allowlist to prevent arbitrary key injection
    ALLOWED_LDAP_KEYS = {
        'server', 'port', 'use_ssl', 'use_starttls', 'base_dn', 'bind_dn',
        'bind_password', 'user_filter', 'username_attribute', 'email_attribute',
        'display_name_attribute', 'group_filter', 'group_attribute',
        'sync_enabled', 'sync_interval', 'default_role', 'enabled',
        'timeout', 'verify_ssl', 'ca_cert'
    }
    for key, value in data.items():
        if key not in ALLOWED_LDAP_KEYS:
            continue
        config = SystemConfig.query.filter_by(key=f'ldap_{key}').first()
        if config:
            config.value = str(value) if value is not None else ''
        else:
            config = SystemConfig(key=f'ldap_{key}', value=str(value) if value is not None else '')
            db.session.add(config)
    
    try:
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        logger.error(f"Failed to update LDAP settings: {e}")
        return error_response('Failed to update LDAP settings', 500)
    
    AuditService.log_action(
        action='settings_update',
        resource_type='settings',
        resource_name='LDAP Settings',
        details='Updated LDAP settings',
        success=True
    )
    
    return success_response(
        data=data,
        message='LDAP settings updated successfully'
    )


@bp.route('/api/v2/settings/ldap/test', methods=['POST'])
@require_auth(['write:settings'])
def test_ldap_connection():
    """Test LDAP connection"""
    data = request.json or {}
    
    # LDAP testing requires ldap3 library
    try:
        import ldap3
        from ldap3 import Server, Connection, ALL
        
        server_url = data.get('server', 'localhost')
        port = data.get('port', 389)
        use_ssl = data.get('use_ssl', False)
        bind_dn = data.get('bind_dn')
        bind_password = data.get('bind_password')
        
        server = Server(server_url, port=port, use_ssl=use_ssl, get_info=ALL)
        conn = Connection(server, bind_dn, bind_password, auto_bind=True)
        
        return success_response(
            data={'connected': True, 'server_info': str(server.info)},
            message='LDAP connection successful'
        )
    except ImportError:
        return error_response('LDAP support not installed (pip install ldap3)', 501)
    except Exception as e:
        logger.error(f"LDAP connection test failed: {e}")
        return error_response('LDAP connection failed', 400)


# ============================================================================
# Webhooks (stored as JSON in SystemConfig)
# ============================================================================

def get_webhooks():
    """Get webhooks from SystemConfig"""
    import json
    config = SystemConfig.query.filter_by(key='webhooks').first()
    if config and config.value:
        try:
            return json.loads(config.value)
        except Exception:
            return []
    return []


def save_webhooks(webhooks):
    """Save webhooks to SystemConfig"""
    import json
    config = SystemConfig.query.filter_by(key='webhooks').first()
    if config:
        config.value = json.dumps(webhooks)
    else:
        config = SystemConfig(key='webhooks', value=json.dumps(webhooks))
        db.session.add(config)
    try:
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        logger.error(f"Failed to save webhooks: {e}")
        raise


@bp.route('/api/v2/settings/webhooks', methods=['GET'])
@require_auth(['read:settings'])
def list_webhooks():
    """List configured webhooks"""
    webhooks = get_webhooks()
    return success_response(data=webhooks, meta={'total': len(webhooks)})


@bp.route('/api/v2/settings/webhooks', methods=['POST'])
@require_auth(['write:settings'])
def create_webhook():
    """Create webhook"""
    from datetime import datetime, timezone
    data = request.json
    
    if not data or not data.get('name'):
        return error_response('Webhook name required', 400)
    
    if not data.get('url'):
        return error_response('Webhook URL required', 400)

    # Narrow SSRF guard — internal webhooks (Slack/Teams/Mattermost on LAN)
    # are legitimate. Block only cloud metadata + loopback.
    try:
        validate_url_not_cloud_metadata(data['url'])
    except ValueError:
        return error_response('Webhook URL must not target cloud metadata services or loopback', 400)

    if not data.get('events'):
        return error_response('At least one event required', 400)
    
    # Get existing webhooks
    webhooks = get_webhooks()
    
    # Generate new ID
    new_id = max([w.get('id', 0) for w in webhooks], default=0) + 1
    
    new_webhook = {
        'id': new_id,
        'name': data['name'],
        'url': data['url'],
        'events': data['events'],
        'enabled': data.get('enabled', True),
        'created_at': datetime.now(timezone.utc).isoformat()
    }
    
    webhooks.append(new_webhook)
    save_webhooks(webhooks)
    
    AuditService.log_action(
        action='webhook_create',
        resource_type='webhook',
        resource_id=str(new_id),
        resource_name=new_webhook['name'],
        details=f'Created webhook: {new_webhook["name"]}',
        success=True
    )
    
    return created_response(
        data=new_webhook,
        message='Webhook created successfully'
    )


@bp.route('/api/v2/settings/webhooks/<int:webhook_id>', methods=['DELETE'])
@require_auth(['delete:settings'])
def delete_webhook(webhook_id):
    """Delete webhook"""
    webhooks = get_webhooks()
    webhooks = [w for w in webhooks if w.get('id') != webhook_id]
    save_webhooks(webhooks)
    
    AuditService.log_action(
        action='webhook_delete',
        resource_type='webhook',
        resource_id=str(webhook_id),
        resource_name=f'Webhook {webhook_id}',
        details=f'Deleted webhook {webhook_id}',
        success=True
    )
    
    from utils.response import no_content_response
    return no_content_response()


@bp.route('/api/v2/settings/webhooks/<int:webhook_id>/test', methods=['POST'])
@require_auth(['write:settings'])
def test_webhook(webhook_id):
    """Test webhook by sending a test event"""
    import requests as http_requests
    
    webhooks = get_webhooks()
    webhook = next((w for w in webhooks if w.get('id') == webhook_id), None)
    
    if not webhook:
        return error_response('Webhook not found', 404)

    # Re-validate stored URL before sending (defense-in-depth, narrow guard)
    try:
        validate_url_not_cloud_metadata(webhook['url'])
    except ValueError as e:
        logger.warning(f"Blocked test of webhook {webhook_id} — URL targets cloud metadata or loopback: {e}")
        return error_response('Webhook URL targets cloud metadata services or loopback', 400)

    test_payload = {
        'event': 'test',
        'timestamp': datetime.now(timezone.utc).isoformat(),
        'data': {'message': 'This is a test webhook from UCM'}
    }
    
    try:
        response = http_requests.post(
            webhook['url'],
            json=test_payload,
            timeout=10,
            headers={'Content-Type': 'application/json', 'User-Agent': 'UCM-Webhook/2.0'}
        )
        return success_response(
            data={'sent': True, 'status_code': response.status_code},
            message=f'Test webhook sent (status: {response.status_code})'
        )
    except Exception as e:
        logger.error(f"Failed to send test webhook: {e}")
        return error_response('Failed to send webhook', 500)


# ============================================================================
# Scheduled Backups
# ============================================================================

@bp.route('/api/v2/settings/backup/schedule', methods=['GET'])
@require_auth(['read:settings'])
def get_backup_schedule():
    """Get backup schedule configuration"""
    return success_response(
        data={
            'enabled': False,
            'frequency': 'daily',  # daily, weekly, monthly
            'time': '02:00',
            'retention_days': 30,
            'include_private_keys': False,
            'remote_storage': {
                'enabled': False,
                'type': None,  # s3, ftp, sftp
                'config': {}
            }
        }
    )


@bp.route('/api/v2/settings/backup/schedule', methods=['PATCH'])
@require_auth(['admin:system'])
def update_backup_schedule():
    """Update backup schedule"""
    data = request.json
    
    if not data:
        return error_response('No data provided', 400)
    
    # TODO: Validate and update schedule
    # - Validate frequency, time format
    # - Update cron job
    # - Save to database
    
    return success_response(
        data=data,
        message='Backup schedule updated successfully'
    )


@bp.route('/api/v2/settings/backup/history', methods=['GET'])
@require_auth(['read:settings'])
def get_backup_history():
    """Get backup history"""
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 20, type=int)
    
    # TODO: Get backup history from database
    
    return success_response(
        data=[
            {
                'id': 1,
                'filename': 'ucm_backup_20260119.tar.gz',
                'size': 1024000,
                'created_at': '2026-01-19T02:00:00Z',
                'type': 'scheduled',
                'status': 'completed'
            }
        ],
        meta={'total': 1, 'page': page, 'per_page': per_page}
    )


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
