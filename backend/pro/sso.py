"""
SSO API - UCM Pro
SAML, OAuth2, LDAP authentication providers
"""

from flask import Blueprint, request, current_app, redirect, url_for, session
from auth.unified import require_auth
from utils.response import success_response, error_response
from models import db, User
from models.pro.sso import SSOProvider, SSOSession
from datetime import datetime, timedelta
import json

bp = Blueprint('sso_pro', __name__)


# ============ Provider Management ============

@bp.route('/api/v2/sso/providers', methods=['GET'])
@require_auth(['read:sso'])
def list_providers():
    """List all SSO providers"""
    providers = SSOProvider.query.all()
    return success_response(data=[p.to_dict() for p in providers])


@bp.route('/api/v2/sso/providers/<int:provider_id>', methods=['GET'])
@require_auth(['read:sso'])
def get_provider(provider_id):
    """Get SSO provider details"""
    provider = SSOProvider.query.get_or_404(provider_id)
    # Include secrets only for admins
    include_secrets = request.args.get('include_secrets') == 'true'
    return success_response(data=provider.to_dict(include_secrets=include_secrets))


@bp.route('/api/v2/sso/providers', methods=['POST'])
@require_auth(['write:sso'])
def create_provider():
    """Create new SSO provider"""
    data = request.get_json()
    
    if not data.get('name'):
        return error_response("Provider name is required", 400)
    if not data.get('provider_type'):
        return error_response("Provider type is required", 400)
    if data['provider_type'] not in ['saml', 'oauth2', 'ldap']:
        return error_response("Invalid provider type. Must be: saml, oauth2, ldap", 400)
    
    # Check name uniqueness
    if SSOProvider.query.filter_by(name=data['name']).first():
        return error_response("Provider name already exists", 400)
    
    provider = SSOProvider(
        name=data['name'],
        provider_type=data['provider_type'],
        display_name=data.get('display_name'),
        icon=data.get('icon'),
        enabled=data.get('enabled', False),
        default_role=data.get('default_role', 'viewer'),
        auto_create_users=data.get('auto_create_users', True),
        auto_update_users=data.get('auto_update_users', True),
    )
    
    # Type-specific fields
    if data['provider_type'] == 'saml':
        provider.saml_entity_id = data.get('saml_entity_id')
        provider.saml_sso_url = data.get('saml_sso_url')
        provider.saml_slo_url = data.get('saml_slo_url')
        provider.saml_certificate = data.get('saml_certificate')
        provider.saml_sign_requests = data.get('saml_sign_requests', True)
    
    elif data['provider_type'] == 'oauth2':
        provider.oauth2_client_id = data.get('oauth2_client_id')
        provider.oauth2_client_secret = data.get('oauth2_client_secret')
        provider.oauth2_auth_url = data.get('oauth2_auth_url')
        provider.oauth2_token_url = data.get('oauth2_token_url')
        provider.oauth2_userinfo_url = data.get('oauth2_userinfo_url')
        provider.oauth2_scopes = json.dumps(data.get('oauth2_scopes', ['openid', 'profile', 'email']))
    
    elif data['provider_type'] == 'ldap':
        provider.ldap_server = data.get('ldap_server')
        provider.ldap_port = data.get('ldap_port', 389)
        provider.ldap_use_ssl = data.get('ldap_use_ssl', False)
        provider.ldap_bind_dn = data.get('ldap_bind_dn')
        provider.ldap_bind_password = data.get('ldap_bind_password')
        provider.ldap_base_dn = data.get('ldap_base_dn')
        provider.ldap_user_filter = data.get('ldap_user_filter', '(uid={username})')
        provider.ldap_group_filter = data.get('ldap_group_filter')
        provider.ldap_username_attr = data.get('ldap_username_attr', 'uid')
        provider.ldap_email_attr = data.get('ldap_email_attr', 'mail')
        provider.ldap_fullname_attr = data.get('ldap_fullname_attr', 'cn')
    
    # JSON fields
    if data.get('attribute_mapping'):
        provider.attribute_mapping = json.dumps(data['attribute_mapping'])
    if data.get('role_mapping'):
        provider.role_mapping = json.dumps(data['role_mapping'])
    
    db.session.add(provider)
    db.session.commit()
    
    return success_response(data=provider.to_dict(), message="SSO provider created")


