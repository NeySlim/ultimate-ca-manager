"""
SSO API - UCM
SAML, OAuth2, LDAP authentication providers
"""

from flask import Blueprint, request, redirect, session, Response
from auth.unified import require_auth
from utils.response import success_response, error_response
from models import db, User, Certificate
from models.sso import SSOProvider, SSOSession
from datetime import datetime, timedelta
import hmac
import json
import base64
import secrets as py_secrets
import traceback
import urllib.parse
import requests as http_requests
from lxml import etree

import logging
logger = logging.getLogger(__name__)

VALID_ROLES = {'admin', 'operator', 'viewer'}

bp = Blueprint('sso_pro', __name__)


def _parse_json_field(value):
    """Parse a JSON field that may be a string, double-encoded string, or dict/list."""
    if not value:
        return {}
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
            if isinstance(parsed, str):
                parsed = json.loads(parsed)
            return parsed if isinstance(parsed, dict) else {}
        except (json.JSONDecodeError, TypeError):
            return {}
    return {}


# LDAP brute-force protection (reuses User model's lockout fields)
LDAP_MAX_FAILED_ATTEMPTS = 5
LDAP_LOCKOUT_MINUTES = 15


def _check_ldap_lockout(username):
    """Check if account is locked due to failed LDAP attempts."""
    user = User.query.filter_by(username=username).first()
    if not user:
        return False
    if user.locked_until:
        if datetime.utcnow() < user.locked_until:
            return True
        user.locked_until = None
        user.failed_logins = 0
        db.session.commit()
    return False


def _record_ldap_failed_attempt(username):
    """Record a failed LDAP login attempt."""
    user = User.query.filter_by(username=username).first()
    if not user:
        return
    user.failed_logins = (user.failed_logins or 0) + 1
    if user.failed_logins >= LDAP_MAX_FAILED_ATTEMPTS:
        user.locked_until = datetime.utcnow() + timedelta(minutes=LDAP_LOCKOUT_MINUTES)
        logger.warning(f"LDAP account locked for {username} after {LDAP_MAX_FAILED_ATTEMPTS} failed attempts")
    db.session.commit()


def _clear_ldap_failed_attempts(username):
    """Clear failed attempt counters on successful login."""
    user = User.query.filter_by(username=username).first()
    if user and (user.failed_logins or user.locked_until):
        user.failed_logins = 0
        user.locked_until = None
        db.session.commit()


