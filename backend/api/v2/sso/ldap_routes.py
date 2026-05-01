from . import bp, VALID_ROLES, logger
from flask import request
from auth.unified import require_auth
from utils.response import success_response, error_response
from models import db, User
from models.sso import SSOProvider, SSOSession
from services.audit_service import AuditService
from utils.datetime_utils import utc_now
from datetime import timedelta
import ldap3
from ldap3 import Server, Connection, ALL, Tls
from ldap3.utils.conv import escape_filter_chars
import ssl
from .helpers import _check_ldap_lockout, _clear_ldap_failed_attempts, _record_ldap_failed_attempt, _resolve_role_from_mapping, _resolve_role, _build_ldap_tls, _decrypt_ldap_password

@bp.route('/api/v2/sso/ldap/login', methods=['POST'])
def ldap_login():
    """
    Direct LDAP authentication.
    Unlike OAuth2/SAML, LDAP authenticates with username/password directly.
    """

    data = request.get_json()
    username = data.get('username')
    password = data.get('password')
    provider_id = data.get('provider_id')

    if not username or not password:
        return error_response("Username and password required", 400)

    # Check account lockout before attempting LDAP auth
    if _check_ldap_lockout(username):
        return error_response("Account temporarily locked due to too many failed attempts", 429)

    # Find LDAP provider
    if provider_id:
        provider = SSOProvider.query.get(provider_id)
    else:
        # Use first enabled LDAP provider
        provider = SSOProvider.query.filter_by(provider_type='ldap', enabled=True).first()

    if not provider:
        return error_response("No LDAP provider configured", 400)

    if not provider.enabled:
        return error_response("LDAP provider is disabled", 400)

    # Authenticate via LDAP
    user_info, error = _ldap_authenticate_user(provider, username, password)

    if error:
        _record_ldap_failed_attempt(username)
        # SEC-11: Audit log failed LDAP attempt
        AuditService.log_action(
            action='login_failure',
            resource_type='user',
            details=f'LDAP authentication failed for {username}',
            success=False,
            username=username
        )
        return error_response("Invalid credentials", 401)

    # Create or update user
    user, error_code = _get_or_create_sso_user(
        provider,
        user_info['username'],
        user_info.get('email', ''),
        user_info.get('fullname', ''),
        user_info
    )

    if not user:
        if error_code == 'auto_create_disabled':
            return error_response("User not found and automatic account creation is disabled. Contact your administrator.", 403)
        return error_response("Failed to create user account", 500)

    # Clear failed attempts on successful login
    _clear_ldap_failed_attempts(username)

    # Create or update session (deduplicate like OAuth2/SAML)
    session_id = user_info['dn']
    sso_session = SSOSession.query.filter_by(session_id=session_id).first()
    if sso_session:
        sso_session.expires_at = utc_now() + timedelta(hours=8)
    else:
        sso_session = SSOSession(
            user_id=user.id,
            provider_id=provider.id,
            session_id=session_id,
            sso_name_id=user_info.get('uid', session_id),
            expires_at=utc_now() + timedelta(hours=8)
        )
        db.session.add(sso_session)
    db.session.commit()

    # Establish Flask session (clear first to prevent session fixation)
    _ldap_now = utc_now()
    session.clear()
    session['user_id'] = user.id
    session['username'] = user.username
    session['role'] = user.role
    session['auth_method'] = 'ldap'
    session['login_time'] = _ldap_now.isoformat()
    session['last_activity'] = _ldap_now.isoformat()
    session.permanent = True

    # Audit log LDAP login success
    AuditService.log_action(
        action='login_success',
        resource_type='user',
        resource_id=user.id,
        resource_name=user.username,
        details=f'LDAP login via {provider.name}',
        success=True,
        username=user.username
    )

    # Generate CSRF token
    csrf_token = None
    try:
        from security.csrf import CSRFProtection
        csrf_token = CSRFProtection.generate_token(user.id)
    except ImportError:
        pass

    # Get role permissions
    from auth.permissions import get_role_permissions
    permissions = get_role_permissions(user.role)

    # Get display settings for frontend
    from models import SystemConfig
    tz_row = SystemConfig.query.filter_by(key='timezone').first()
    df_row = SystemConfig.query.filter_by(key='date_format').first()
    st_row = SystemConfig.query.filter_by(key='show_time').first()

    return success_response(
        data={
            'user': user.to_dict(),
            'role': user.role,
            'permissions': permissions,
            'csrf_token': csrf_token,
            'timezone': tz_row.value if tz_row else 'UTC',
            'date_format': df_row.value if df_row else 'short',
            'show_time': st_row.value != 'false' if st_row else True,
        },
        message='LDAP authentication successful'
    )