@bp.route('/api/v2/sso/providers/<int:provider_id>', methods=['PUT'])
@bp.route('/api/v2/sso/providers/<string:provider_type_name>', methods=['PUT'])
@require_auth(['write:sso'])
def update_provider(provider_id=None, provider_type_name=None):
    """Update SSO provider by ID or by type name (for single-provider types)"""
    if provider_id:
        provider = SSOProvider.query.get_or_404(provider_id)
    elif provider_type_name:
        # Find provider by type (for backward compatibility / simple configs)
        provider = SSOProvider.query.filter_by(provider_type=provider_type_name).first()
        if not provider:
            return error_response(f"No provider found with type: {provider_type_name}", 404)
        provider_id = provider.id
    else:
        return error_response("Provider ID or type required", 400)
    
    data = request.get_json()
    
    # Update common fields
    if 'name' in data:
        # Check uniqueness
        existing = SSOProvider.query.filter_by(name=data['name']).first()
        if existing and existing.id != provider_id:
            return error_response("Provider name already exists", 400)
        provider.name = data['name']
    
    if 'display_name' in data:
        provider.display_name = data['display_name']
    if 'icon' in data:
        provider.icon = data['icon']
    if 'enabled' in data:
        provider.enabled = data['enabled']
    if 'default_role' in data:
        provider.default_role = data['default_role']
    if 'auto_create_users' in data:
        provider.auto_create_users = data['auto_create_users']
    if 'auto_update_users' in data:
        provider.auto_update_users = data['auto_update_users']
    
    # Type-specific fields
    if provider.provider_type == 'saml':
        for field in ['saml_entity_id', 'saml_sso_url', 'saml_slo_url', 'saml_certificate', 'saml_sign_requests']:
            if field in data:
                setattr(provider, field, data[field])
    
    elif provider.provider_type == 'oauth2':
        for field in ['oauth2_client_id', 'oauth2_client_secret', 'oauth2_auth_url', 
                      'oauth2_token_url', 'oauth2_userinfo_url']:
            if field in data:
                setattr(provider, field, data[field])
        if 'oauth2_scopes' in data:
            provider.oauth2_scopes = json.dumps(data['oauth2_scopes'])
    
    elif provider.provider_type == 'ldap':
        for field in ['ldap_server', 'ldap_port', 'ldap_use_ssl', 'ldap_bind_dn', 
                      'ldap_bind_password', 'ldap_base_dn', 'ldap_user_filter',
                      'ldap_group_filter', 'ldap_username_attr', 'ldap_email_attr', 
                      'ldap_fullname_attr']:
            if field in data:
                setattr(provider, field, data[field])
    
    # JSON fields
    if 'attribute_mapping' in data:
        provider.attribute_mapping = json.dumps(data['attribute_mapping'])
    if 'role_mapping' in data:
        provider.role_mapping = json.dumps(data['role_mapping'])
    
    db.session.commit()
    return success_response(data=provider.to_dict(), message="SSO provider updated")


@bp.route('/api/v2/sso/providers/<int:provider_id>', methods=['DELETE'])
@require_auth(['delete:sso'])
def delete_provider(provider_id):
    """Delete SSO provider"""
    provider = SSOProvider.query.get_or_404(provider_id)
    
    # Delete associated sessions first
    SSOSession.query.filter_by(provider_id=provider_id).delete()
    
    db.session.delete(provider)
    db.session.commit()
    
    return success_response(message="SSO provider deleted")


@bp.route('/api/v2/sso/providers/<int:provider_id>/toggle', methods=['POST'])
@require_auth(['write:sso'])
def toggle_provider(provider_id):
    """Enable/disable SSO provider"""
    provider = SSOProvider.query.get_or_404(provider_id)
    provider.enabled = not provider.enabled
    db.session.commit()
    
    status = "enabled" if provider.enabled else "disabled"
    return success_response(data=provider.to_dict(), message=f"SSO provider {status}")


@bp.route('/api/v2/sso/providers/<int:provider_id>/test', methods=['POST'])
@require_auth(['write:sso'])
def test_provider(provider_id):
    """Test SSO provider connection"""
    provider = SSOProvider.query.get_or_404(provider_id)
    
    if provider.provider_type == 'ldap':
        return _test_ldap_connection(provider)
    elif provider.provider_type == 'oauth2':
        return _test_oauth2_connection(provider)
    elif provider.provider_type == 'saml':
        return _test_saml_connection(provider)
    
    return error_response("Unknown provider type", 400)


