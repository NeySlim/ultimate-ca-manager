from . import bp, VALID_ROLES
from flask import request, redirect, session, Response
from auth.unified import require_auth
from utils.response import success_response, error_response
from models import db, User
from models.sso import SSOProvider, SSOSession
from services.audit_service import AuditService
from utils.datetime_utils import utc_now
from datetime import timedelta
import secrets as py_secrets
import base64
import urllib.parse
import hmac
from .helpers import _check_ldap_lockout, _clear_ldap_failed_attempts, _record_ldap_failed_attempt, _resolve_role_from_mapping, _resolve_role, _parse_json_field

# ============ Public SSO Endpoints (no auth) ============

@bp.route('/api/v2/sso/available', methods=['GET'])
def get_available_providers():
    """Get list of enabled SSO providers for login page"""
    providers = SSOProvider.query.filter_by(enabled=True).all()

    return success_response(data=[{
        'id': p.id,
        'name': p.name,
        'display_name': p.display_name or p.name,
        'provider_type': p.provider_type,
        'icon': p.icon,
        'is_default': p.is_default,
        'login_url': f'/api/v2/sso/login/{p.provider_type}' if p.provider_type != 'ldap' else None
    } for p in providers])


@bp.route('/api/v2/sso/login/<provider_type>', methods=['GET'])
def initiate_sso_login(provider_type):
    """
    Initiate SSO login flow.
    For OAuth2: redirects to authorization URL
    For SAML: redirects to IdP SSO URL
    For LDAP: returns error (LDAP uses direct auth via /api/v2/sso/ldap/login)
    """
    if provider_type not in ('saml', 'oauth2'):
        return error_response("Use /api/v2/sso/ldap/login for LDAP authentication", 400)

    provider = SSOProvider.query.filter_by(provider_type=provider_type, enabled=True).first()
    if not provider:
        return error_response(f"No enabled {provider_type.upper()} provider found", 404)

    # Generate state token for CSRF protection
    state = py_secrets.token_urlsafe(32)
    session['sso_state'] = state
    session['sso_provider_id'] = provider.id

    if provider.provider_type == 'oauth2':
        # Build OAuth2 authorization URL
        scopes = json.loads(provider.oauth2_scopes) if provider.oauth2_scopes else ['openid', 'profile', 'email']

        callback_url = request.url_root.rstrip('/') + '/api/v2/sso/callback/oauth2'

        params = {
            'client_id': provider.oauth2_client_id,
            'redirect_uri': callback_url,
            'response_type': 'code',
            'scope': ' '.join(scopes),
            'state': state
        }

        auth_url = provider.oauth2_auth_url + '?' + urllib.parse.urlencode(params)
        return redirect(auth_url)

    elif provider.provider_type == 'saml':
        # For SAML, generate proper AuthnRequest
        if not provider.saml_sso_url:
            return error_response("SAML SSO URL not configured", 400)

        try:
            saml_auth = _get_saml_auth(request, provider, state)
            redirect_url = saml_auth.login()
            return redirect(redirect_url)
        except Exception as e:
            logger.error(f"SAML login initiation error: {e}")
            return error_response("SAML login failed. Check SAML configuration.", 500)

    return error_response("Unknown provider type", 400)


