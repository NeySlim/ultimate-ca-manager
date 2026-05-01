from . import bp, VALID_ROLES
from flask import request
from auth.unified import require_auth
from utils.response import success_response, error_response
from models import db
from models.sso import SSOProvider, SSOSession
from services.audit_service import AuditService
import json
from .helpers import _encrypt_ldap_password, _parse_json_field

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
        sync_role_on_login=data.get('sync_role_on_login', False),
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
        provider.saml_verify_ssl = data.get('saml_verify_ssl', True)
        ca = data.get('saml_ca_bundle')
        provider.saml_ca_bundle = ca if isinstance(ca, str) and ca.strip() else None

    elif data['provider_type'] == 'oauth2':
        provider.oauth2_client_id = data.get('oauth2_client_id')
        provider.oauth2_client_secret = data.get('oauth2_client_secret')
        provider.oauth2_auth_url = data.get('oauth2_auth_url')
        provider.oauth2_token_url = data.get('oauth2_token_url')
        provider.oauth2_userinfo_url = data.get('oauth2_userinfo_url')
        provider.oauth2_scopes = json.dumps(data.get('oauth2_scopes', ['openid', 'profile', 'email']))
        provider.oauth2_verify_ssl = data.get('oauth2_verify_ssl', True)
        ca = data.get('oauth2_ca_bundle')
        provider.oauth2_ca_bundle = ca if isinstance(ca, str) and ca.strip() else None

    elif data['provider_type'] == 'ldap':
        provider.ldap_server = data.get('ldap_server')
        provider.ldap_port = data.get('ldap_port', 389)
        provider.ldap_use_ssl = data.get('ldap_use_ssl', False)
        provider.ldap_verify_ssl = data.get('ldap_verify_ssl', True)
        ca = data.get('ldap_ca_bundle')
        provider.ldap_ca_bundle = ca if isinstance(ca, str) and ca.strip() else None
        provider.ldap_bind_dn = data.get('ldap_bind_dn')
        provider.ldap_bind_password = _encrypt_ldap_password(data.get('ldap_bind_password'))
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

    AuditService.log_action(
        action='sso_provider_created',
        resource_type='sso_provider',
        resource_id=provider.id,
        resource_name=provider.name,
        details=f"Type: {provider.provider_type}",
        success=True,
    )

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
    if 'sync_role_on_login' in data:
        provider.sync_role_on_login = bool(data['sync_role_on_login'])

    # Type-specific fields
    if provider.provider_type == 'saml':
        for field in ['saml_metadata_url', 'saml_entity_id', 'saml_sso_url', 'saml_slo_url',
                      'saml_certificate', 'saml_sign_requests', 'saml_sp_cert_source',
                      'saml_verify_ssl']:
            if field in data:
                setattr(provider, field, data[field])
        # ca_bundle: only update if string PEM content (ignore bool from to_dict round-trip)
        if 'saml_ca_bundle' in data and isinstance(data['saml_ca_bundle'], str):
            provider.saml_ca_bundle = data['saml_ca_bundle'] or None

    elif provider.provider_type == 'oauth2':
        for field in ['oauth2_client_id', 'oauth2_auth_url',
                      'oauth2_token_url', 'oauth2_userinfo_url',
                      'oauth2_verify_ssl']:
            if field in data:
                setattr(provider, field, data[field])
        # ca_bundle: only update if string PEM content (ignore bool from to_dict round-trip)
        if 'oauth2_ca_bundle' in data and isinstance(data['oauth2_ca_bundle'], str):
            provider.oauth2_ca_bundle = data['oauth2_ca_bundle'] or None
        # Only update secret if non-empty (empty = keep existing)
        if data.get('oauth2_client_secret'):
            provider.oauth2_client_secret = data['oauth2_client_secret']
        if 'oauth2_scopes' in data:
            provider.oauth2_scopes = json.dumps(data['oauth2_scopes'])

    elif provider.provider_type == 'ldap':
        for field in ['ldap_server', 'ldap_port', 'ldap_use_ssl', 'ldap_bind_dn',
                      'ldap_base_dn', 'ldap_user_filter',
                      'ldap_group_filter', 'ldap_group_member_attr', 'ldap_username_attr', 'ldap_email_attr',
                      'ldap_fullname_attr', 'ldap_verify_ssl']:
            if field in data:
                setattr(provider, field, data[field])
        # ca_bundle: only update if string PEM content (ignore bool from to_dict round-trip)
        if 'ldap_ca_bundle' in data and isinstance(data['ldap_ca_bundle'], str):
            provider.ldap_ca_bundle = data['ldap_ca_bundle'] or None
        # Only update password if non-empty (empty = keep existing)
        if data.get('ldap_bind_password'):
            provider.ldap_bind_password = _encrypt_ldap_password(data['ldap_bind_password'])

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
    AuditService.log_action(
        action='sso_provider_updated',
        resource_type='sso_provider',
        resource_id=provider.id,
        resource_name=provider.name,
        details=f"Updated fields: {', '.join(data.keys())}",
        success=True,
    )
    return success_response(data=provider.to_dict(), message="SSO provider updated")


@bp.route('/api/v2/sso/providers/<int:provider_id>', methods=['DELETE'])
@require_auth(['delete:sso'])
def delete_provider(provider_id):
    """Delete SSO provider"""
    provider = SSOProvider.query.get_or_404(provider_id)
    provider_name = provider.name
    provider_type = provider.provider_type

    # Delete associated sessions first
    SSOSession.query.filter_by(provider_id=provider_id).delete()

    db.session.delete(provider)
    db.session.commit()

    AuditService.log_action(
        action='sso_provider_deleted',
        resource_type='sso_provider',
        resource_id=provider_id,
        resource_name=provider_name,
        details=f"Type: {provider_type}",
        success=True,
    )

    return success_response(message="SSO provider deleted")


@bp.route('/api/v2/sso/providers/<int:provider_id>/toggle', methods=['POST'])
@require_auth(['write:sso'])
def toggle_provider(provider_id):
    """Enable/disable SSO provider"""
    provider = SSOProvider.query.get_or_404(provider_id)
    provider.enabled = not provider.enabled
    db.session.commit()

    status = "enabled" if provider.enabled else "disabled"
    AuditService.log_action(
        action=f'sso_provider_{status}',
        resource_type='sso_provider',
        resource_id=provider.id,
        resource_name=provider.name,
        details=f"Type: {provider.provider_type}",
        success=True,
    )
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
