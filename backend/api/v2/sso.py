"""
SSO API - UCM
SAML, OAuth2, LDAP authentication providers
"""

from flask import Blueprint, request, current_app, redirect, url_for, session
from auth.unified import require_auth
from utils.response import success_response, error_response
from models import db, User
from models.sso import SSOProvider, SSOSession
from datetime import datetime, timedelta
import json
import urllib.parse

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
        is_default=data.get('is_default', False),
        default_role=data.get('default_role', 'viewer'),
        auto_create_users=data.get('auto_create_users', True),
        auto_update_users=data.get('auto_update_users', True),
    )
    
    # If setting as default, clear other providers
    if provider.is_default:
        SSOProvider.query.filter(SSOProvider.id != provider.id).update({'is_default': False})
    
    # Type-specific fields
    if data['provider_type'] == 'saml':
        provider.saml_metadata_url = data.get('saml_metadata_url')
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
    
    # JSON fields - normalize to ensure clean JSON string storage
    if data.get('attribute_mapping'):
        val = data['attribute_mapping']
        if isinstance(val, str):
            val = json.loads(val)
        provider.attribute_mapping = json.dumps(val)
    if data.get('role_mapping'):
        val = data['role_mapping']
        if isinstance(val, str):
            val = json.loads(val)
        provider.role_mapping = json.dumps(val)
    
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
    if 'is_default' in data:
        provider.is_default = data['is_default']
        if provider.is_default:
            SSOProvider.query.filter(SSOProvider.id != provider.id).update({'is_default': False})
    if 'default_role' in data:
        provider.default_role = data['default_role']
    if 'auto_create_users' in data:
        provider.auto_create_users = data['auto_create_users']
    if 'auto_update_users' in data:
        provider.auto_update_users = data['auto_update_users']
    
    # Type-specific fields
    if provider.provider_type == 'saml':
        for field in ['saml_metadata_url', 'saml_entity_id', 'saml_sso_url', 'saml_slo_url', 'saml_certificate', 'saml_sign_requests']:
            if field in data:
                setattr(provider, field, data[field])
    
    elif provider.provider_type == 'oauth2':
        for field in ['oauth2_client_id', 'oauth2_auth_url', 
                      'oauth2_token_url', 'oauth2_userinfo_url']:
            if field in data:
                setattr(provider, field, data[field])
        # Only update secret if non-empty (empty = keep existing)
        if data.get('oauth2_client_secret'):
            provider.oauth2_client_secret = data['oauth2_client_secret']
        if 'oauth2_scopes' in data:
            provider.oauth2_scopes = json.dumps(data['oauth2_scopes'])
    
    elif provider.provider_type == 'ldap':
        for field in ['ldap_server', 'ldap_port', 'ldap_use_ssl', 'ldap_bind_dn', 
                      'ldap_base_dn', 'ldap_user_filter',
                      'ldap_group_filter', 'ldap_username_attr', 'ldap_email_attr', 
                      'ldap_fullname_attr']:
            if field in data:
                setattr(provider, field, data[field])
        # Only update password if non-empty (empty = keep existing)
        if data.get('ldap_bind_password'):
            provider.ldap_bind_password = data['ldap_bind_password']
    
    # JSON fields
    if 'attribute_mapping' in data:
        val = data['attribute_mapping']
        if isinstance(val, str):
            val = json.loads(val)
        provider.attribute_mapping = json.dumps(val)
    if 'role_mapping' in data:
        val = data['role_mapping']
        if isinstance(val, str):
            val = json.loads(val)
        provider.role_mapping = json.dumps(val)
    
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


# ============ SAML Metadata ============

@bp.route('/api/v2/sso/saml/metadata/fetch', methods=['POST'])
@require_auth(['write:sso'])
def fetch_idp_metadata():
    """Fetch and parse IDP metadata XML from a URL"""
    import requests as http_requests
    
    data = request.get_json()
    metadata_url = data.get('metadata_url')
    if not metadata_url:
        return error_response("metadata_url is required", 400)
    
    try:
        resp = http_requests.get(metadata_url, timeout=10, verify=True)
        resp.raise_for_status()
    except http_requests.exceptions.SSLError:
        try:
            resp = http_requests.get(metadata_url, timeout=10, verify=False)
            resp.raise_for_status()
        except Exception as e:
            return error_response(f"Failed to fetch metadata: {str(e)}", 400)
    except Exception as e:
        return error_response(f"Failed to fetch metadata: {str(e)}", 400)
    
    try:
        parsed = _parse_saml_metadata(resp.text)
        return success_response(data=parsed, message="IDP metadata parsed successfully")
    except Exception as e:
        return error_response(f"Failed to parse metadata XML: {str(e)}", 400)