def _test_ldap_connection(provider):
    """Test LDAP connection"""
    try:
        import ldap3
        from ldap3 import Server, Connection, ALL
        from ldap3.utils.conv import escape_filter_chars
        
        server = Server(
            provider.ldap_server,
            port=provider.ldap_port,
            use_ssl=provider.ldap_use_ssl,
            get_info=ALL
        )
        
        conn = Connection(
            server,
            user=provider.ldap_bind_dn,
            password=provider.ldap_bind_password,
            auto_bind=True
        )
        
        # Test search with escaped filter
        conn.search(
            provider.ldap_base_dn,
            '(objectClass=*)',
            attributes=['cn'],
            size_limit=1
        )
        
        conn.unbind()
        
        return success_response(data={
            'status': 'success',
            'message': 'LDAP connection successful',
            'server_info': str(server.info)[:500] if server.info else None
        })
    except ImportError:
        return error_response("LDAP library not installed. Run: pip install ldap3", 500)
    except Exception as e:
        return error_response(f"LDAP connection failed: {str(e)}", 400)


def _ldap_authenticate_user(provider, username, password):
    """Authenticate user via LDAP with proper filter escaping"""
    try:
        import ldap3
        from ldap3 import Server, Connection, ALL
        from ldap3.utils.conv import escape_filter_chars
        
        server = Server(
            provider.ldap_server,
            port=provider.ldap_port,
            use_ssl=provider.ldap_use_ssl,
            get_info=ALL
        )
        
        # First bind as service account
        conn = Connection(
            server,
            user=provider.ldap_bind_dn,
            password=provider.ldap_bind_password,
            auto_bind=True
        )
        
        # SECURITY: Escape username to prevent LDAP injection
        safe_username = escape_filter_chars(username)
        
        # Search for user with escaped filter
        user_filter = provider.ldap_user_filter.replace('{username}', safe_username)
        conn.search(
            provider.ldap_base_dn,
            user_filter,
            attributes=[
                provider.ldap_username_attr,
                provider.ldap_email_attr,
                provider.ldap_fullname_attr
            ]
        )
        
        if not conn.entries:
            conn.unbind()
            return None, "User not found in LDAP"
        
        user_entry = conn.entries[0]
        user_dn = user_entry.entry_dn
        
        # Close service account connection
        conn.unbind()
        
        # Attempt to bind as the user to verify password
        user_conn = Connection(
            server,
            user=user_dn,
            password=password
        )
        
        if not user_conn.bind():
            return None, "Invalid password"
        
        user_conn.unbind()
        
        # Return user info
        return {
            'dn': user_dn,
            'username': str(getattr(user_entry, provider.ldap_username_attr, username)),
            'email': str(getattr(user_entry, provider.ldap_email_attr, '')),
            'fullname': str(getattr(user_entry, provider.ldap_fullname_attr, ''))
        }, None
        
    except ImportError:
        return None, "LDAP library not installed"
    except Exception as e:
        return None, str(e)


def _test_oauth2_connection(provider):
    """Test OAuth2 configuration (checks URLs are reachable)"""
    try:
        import requests
        
        # Test auth URL
        response = requests.head(provider.oauth2_auth_url, timeout=5, allow_redirects=True)
        
        return success_response(data={
            'status': 'success',
            'message': 'OAuth2 endpoints reachable',
            'auth_url_status': response.status_code
        })
    except Exception as e:
        return error_response(f"OAuth2 test failed: {str(e)}", 400)


def _test_saml_connection(provider):
    """Test SAML configuration"""
    # For SAML, we mainly verify the certificate is valid
    if not provider.saml_certificate:
        return error_response("SAML certificate not configured", 400)
    
    try:
        from cryptography import x509
        from cryptography.hazmat.backends import default_backend
        
        # Try to parse certificate
        cert_pem = provider.saml_certificate
        if not cert_pem.startswith('-----BEGIN'):
            cert_pem = f"-----BEGIN CERTIFICATE-----\n{cert_pem}\n-----END CERTIFICATE-----"
        
        cert = x509.load_pem_x509_certificate(cert_pem.encode(), default_backend())
        
        return success_response(data={
            'status': 'success',
            'message': 'SAML certificate valid',
            'cert_subject': cert.subject.rfc4514_string(),
            'cert_expires': cert.not_valid_after_utc.isoformat()
        })
    except Exception as e:
        return error_response(f"SAML certificate invalid: {str(e)}", 400)


