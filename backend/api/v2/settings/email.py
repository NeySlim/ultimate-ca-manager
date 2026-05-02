"""
Settings - Email/SMTP settings + OAuth2 + template routes
"""

from flask import request
from auth.unified import require_auth
from utils.response import success_response, error_response
from utils.ssrf_protection import validate_url_not_cloud_metadata
from models import db
from services.audit_service import AuditService
import logging

from . import bp

logger = logging.getLogger(__name__)


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