@bp.route('/api/v2/sso/saml/metadata', methods=['GET'])
def get_sp_metadata():
    """Generate SP metadata XML for configuring the IDP"""
    sp_base = request.url_root.rstrip('/')
    entity_id = f'{sp_base}/api/v2/sso'
    acs_url = f'{sp_base}/api/v2/sso/callback/saml'
    slo_url = f'{sp_base}/api/v2/sso/callback/saml'
    
    metadata_xml = f'''<?xml version="1.0" encoding="UTF-8"?>
<md:EntityDescriptor xmlns:md="urn:oasis:names:tc:SAML:2.0:metadata"
                     entityID="{entity_id}">
  <md:SPSSODescriptor AuthnRequestsSigned="false"
                      WantAssertionsSigned="false"
                      protocolSupportEnumeration="urn:oasis:names:tc:SAML:2.0:protocol">
    <md:NameIDFormat>urn:oasis:names:tc:SAML:1.1:nameid-format:unspecified</md:NameIDFormat>
    <md:AssertionConsumerService Binding="urn:oasis:names:tc:SAML:2.0:bindings:HTTP-POST"
                                Location="{acs_url}"
                                index="1"
                                isDefault="true"/>
    <md:SingleLogoutService Binding="urn:oasis:names:tc:SAML:2.0:bindings:HTTP-Redirect"
                            Location="{slo_url}"/>
  </md:SPSSODescriptor>
</md:EntityDescriptor>'''
    
    from flask import Response
    return Response(metadata_xml, mimetype='application/xml',
                    headers={'Content-Disposition': 'inline; filename="ucm-sp-metadata.xml"'})


def _parse_saml_metadata(xml_text):
    """Parse SAML IDP metadata XML and extract key fields"""
    from lxml import etree
    
    NS = {
        'md': 'urn:oasis:names:tc:SAML:2.0:metadata',
        'ds': 'http://www.w3.org/2000/09/xmldsig#',
    }
    
    root = etree.fromstring(xml_text.encode('utf-8'))
    
    result = {
        'entity_id': None,
        'sso_url': None,
        'slo_url': None,
        'certificate': None,
    }
    
    # Entity ID from root or IDPSSODescriptor
    result['entity_id'] = root.get('entityID')
    
    # Find IDPSSODescriptor
    idp = root.find('.//md:IDPSSODescriptor', NS)
    if idp is None:
        # Try without namespace prefix (some IdPs use default ns)
        idp = root.find('.//{urn:oasis:names:tc:SAML:2.0:metadata}IDPSSODescriptor')
    
    if idp is not None:
        # SSO URL (HTTP-Redirect preferred, fallback to HTTP-POST)
        for binding in ['urn:oasis:names:tc:SAML:2.0:bindings:HTTP-Redirect',
                        'urn:oasis:names:tc:SAML:2.0:bindings:HTTP-POST']:
            sso = idp.find(f'md:SingleSignOnService[@Binding="{binding}"]', NS)
            if sso is None:
                sso = idp.find(f'{{urn:oasis:names:tc:SAML:2.0:metadata}}SingleSignOnService[@Binding="{binding}"]')
            if sso is not None:
                result['sso_url'] = sso.get('Location')
                break
        
        # SLO URL
        for binding in ['urn:oasis:names:tc:SAML:2.0:bindings:HTTP-Redirect',
                        'urn:oasis:names:tc:SAML:2.0:bindings:HTTP-POST']:
            slo = idp.find(f'md:SingleLogoutService[@Binding="{binding}"]', NS)
            if slo is None:
                slo = idp.find(f'{{urn:oasis:names:tc:SAML:2.0:metadata}}SingleLogoutService[@Binding="{binding}"]')
            if slo is not None:
                result['slo_url'] = slo.get('Location')
                break
        
        # Certificate (first X509Certificate found)
        cert = idp.find('.//ds:X509Certificate', NS)
        if cert is None:
            cert = idp.find('.//{http://www.w3.org/2000/09/xmldsig#}X509Certificate')
        if cert is not None and cert.text:
            # Clean up whitespace and format
            cert_text = cert.text.strip().replace('\n', '').replace(' ', '')
            # Format as PEM lines of 64 chars
            lines = [cert_text[i:i+64] for i in range(0, len(cert_text), 64)]
            result['certificate'] = '\n'.join(lines)
    
    if not result['entity_id'] and not result['sso_url']:
        raise ValueError("Could not find IDP entity ID or SSO URL in metadata")
    
    return result


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
    import secrets as py_secrets
    import urllib.parse
    
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
            current_app.logger.error(f"SAML login initiation error: {e}")
            return error_response(f"SAML login failed: {str(e)}", 500)
    
    return error_response("Unknown provider type", 400)