def _get_saml_auth(flask_request, provider, relay_state=None):
    """Build a OneLogin_Saml2_Auth from Flask request and SSO provider config."""
    from onelogin.saml2.auth import OneLogin_Saml2_Auth

    # Build request dict for python3-saml
    url_data = urllib.parse.urlparse(flask_request.url)
    req = {
        'https': 'on' if url_data.scheme == 'https' else 'off',
        'http_host': flask_request.host,
        'script_name': flask_request.path,
        'get_data': flask_request.args.copy(),
        'post_data': flask_request.form.copy(),
        'server_port': url_data.port or (443 if url_data.scheme == 'https' else 80),
    }

    sp_base = flask_request.url_root.rstrip('/')

    saml_settings = {
        'strict': False,
        'debug': True,
        'sp': {
            'entityId': f'{sp_base}/api/v2/sso',
            'assertionConsumerService': {
                'url': f'{sp_base}/api/v2/sso/callback/saml',
                'binding': 'urn:oasis:names:tc:SAML:2.0:bindings:HTTP-POST',
            },
            'singleLogoutService': {
                'url': f'{sp_base}/api/v2/sso/callback/saml',
                'binding': 'urn:oasis:names:tc:SAML:2.0:bindings:HTTP-Redirect',
            },
            'NameIDFormat': getattr(provider, 'saml_name_id_format', None) or 'urn:oasis:names:tc:SAML:1.1:nameid-format:unspecified',
        },
        'idp': {
            'entityId': provider.saml_entity_id,
            'singleSignOnService': {
                'url': provider.saml_sso_url,
                'binding': 'urn:oasis:names:tc:SAML:2.0:bindings:HTTP-Redirect',
            },
            'x509cert': provider.saml_certificate or '',
        },
        'security': {
            'wantAssertionsSigned': False,
            'wantMessagesSigned': False,
            'authnRequestsSigned': False,
            'wantNameIdEncrypted': False,
            'wantAssertionsEncrypted': False,
            'requestedAuthnContext': False,
            'allowSingleLabelDomains': True,
        },
    }

    if provider.saml_slo_url:
        saml_settings['idp']['singleLogoutService'] = {
            'url': provider.saml_slo_url,
            'binding': 'urn:oasis:names:tc:SAML:2.0:bindings:HTTP-Redirect',
        }

    return OneLogin_Saml2_Auth(req, saml_settings)


def _get_or_create_sso_user(provider, username, email, fullname, external_data):
    """Create or update a user from SSO authentication

    Returns:
        tuple: (user, error_code) - user object or None, and error code if failed
    """
    user = User.query.filter_by(username=username).first()

    if user:
        # Backfill auth_source/sso_provider_id for users created before
        # migration 024 — useful when several providers share a directory
        # and the migration could not infer the right one.
        if (user.auth_source or 'local') == 'local' and user.password_hash == '!SSO_NO_PASSWORD!':
            user.auth_source = provider.provider_type
            user.sso_provider_id = provider.id
        elif user.sso_provider_id != provider.id and user.auth_source != 'local':
            # User logged in through a different SSO provider — record latest.
            user.sso_provider_id = provider.id
            user.auth_source = provider.provider_type

        # ── Userinfo sync (email, full name) ─────────────────────────────
        # Controlled by `auto_update_users`. Does NOT touch the role.
        if provider.auto_update_users:
            if email:
                user.email = email
            if fullname:
                user.full_name = fullname

        # ── Role sync ────────────────────────────────────────────────────
        # See #81. Default behaviour: role is set at creation only and
        # then managed in the UCM UI. Re-sync on login is opt-in via
        # `sync_role_on_login` and only acts on an explicit role_mapping
        # match — never falls back to `default_role` for existing users.
        if provider.sync_role_on_login:
            mapped_role = _resolve_role_from_mapping(provider, external_data)
            if mapped_role is not None and user.role != mapped_role:
                logger.info(
                    f"SSO role sync: user {username} role changed "
                    f"{user.role} → {mapped_role} (mapping match)"
                )
                from services.audit_service import AuditService
                AuditService.log_action(
                    action='role_change',
                    resource_type='user',
                    resource_name=username,
                    username=username,
                    details=(
                        f"SSO role sync: role changed from {user.role} to "
                        f"{mapped_role} (role_mapping match)"
                    ),
                    success=True
                )
                user.role = mapped_role

        user.last_login = utc_now()
        try:
            db.session.commit()
        except Exception as e:
            db.session.rollback()
            logger.error(f"Failed to update SSO user {username}: {e}")
        return user, None

    # Create new user if auto_create is enabled
    if not provider.auto_create_users:
        logger.warning(f"SSO user {username} not found and auto_create disabled")
        return None, 'auto_create_disabled'

    # Creation path keeps the historical fallback to default_role.
    role = _resolve_role(provider, external_data)

    user = User(
        username=username,
        email=email or f'{username}@sso.local',
        full_name=fullname or username,
        role=role,
        active=True,
        last_login=utc_now(),
        auth_source=provider.provider_type,
        sso_provider_id=provider.id,
    )

    # SSO users don't have a password — use sentinel that cannot match any hash
    user.password_hash = '!SSO_NO_PASSWORD!'

    db.session.add(user)
    db.session.commit()

    logger.info(f"Created SSO user: {username} with role {role}")
    return user, None