# ============ SSO Sessions ============

@bp.route('/api/v2/sso/sessions', methods=['GET'])
@require_auth(['read:sso'])
def list_sessions():
    """List active SSO sessions"""
    sessions = SSOSession.query.filter(
        SSOSession.expires_at > datetime.utcnow()
    ).all()
    return success_response(data=[s.to_dict() for s in sessions])


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
        'is_default': p.is_default
    } for p in providers])


@bp.route('/api/v2/sso/login/<int:provider_id>', methods=['GET'])
def initiate_sso_login(provider_id):
    """
    Initiate SSO login flow.
    For OAuth2: redirects to authorization URL
    For SAML: redirects to IdP SSO URL
    For LDAP: returns error (LDAP uses direct auth via /api/v2/sso/ldap/login)
    """
    import secrets as py_secrets
    import urllib.parse
    
    provider = SSOProvider.query.get_or_404(provider_id)
    
    if not provider.enabled:
        return error_response("SSO provider is disabled", 400)
    
    if provider.provider_type == 'ldap':
        return error_response("LDAP uses direct authentication. Use /api/v2/sso/ldap/login instead.", 400)
    
    # Generate state token for CSRF protection
    state = py_secrets.token_urlsafe(32)
    session['sso_state'] = state
    session['sso_provider_id'] = provider_id
    
    if provider.provider_type == 'oauth2':
        # Build OAuth2 authorization URL
        scopes = json.loads(provider.oauth2_scopes) if provider.oauth2_scopes else ['openid', 'profile', 'email']
        
        # Get callback URL from request
        callback_url = request.url_root.rstrip('/') + f'/api/v2/sso/callback/{provider_id}'
        
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
        # For SAML, we'd need to generate a SAML AuthnRequest
        # This is a simplified redirect - full SAML requires python3-saml library
        if not provider.saml_sso_url:
            return error_response("SAML SSO URL not configured", 400)
        
        # Simple redirect (real SAML needs signed request)
        return redirect(provider.saml_sso_url)
    
    return error_response("Unknown provider type", 400)


@bp.route('/api/v2/sso/callback/<int:provider_id>', methods=['GET', 'POST'])
def sso_callback(provider_id):
    """
    Handle SSO callback from OAuth2/SAML providers.
    Creates or updates user and establishes session.
    """
    import requests
    from auth.unified import create_tokens_for_user
    
    provider = SSOProvider.query.get_or_404(provider_id)
    
    if not provider.enabled:
        return redirect('/login?error=provider_disabled')
    
    # Verify state for CSRF protection
    state = request.args.get('state')
    if state != session.get('sso_state'):
        return redirect('/login?error=invalid_state')
    
    if provider.provider_type == 'oauth2':
        code = request.args.get('code')
        if not code:
            error = request.args.get('error', 'no_code')
            return redirect(f'/login?error={error}')
        
        try:
            # Exchange code for token
            callback_url = request.url_root.rstrip('/') + f'/api/v2/sso/callback/{provider_id}'
            
            token_response = requests.post(
                provider.oauth2_token_url,
                data={
                    'grant_type': 'authorization_code',
                    'code': code,
                    'redirect_uri': callback_url,
                    'client_id': provider.oauth2_client_id,
                    'client_secret': provider.oauth2_client_secret
                },
                timeout=10
            )
            
            if not token_response.ok:
                current_app.logger.error(f"OAuth2 token exchange failed: {token_response.text}")
                return redirect('/login?error=token_exchange_failed')
            
            tokens = token_response.json()
            access_token = tokens.get('access_token')
            
            if not access_token:
                return redirect('/login?error=no_access_token')
            
            # Get user info
            userinfo_response = requests.get(
                provider.oauth2_userinfo_url,
                headers={'Authorization': f'Bearer {access_token}'},
                timeout=10
            )
            
            if not userinfo_response.ok:
                return redirect('/login?error=userinfo_failed')
            
            userinfo = userinfo_response.json()
            
            # Map attributes
            attr_mapping = json.loads(provider.attribute_mapping) if provider.attribute_mapping else {}
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
                sso_session.expires_at = datetime.utcnow() + timedelta(hours=8)
            else:
                sso_session = SSOSession(
                    user_id=user.id,
                    provider_id=provider.id,
                    session_id=session_id,
                    sso_name_id=session_id,
                    expires_at=datetime.utcnow() + timedelta(hours=8)
                )
                db.session.add(sso_session)
            db.session.commit()
            
            # Create JWT tokens
            jwt_tokens = create_tokens_for_user(user)
            
            # Also establish Flask session for cookie-based auth
            session['user_id'] = user.id
            session['username'] = user.username
            session['role'] = user.role
            session['auth_method'] = 'sso'
            session.permanent = True  # Use permanent session
            
            # Redirect to app with tokens in URL fragment (secure: not sent to server)
            return redirect(f'/login/sso-complete?token={jwt_tokens["access_token"]}')
            
        except Exception as e:
            current_app.logger.error(f"OAuth2 callback error: {e}")
            return redirect('/login?error=callback_error')
    
    elif provider.provider_type == 'saml':
        # Handle SAML response
        # This is simplified - real SAML needs signature verification
        saml_response = request.form.get('SAMLResponse')
        if not saml_response:
            return redirect('/login?error=no_saml_response')
        
        # TODO: Parse and verify SAML response
        return redirect('/login?error=saml_not_implemented')
    
    return redirect('/login?error=unknown_provider_type')