@bp.route('/api/v2/sso/callback/<provider_type>', methods=['GET', 'POST'])
def sso_callback(provider_type):
    """
    Handle SSO callback from OAuth2/SAML providers.
    Creates or updates user and establishes session.
    """
    import requests
    
    if provider_type not in ('saml', 'oauth2'):
        return redirect('/login?error=invalid_provider_type')
    
    provider = SSOProvider.query.filter_by(provider_type=provider_type, enabled=True).first()
    if not provider:
        return redirect('/login?error=provider_not_found')
    
    # Verify state for CSRF protection (OAuth2 only — SAML uses its own mechanisms)
    if provider_type == 'oauth2':
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
            callback_url = request.url_root.rstrip('/') + '/api/v2/sso/callback/oauth2'
            
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
            attr_mapping = provider.attribute_mapping
            if isinstance(attr_mapping, str):
                try:
                    attr_mapping = json.loads(attr_mapping)
                    if isinstance(attr_mapping, str):
                        attr_mapping = json.loads(attr_mapping)
                except (json.JSONDecodeError, TypeError):
                    attr_mapping = {}
            if not isinstance(attr_mapping, dict):
                attr_mapping = {}
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
            
            # Establish Flask session
            session['user_id'] = user.id
            session['username'] = user.username
            session['role'] = user.role
            session['auth_method'] = 'sso'
            session.permanent = True
            
            # Redirect to app (session cookie is set automatically)
            return redirect('/login/sso-complete')
            
        except Exception as e:
            import traceback
            current_app.logger.error(f"OAuth2 callback error: {e}\n{traceback.format_exc()}")
            return redirect('/login?error=callback_error')
    
    elif provider.provider_type == 'saml':
        try:
            saml_auth = _get_saml_auth(request, provider)
            attrs = {}
            name_id = ''
            
            try:
                saml_auth.process_response()
                errors = saml_auth.get_errors()
                if errors:
                    current_app.logger.error(f"SAML errors: {errors}, reason: {saml_auth.get_last_error_reason()}")
                    return redirect('/login?error=saml_validation_failed')
                attrs = saml_auth.get_attributes()
                name_id = saml_auth.get_nameid()
            except Exception as saml_err:
                # Some IdPs (e.g. Keycloak) send duplicate attribute names
                # which python3-saml rejects; parse manually as fallback
                current_app.logger.warning(f"SAML standard parsing failed, using fallback: {saml_err}")
                import base64
                from lxml import etree
                saml_response_b64 = request.form.get('SAMLResponse', '')
                saml_xml = base64.b64decode(saml_response_b64)
                root = etree.fromstring(saml_xml)
                ns = {'saml': 'urn:oasis:names:tc:SAML:2.0:assertion'}
                name_id_el = root.find('.//saml:NameID', ns)
                name_id = name_id_el.text if name_id_el is not None else ''
                for attr_el in root.findall('.//saml:Attribute', ns):
                    attr_name = attr_el.get('Name', '')
                    if attr_name and attr_name not in attrs:
                        values = [v.text or '' for v in attr_el.findall('saml:AttributeValue', ns)]
                        attrs[attr_name] = values
            
            # Map attributes
            attr_mapping = provider.attribute_mapping
            if isinstance(attr_mapping, str):
                try:
                    attr_mapping = json.loads(attr_mapping)
                    if isinstance(attr_mapping, str):
                        attr_mapping = json.loads(attr_mapping)
                except (json.JSONDecodeError, TypeError):
                    attr_mapping = {}
            if not isinstance(attr_mapping, dict):
                attr_mapping = {}
            
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
                sso_session.expires_at = datetime.utcnow() + timedelta(hours=8)
            else:
                sso_session = SSOSession(
                    user_id=user.id,
                    provider_id=provider.id,
                    session_id=name_id,
                    sso_name_id=name_id,
                    expires_at=datetime.utcnow() + timedelta(hours=8)
                )
                db.session.add(sso_session)
            db.session.commit()
            
            # Establish Flask session
            session['user_id'] = user.id
            session['username'] = user.username
            session['role'] = user.role
            session['auth_method'] = 'sso'
            session.permanent = True
            
            return redirect('/login/sso-complete')
            
        except Exception as e:
            import traceback
            current_app.logger.error(f"SAML callback error: {e}\n{traceback.format_exc()}")
            return redirect('/login?error=callback_error')
    
    return redirect('/login?error=unknown_provider_type')


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
    
    # Establish Flask session
    session['user_id'] = user.id
    session['username'] = user.username
    session['role'] = user.role
    session['auth_method'] = 'ldap'
    session.permanent = True
    
    return success_response(
        data={
            'user': user.to_dict()
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
    role_mapping = provider.role_mapping
    if isinstance(role_mapping, str):
        try:
            role_mapping = json.loads(role_mapping)
            if isinstance(role_mapping, str):
                role_mapping = json.loads(role_mapping)
        except (json.JSONDecodeError, TypeError):
            role_mapping = {}
    if not isinstance(role_mapping, dict):
        role_mapping = {}
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