def _resolve_role(provider, external_data):
    """Resolve user role from role_mapping or default_role."""
    role_mapping = _parse_json_field(provider.role_mapping)
    if role_mapping:
        external_roles = external_data.get('roles', external_data.get('groups', []))
        if isinstance(external_roles, str):
            external_roles = [external_roles]
        logger.info(f"Role resolution: mapping={role_mapping}, external_groups={external_roles}")
        for ext_role, ucm_role in role_mapping.items():
            if ext_role in external_roles:
                resolved = ucm_role if ucm_role in VALID_ROLES else 'viewer'
                logger.info(f"Role resolved via mapping: {ext_role} -> {resolved}")
                return resolved
    fallback = provider.default_role if provider.default_role in VALID_ROLES else 'viewer'
    logger.info(f"Role resolved via default_role: {fallback}")
    return fallback


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
    
    # Enforce 1 provider per type
    existing = SSOProvider.query.filter_by(provider_type=data['provider_type']).first()
    if existing:
        return error_response(f"A {data['provider_type'].upper()} provider already exists. Only one provider per type is allowed.", 400)
    
    provider = SSOProvider(
        name=data['name'],
        provider_type=data['provider_type'],
        display_name=data.get('display_name'),
        icon=data.get('icon'),
        enabled=data.get('enabled', False),
        is_default=data.get('is_default', False),
        default_role=data.get('default_role', 'viewer') if data.get('default_role') in VALID_ROLES else 'viewer',
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
        provider.saml_sp_cert_source = data.get('saml_sp_cert_source', 'https')
    
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
        provider.ldap_group_member_attr = data.get('ldap_group_member_attr', 'member')
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
        provider.default_role = data['default_role'] if data['default_role'] in VALID_ROLES else 'viewer'
    if 'auto_create_users' in data:
        provider.auto_create_users = data['auto_create_users']
    if 'auto_update_users' in data:
        provider.auto_update_users = data['auto_update_users']
    
    # Type-specific fields
    if provider.provider_type == 'saml':
        for field in ['saml_metadata_url', 'saml_entity_id', 'saml_sso_url', 'saml_slo_url', 'saml_certificate', 'saml_sign_requests', 'saml_sp_cert_source']:
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
                      'ldap_group_filter', 'ldap_group_member_attr', 'ldap_username_attr', 'ldap_email_attr', 
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
        logger.error(f"LDAP connection test failed: {e}")
        return error_response("LDAP connection failed. Check server address, port, and credentials.", 400)


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
            return None, "Invalid credentials"
        
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
            return None, "Invalid credentials"
        
        user_conn.unbind()
        
        # Fetch user's groups for role mapping
        groups = []
        if provider.ldap_group_filter:
            member_attr = (provider.ldap_group_member_attr or 'member').strip().lower()
            try:
                if member_attr == 'memberof':
                    # Method: read memberOf attribute from user entry (AD style)
                    memberof_conn = Connection(
                        server,
                        user=provider.ldap_bind_dn,
                        password=provider.ldap_bind_password,
                        auto_bind=True
                    )
                    safe_dn = escape_filter_chars(user_dn)
                    memberof_conn.search(
                        provider.ldap_base_dn,
                        f'(distinguishedName={safe_dn})',
                        attributes=['memberOf']
                    )
                    if not memberof_conn.entries:
                        # Fallback: search by user filter
                        safe_un = escape_filter_chars(username)
                        uf = provider.ldap_user_filter.replace('{username}', safe_un)
                        memberof_conn.search(provider.ldap_base_dn, uf, attributes=['memberOf'])
                    
                    if memberof_conn.entries:
                        entry = memberof_conn.entries[0]
                        if hasattr(entry, 'memberOf'):
                            group_dns = entry.memberOf.values if hasattr(entry.memberOf, 'values') else [str(entry.memberOf)]
                            # Extract CN from each group DN
                            for gdn in group_dns:
                                gdn_str = str(gdn)
                                # Parse CN from DN like "CN=Grp_IT_ADM,OU=Groups,DC=example,DC=com"
                                for part in gdn_str.split(','):
                                    part = part.strip()
                                    if part.upper().startswith('CN='):
                                        groups.append(part[3:])
                                        break
                    memberof_conn.unbind()
                    logger.info(f"LDAP memberOf groups for {username}: {groups}")
                else:
                    # Method: search groups where member/uniqueMember = user_dn (OpenLDAP style)
                    group_conn = Connection(
                        server,
                        user=provider.ldap_bind_dn,
                        password=provider.ldap_bind_password,
                        auto_bind=True
                    )
                    group_base = ','.join(provider.ldap_base_dn.split(',')[1:]) or provider.ldap_base_dn
                    # Ensure group_filter has parentheses
                    gf = provider.ldap_group_filter.strip()
                    if not gf.startswith('('):
                        gf = f'({gf})'
                    safe_dn = escape_filter_chars(user_dn)
                    group_filter = f'(&{gf}({member_attr}={safe_dn}))'
                    group_conn.search(group_base, group_filter, attributes=['cn'])
                    groups = [str(entry.cn) for entry in group_conn.entries if hasattr(entry, 'cn')]
                    group_conn.unbind()
                    logger.info(f"LDAP {member_attr} groups for {username}: {groups}")
            except Exception as e:
                logger.warning(f"Failed to fetch LDAP groups for {username}: {e}")
        
        # Return user info
        return {
            'dn': user_dn,
            'username': str(getattr(user_entry, provider.ldap_username_attr, username)),
            'email': str(getattr(user_entry, provider.ldap_email_attr, '')),
            'fullname': str(getattr(user_entry, provider.ldap_fullname_attr, '')),
            'groups': groups
        }, None
        
    except ImportError:
        return None, "LDAP library not installed"
    except Exception as e:
        logger.error(f"LDAP authentication error: {e}")
        return None, "LDAP authentication failed"


def _test_oauth2_connection(provider):
    """Test OAuth2 configuration (checks URLs are reachable)"""
    try:
        # Test auth URL
        response = http_requests.head(provider.oauth2_auth_url, timeout=5, allow_redirects=True)
        
        return success_response(data={
            'status': 'success',
            'message': 'OAuth2 endpoints reachable',
            'auth_url_status': response.status_code
        })
    except Exception as e:
        logger.error(f"OAuth2 connection test failed: {e}")
        return error_response("OAuth2 test failed. Check authorization URL is reachable.", 400)


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
        logger.error(f"SAML certificate validation failed: {e}")
        return error_response("SAML certificate is invalid or malformed", 400)


# ============ Test Mapping (Dry Run) ============

@bp.route('/api/v2/sso/providers/<int:provider_id>/test-mapping', methods=['POST'])
@require_auth(['write:sso'])
def test_mapping(provider_id):
    """Dry-run LDAP group lookup: fetches groups for a username without creating a session"""
    provider = SSOProvider.query.get_or_404(provider_id)
    
    if provider.provider_type != 'ldap':
        return error_response("Test mapping is only available for LDAP providers", 400)
    
    data = request.get_json() or {}
    test_username = data.get('username', '').strip()
    if not test_username:
        return error_response("Username is required", 400)
    
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
        
        safe_username = escape_filter_chars(test_username)
        user_filter = provider.ldap_user_filter.replace('{username}', safe_username)
        
        attrs = [
            provider.ldap_username_attr,
            provider.ldap_email_attr,
            provider.ldap_fullname_attr
        ]
        member_attr = (provider.ldap_group_member_attr or 'member').strip().lower()
        if member_attr == 'memberof':
            attrs.append('memberOf')
        
        conn.search(provider.ldap_base_dn, user_filter, attributes=attrs)
        
        if not conn.entries:
            conn.unbind()
            return success_response(data={
                'found': False,
                'message': f'User "{test_username}" not found in LDAP'
            })
        
        user_entry = conn.entries[0]
        user_dn = user_entry.entry_dn
        
        # Fetch groups
        groups = []
        if provider.ldap_group_filter:
            if member_attr == 'memberof':
                if hasattr(user_entry, 'memberOf'):
                    group_dns = user_entry.memberOf.values if hasattr(user_entry.memberOf, 'values') else [str(user_entry.memberOf)]
                    for gdn in group_dns:
                        gdn_str = str(gdn)
                        for part in gdn_str.split(','):
                            part = part.strip()
                            if part.upper().startswith('CN='):
                                groups.append(part[3:])
                                break
                else:
                    # Fallback: re-search with memberOf attribute
                    safe_dn = escape_filter_chars(user_dn)
                    conn.search(provider.ldap_base_dn, f'(distinguishedName={safe_dn})', attributes=['memberOf'])
                    if conn.entries and hasattr(conn.entries[0], 'memberOf'):
                        group_dns = conn.entries[0].memberOf.values if hasattr(conn.entries[0].memberOf, 'values') else [str(conn.entries[0].memberOf)]
                        for gdn in group_dns:
                            gdn_str = str(gdn)
                            for part in gdn_str.split(','):
                                part = part.strip()
                                if part.upper().startswith('CN='):
                                    groups.append(part[3:])
                                    break
            else:
                group_base = ','.join(provider.ldap_base_dn.split(',')[1:]) or provider.ldap_base_dn
                gf = provider.ldap_group_filter.strip()
                if not gf.startswith('('):
                    gf = f'({gf})'
                safe_dn = escape_filter_chars(user_dn)
                group_filter = f'(&{gf}({member_attr}={safe_dn}))'
                conn.search(group_base, group_filter, attributes=['cn'])
                groups = [str(entry.cn) for entry in conn.entries if hasattr(entry, 'cn')]
        
        conn.unbind()
        
        # Resolve role using same logic as real login
        resolved_role = _resolve_role(provider, {'groups': groups})
        
        return success_response(data={
            'found': True,
            'user_dn': user_dn,
            'username': str(getattr(user_entry, provider.ldap_username_attr, test_username)),
            'email': str(getattr(user_entry, provider.ldap_email_attr, '')),
            'groups': groups,
            'resolved_role': resolved_role,
            'role_mapping': _parse_json_field(provider.role_mapping) or {},
            'default_role': provider.default_role
        })
        
    except ImportError:
        return error_response("LDAP library not installed", 500)
    except Exception as e:
        logger.error(f"LDAP test mapping failed: {e}")
        return error_response(f"Test mapping failed: check LDAP configuration", 400)


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
            logger.error(f"Failed to fetch IDP metadata (SSL fallback): {e}")
            return error_response("Failed to fetch metadata. Check the URL is reachable.", 400)
    except Exception as e:
        logger.error(f"Failed to fetch IDP metadata: {e}")
        return error_response("Failed to fetch metadata. Check the URL is reachable.", 400)
    
    try:
        parsed = _parse_saml_metadata(resp.text)
        return success_response(data=parsed, message="IDP metadata parsed successfully")
    except Exception as e:
        logger.error(f"Failed to parse IDP metadata XML: {e}")
        return error_response("Failed to parse metadata XML. Ensure the URL returns valid SAML metadata.", 400)


@bp.route('/api/v2/sso/saml/certificates', methods=['GET'])
@require_auth(['read:sso'])
def list_saml_certificates():
    """List valid certificates available for SAML SP metadata.
    Returns HTTPS cert + all valid certs from the database."""
    import os
    from datetime import datetime
    
    certs = []
    
    # Option 1: HTTPS certificate (default)
    data_path = os.environ.get('DATA_PATH', '/opt/ucm/data')
    cert_path = os.path.join(data_path, 'https_cert.pem')
    try:
        from cryptography import x509
        from cryptography.hazmat.primitives import serialization
        with open(cert_path, 'rb') as f:
            pem_data = f.read()
        cert = x509.load_pem_x509_certificate(pem_data)
        certs.append({
            'id': 'https',
            'label': f'HTTPS Certificate ({cert.subject.rfc4514_string()})',
            'subject': cert.subject.rfc4514_string(),
            'not_after': cert.not_valid_after_utc.isoformat() if hasattr(cert, 'not_valid_after_utc') else cert.not_valid_after.isoformat(),
            'is_default': True,
        })
    except Exception as e:
        logger.warning(f"Could not load HTTPS cert: {e}")
        certs.append({
            'id': 'https',
            'label': 'HTTPS Certificate',
            'subject': 'Unknown',
            'not_after': None,
            'is_default': True,
        })
    
    # Option 2+: Valid certificates from database
    try:
        db_certs = Certificate.query.filter(
            Certificate.revoked == False,
            Certificate.valid_to > datetime.utcnow(),
            Certificate.crt.isnot(None)
        ).order_by(Certificate.subject_cn).all()
        
        for c in db_certs:
            certs.append({
                'id': str(c.id),
                'label': c.subject_cn or c.descr or f'Certificate #{c.id}',
                'subject': c.subject,
                'issuer': c.issuer,
                'not_after': c.valid_to.isoformat() if c.valid_to else None,
                'key_type': c.key_algo,
                'is_default': False,
            })
    except Exception as e:
        logger.warning(f"Could not list certificates: {e}")
    
    return success_response(data=certs)


@bp.route('/api/v2/sso/saml/metadata', methods=['GET'])
def get_sp_metadata():
    """Generate schema-valid SAML 2.0 SP metadata XML for configuring the IDP.
    
    Uses python3-saml's metadata builder to ensure compliance with
    the SAML 2.0 Metadata XSD (correct element ordering, validUntil, etc.).
    Includes SP signing certificate (HTTPS cert) in KeyDescriptor.
    Works with strict IDPs like Omnissa Workspace ONE Access, ADFS, Shibboleth.
    """
    import os
    from onelogin.saml2.settings import OneLogin_Saml2_Settings
    
    sp_base = request.url_root.rstrip('/')
    entity_id = f'{sp_base}/api/v2/sso'
    acs_url = f'{sp_base}/api/v2/sso/callback/saml'
    slo_url = f'{sp_base}/api/v2/sso/callback/saml'
    
    # Load SAML provider config if available (for NameIDFormat override + cert source)
    provider = SSOProvider.query.filter_by(provider_type='saml').first()
    name_id_format = (getattr(provider, 'saml_name_id_format', None) 
                      if provider else None) or 'urn:oasis:names:tc:SAML:1.1:nameid-format:unspecified'
    
    # Determine certificate source
    cert_source = (getattr(provider, 'saml_sp_cert_source', None)
                   if provider else None) or 'https'
    
    # Load SP certificate for KeyDescriptor
    sp_cert = ''
    data_path = os.environ.get('DATA_PATH', '/opt/ucm/data')
    
    if cert_source != 'https':
        # Load certificate from database by ID (must be valid and not revoked)
        try:
            from datetime import datetime as dt
            db_cert = Certificate.query.filter(
                Certificate.id == int(cert_source),
                Certificate.revoked == False,
                Certificate.valid_to > dt.utcnow(),
                Certificate.crt.isnot(None)
            ).first()
            if db_cert:
                cert_content = base64.b64decode(db_cert.crt).decode('utf-8')
                in_cert = False
                cert_lines = []
                for line in cert_content.splitlines():
                    if '-----BEGIN CERTIFICATE-----' in line:
                        in_cert = True
                        continue
                    if '-----END CERTIFICATE-----' in line:
                        break
                    if in_cert:
                        cert_lines.append(line.strip())
                sp_cert = ''.join(cert_lines)
                logger.info(f"Using database certificate #{cert_source} for SP metadata")
            else:
                logger.warning(f"Certificate #{cert_source} not found, falling back to HTTPS cert")
                cert_source = 'https'
        except Exception as e:
            logger.warning(f"Could not load certificate #{cert_source}: {e}, falling back to HTTPS cert")
            cert_source = 'https'
    
    if cert_source == 'https':
        # Default: use HTTPS certificate
        cert_path = os.path.join(data_path, 'https_cert.pem')
        try:
            with open(cert_path, 'r') as f:
                cert_content = f.read()
            in_cert = False
            cert_lines = []
            for line in cert_content.splitlines():
                if '-----BEGIN CERTIFICATE-----' in line:
                    in_cert = True
                    continue
                if '-----END CERTIFICATE-----' in line:
                    break
                if in_cert:
                    cert_lines.append(line.strip())
            sp_cert = ''.join(cert_lines)
        except Exception as e:
            logger.warning(f"Could not load SP certificate from {cert_path}: {e}")
    
    settings_data = {
        'strict': False,
        'sp': {
            'entityId': entity_id,
            'assertionConsumerService': {
                'url': acs_url,
                'binding': 'urn:oasis:names:tc:SAML:2.0:bindings:HTTP-POST',
            },
            'singleLogoutService': {
                'url': slo_url,
                'binding': 'urn:oasis:names:tc:SAML:2.0:bindings:HTTP-Redirect',
            },
            'NameIDFormat': name_id_format,
        },
        'idp': {
            'entityId': 'https://idp.placeholder.local',
            'singleSignOnService': {
                'url': 'https://idp.placeholder.local/sso',
                'binding': 'urn:oasis:names:tc:SAML:2.0:bindings:HTTP-Redirect',
            },
        },
    }
    
    # Include SP cert if available — generates KeyDescriptor in metadata
    if sp_cert:
        settings_data['sp']['x509cert'] = sp_cert
    
    try:
        settings = OneLogin_Saml2_Settings(settings_data, custom_base_path='/tmp')
        metadata = settings.get_sp_metadata()
        if isinstance(metadata, bytes):
            metadata = metadata.decode('utf-8')
        
        errors = settings.validate_metadata(metadata)
        if errors:
            logger.warning(f"SP metadata validation warnings: {errors}")
        
        return Response(metadata, mimetype='application/xml',
                        headers={'Content-Disposition': 'inline; filename="ucm-sp-metadata.xml"'})
    except Exception as e:
        logger.error(f"Failed to generate SP metadata via python3-saml: {e}")
        # Fallback: hand-crafted but schema-compliant (correct element order per XSD)
        key_descriptor = ''
        if sp_cert:
            key_descriptor = f'''    <md:KeyDescriptor use="signing">
      <ds:KeyInfo xmlns:ds="http://www.w3.org/2000/09/xmldsig#">
        <ds:X509Data>
          <ds:X509Certificate>{sp_cert}</ds:X509Certificate>
        </ds:X509Data>
      </ds:KeyInfo>
    </md:KeyDescriptor>
'''
        metadata_xml = f'''<?xml version="1.0" encoding="UTF-8"?>
<md:EntityDescriptor xmlns:md="urn:oasis:names:tc:SAML:2.0:metadata"
                     entityID="{entity_id}">
  <md:SPSSODescriptor AuthnRequestsSigned="false"
                      WantAssertionsSigned="true"
                      protocolSupportEnumeration="urn:oasis:names:tc:SAML:2.0:protocol">
{key_descriptor}    <md:SingleLogoutService Binding="urn:oasis:names:tc:SAML:2.0:bindings:HTTP-Redirect"
                            Location="{slo_url}"/>
    <md:NameIDFormat>{name_id_format}</md:NameIDFormat>
    <md:AssertionConsumerService Binding="urn:oasis:names:tc:SAML:2.0:bindings:HTTP-POST"
                                Location="{acs_url}"
                                index="1"
                                isDefault="true"/>
  </md:SPSSODescriptor>
</md:EntityDescriptor>'''
        return Response(metadata_xml, mimetype='application/xml',
                        headers={'Content-Disposition': 'inline; filename="ucm-sp-metadata.xml"'})


def _parse_saml_metadata(xml_text):
    """Parse SAML IDP metadata XML and extract key fields"""
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
            
            token_response = http_requests.post(
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
                timeout=10
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
            logger.error(f"OAuth2 callback error: {e}\n{traceback.format_exc()}")
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
                    logger.error(f"SAML errors: {errors}, reason: {saml_auth.get_last_error_reason()}")
                    return redirect('/login?error=saml_validation_failed')
                attrs = saml_auth.get_attributes()
                name_id = saml_auth.get_nameid()
            except Exception as saml_err:
                # Some IdPs (e.g. Keycloak) send duplicate attribute names
                # which python3-saml rejects; parse manually as fallback
                logger.warning(f"SAML standard parsing failed, using fallback: {saml_err}")
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
            logger.error(f"SAML callback error: {e}\n{traceback.format_exc()}")
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
        sso_session.expires_at = datetime.utcnow() + timedelta(hours=8)
    else:
        sso_session = SSOSession(
            user_id=user.id,
            provider_id=provider.id,
            session_id=session_id,
            sso_name_id=user_info.get('uid', session_id),
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
    
    return success_response(
        data={
            'user': user.to_dict(),
            'role': user.role,
            'permissions': permissions,
            'csrf_token': csrf_token
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
        # Update existing user if auto_update is enabled
        if provider.auto_update_users:
            if email:
                user.email = email
            if fullname:
                user.full_name = fullname
            user.role = _resolve_role(provider, external_data)
            user.last_login = datetime.utcnow()
            db.session.commit()
        return user, None
    
    # Create new user if auto_create is enabled
    if not provider.auto_create_users:
        logger.warning(f"SSO user {username} not found and auto_create disabled")
        return None, 'auto_create_disabled'
    
    role = _resolve_role(provider, external_data)
    
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
    
    logger.info(f"Created SSO user: {username} with role {role}")
    return user, None