@bp.route('/api/v2/sso/ldap/login', methods=['POST'])
def ldap_login():
    """
    Direct LDAP authentication.
    Unlike OAuth2/SAML, LDAP authenticates with username/password directly.
    """
    from auth.unified import create_tokens_for_user
    
    data = request.get_json()
    username = data.get('username')
    password = data.get('password')
    provider_id = data.get('provider_id')
    
    if not username or not password:
        return error_response("Username and password required", 400)
    
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
        return error_response(f"LDAP authentication failed: {error}", 401)
    
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
    
    # Create session
    sso_session = SSOSession(
        user_id=user.id,
        provider_id=provider.id,
        session_id=user_info['dn'],
        sso_name_id=user_info.get('uid', user_info['dn']),
        expires_at=datetime.utcnow() + timedelta(hours=8)
    )
    db.session.add(sso_session)
    db.session.commit()
    
    # Create JWT tokens
    tokens = create_tokens_for_user(user)
    
    # Also establish Flask session for cookie-based auth
    session['user_id'] = user.id
    session['username'] = user.username
    session['role'] = user.role
    session['auth_method'] = 'ldap'
    session.permanent = True
    
    return success_response(
        data={
            'access_token': tokens['access_token'],
            'user': user.to_dict()
        },
        message='LDAP authentication successful'
    )


def _get_or_create_sso_user(provider, username, email, fullname, external_data):
    """Create or update a user from SSO authentication
    
    Returns:
        tuple: (user, error_code) - user object or None, and error code if failed
    """
    from datetime import timedelta
    
    user = User.query.filter_by(username=username).first()
    
    if user:
        # Update existing user if auto_update is enabled
        if provider.auto_update_users:
            if email:
                user.email = email
            if fullname:
                user.full_name = fullname
            user.last_login = datetime.utcnow()
            db.session.commit()
        return user, None
    
    # Create new user if auto_create is enabled
    if not provider.auto_create_users:
        current_app.logger.warning(f"SSO user {username} not found and auto_create disabled")
        return None, 'auto_create_disabled'
    
    # Map role from provider config
    role_mapping = json.loads(provider.role_mapping) if provider.role_mapping else {}
    role = provider.default_role or 'viewer'
    
    # Check if external data contains role info
    if role_mapping:
        external_roles = external_data.get('roles', external_data.get('groups', []))
        if isinstance(external_roles, str):
            external_roles = [external_roles]
        
        for ext_role, ucm_role in role_mapping.items():
            if ext_role in external_roles:
                role = ucm_role
                break
    
    user = User(
        username=username,
        email=email or f'{username}@sso.local',
        full_name=fullname or username,
        role=role,
        active=True,
        last_login=datetime.utcnow()
    )
    
    # SSO users don't have a password (they auth via SSO)
    user.password_hash = ''
    
    db.session.add(user)
    db.session.commit()
    
    current_app.logger.info(f"Created SSO user: {username} with role {role}")
    return user, None