@bp.route('/api/v2/sso/callback/<provider_type>', methods=['GET', 'POST'])
def sso_callback(provider_type):
    """
    Handle SSO callback from OAuth2/SAML providers.
    Creates or updates user and establishes session.
    """
    if provider_type not in ('saml', 'oauth2'):
        return redirect('/login?error=invalid_provider_type')

    provider = SSOProvider.query.filter_by(provider_type=provider_type, enabled=True).first()
    if not provider:
        return redirect('/login?error=provider_not_found')

    # Verify state for CSRF protection (OAuth2 only — SAML uses its own mechanisms)
    if provider_type == 'oauth2':
        state = request.args.get('state')
        stored_state = session.get('sso_state', '')
        if not state or not hmac.compare_digest(state, stored_state):
            return redirect('/login?error=invalid_state')

    if provider.provider_type == 'oauth2':
        code = request.args.get('code')
        if not code:
            error = request.args.get('error', 'no_code')
            return redirect(f'/login?error={error}')

        try:
            # Exchange code for token
            callback_url = request.url_root.rstrip('/') + '/api/v2/sso/callback/oauth2'

            verify = _get_ssl_verify(provider, 'oauth2')
            token_response = http_requests.post(
                provider.oauth2_token_url,
                data={
                    'grant_type': 'authorization_code',
                    'code': code,
                    'redirect_uri': callback_url,
                    'client_id': provider.oauth2_client_id,
                    'client_secret': provider.oauth2_client_secret
                },
                timeout=10,
                verify=verify
            )

            if not token_response.ok:
                logger.error(f"OAuth2 token exchange failed: {token_response.text}")
                return redirect('/login?error=token_exchange_failed')

            tokens = token_response.json()
            access_token = tokens.get('access_token')

            if not access_token:
                return redirect('/login?error=no_access_token')

            # Get user info
            userinfo_response = http_requests.get(
                provider.oauth2_userinfo_url,
                headers={'Authorization': f'Bearer {access_token}'},
                timeout=10,
                verify=verify
            )

            if not userinfo_response.ok:
                return redirect('/login?error=userinfo_failed')

            userinfo = userinfo_response.json()

            # Map attributes
            attr_mapping = _parse_json_field(provider.attribute_mapping)
            username = userinfo.get(attr_mapping.get('username', 'preferred_username')) or userinfo.get('email', '').split('@')[0]
            email = userinfo.get(attr_mapping.get('email', 'email'), '')
            fullname = userinfo.get(attr_mapping.get('fullname', 'name'), '')

            if not username:
                return redirect('/login?error=no_username')

            # Create or update user
            user, error_code = _get_or_create_sso_user(provider, username, email, fullname, userinfo)

            if not user:
                return redirect(f'/login?error={error_code or "user_creation_failed"}')

            # Create or update SSO session for audit
            session_id = userinfo.get('sub', username)
            sso_session = SSOSession.query.filter_by(session_id=session_id).first()
            if sso_session:
                sso_session.expires_at = utc_now() + timedelta(hours=8)
            else:
                sso_session = SSOSession(
                    user_id=user.id,
                    provider_id=provider.id,
                    session_id=session_id,
                    sso_name_id=session_id,
                    expires_at=utc_now() + timedelta(hours=8)
                )
                db.session.add(sso_session)
            db.session.commit()

            # Establish Flask session (clear first to prevent session fixation)
            _sso_now = utc_now()
            session.clear()
            session['user_id'] = user.id
            session['username'] = user.username
            session['role'] = user.role
            session['auth_method'] = 'sso'
            session['login_time'] = _sso_now.isoformat()
            session['last_activity'] = _sso_now.isoformat()
            session.permanent = True

            # SEC-07: Audit log SSO login
            AuditService.log_action(
                action='login_success',
                resource_type='user',
                resource_id=user.id,
                resource_name=user.username,
                details=f'OAuth2 SSO login via {provider.name}',
                success=True,
                username=user.username
            )

            # Redirect to app (session cookie is set automatically)
            return redirect('/login/sso-complete')

        except Exception as e:
            logger.error(f"OAuth2 callback error: {e}\n{traceback.format_exc()}")
            AuditService.log_action(
                action='login_failure',
                resource_type='sso',
                details=f'OAuth2 callback error for provider {provider.name}',
                success=False
            )
            return redirect('/login?error=callback_error')
        finally:
            _cleanup_ssl_verify(verify)

    elif provider.provider_type == 'saml':
        try:
            saml_auth = _get_saml_auth(request, provider)
            attrs = {}
            name_id = ''

            # SECURITY: NEVER fall back to an unsigned XML parser here.
            # python3-saml handles signature + assertion validation. If it raises,
            # the response is untrusted — we must reject, not parse manually.
            # (Previous fallback allowed SAML auth bypass — CVE-level issue.)
            try:
                saml_auth.process_response()
            except Exception as saml_err:
                logger.error(f"SAML response processing failed: {saml_err}")
                AuditService.log_action(
                    action='login_failure',
                    resource_type='sso',
                    details=f'SAML response rejected (parse error) for provider {provider.name}',
                    success=False
                )
                return redirect('/login?error=saml_validation_failed')

            errors = saml_auth.get_errors()
            if errors:
                logger.error(f"SAML errors: {errors}, reason: {saml_auth.get_last_error_reason()}")
                AuditService.log_action(
                    action='login_failure',
                    resource_type='sso',
                    details=f'SAML validation errors for provider {provider.name}: {errors}',
                    success=False
                )
                return redirect('/login?error=saml_validation_failed')

            # Only reached after signature + assertion verification succeeded
            attrs = saml_auth.get_attributes()
            name_id = saml_auth.get_nameid()

            # Map attributes
            attr_mapping = _parse_json_field(provider.attribute_mapping)

            username_key = attr_mapping.get('username', 'username')
            email_key = attr_mapping.get('email', 'email')
            fullname_key = attr_mapping.get('fullname', 'name')

            # SAML attributes are lists
            username = (attrs.get(username_key, [None])[0] or name_id or '').strip()
            email = (attrs.get(email_key, [None])[0] or '').strip()
            fullname = (attrs.get(fullname_key, [None])[0] or '').strip()

            if not username:
                return redirect('/login?error=no_username')

            # Create or update user
            user, error_code = _get_or_create_sso_user(
                provider, username, email, fullname,
                {'name_id': name_id, 'attributes': {k: v for k, v in attrs.items()}}
            )

            if not user:
                return redirect(f'/login?error={error_code or "user_creation_failed"}')

            # Track SSO session
            sso_session = SSOSession.query.filter_by(session_id=name_id).first()
            if sso_session:
                sso_session.expires_at = utc_now() + timedelta(hours=8)
            else:
                sso_session = SSOSession(
                    user_id=user.id,
                    provider_id=provider.id,
                    session_id=name_id,
                    sso_name_id=name_id,
                    expires_at=utc_now() + timedelta(hours=8)
                )
                db.session.add(sso_session)
            db.session.commit()

            # Establish Flask session (clear first to prevent session fixation)
            _saml_now = utc_now()
            session.clear()
            session['user_id'] = user.id
            session['username'] = user.username
            session['role'] = user.role
            session['auth_method'] = 'sso'
            session['login_time'] = _saml_now.isoformat()
            session['last_activity'] = _saml_now.isoformat()
            session.permanent = True

            # SEC-07: Audit log SAML SSO login
            AuditService.log_action(
                action='login_success',
                resource_type='user',
                resource_id=user.id,
                resource_name=user.username,
                details=f'SAML SSO login via {provider.name}',
                success=True,
                username=user.username
            )

            return redirect('/login/sso-complete')

        except Exception as e:
            logger.error(f"SAML callback error: {e}\n{traceback.format_exc()}")
            AuditService.log_action(
                action='login_failure',
                resource_type='sso',
                details=f'SAML callback error for provider {provider.name}',
                success=False
            )
            return redirect('/login?error=callback_error')

    return redirect('/login?error=unknown_provider_type')
