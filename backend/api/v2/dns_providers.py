"""
DNS Providers API Routes
CRUD operations for DNS provider configurations
"""
import json
from flask import Blueprint, request
from auth.unified import require_auth
from utils.response import success_response, error_response
from models import db, DnsProvider
from services.audit_service import AuditService
from services.acme.dns_providers import (
    get_available_providers, 
    is_valid_provider_type,
    create_provider,
    get_provider_class
)

bp = Blueprint('dns_providers', __name__)


@bp.route('/api/v2/dns-providers', methods=['GET'])
@require_auth(['read:acme'])
def list_providers():
    """List all configured DNS providers"""
    providers = DnsProvider.query.order_by(DnsProvider.name).all()
    return success_response(data=[p.to_dict(include_credentials=True) for p in providers])


@bp.route('/api/v2/dns-providers/types', methods=['GET'])
@require_auth(['read:acme'])
def list_provider_types():
    """List available DNS provider types with their credential schemas"""
    types = get_available_providers()
    return success_response(data=types)


@bp.route('/api/v2/dns-providers', methods=['POST'])
@require_auth(['write:acme'])
def create_dns_provider():
    """Create a new DNS provider configuration"""
    data = request.json
    
    if not data:
        return error_response('Request body required', 400)
    
    name = data.get('name')
    provider_type = data.get('provider_type')
    credentials = data.get('credentials', {})
    if credentials and not isinstance(credentials, dict):
        return error_response('Credentials must be an object', 400)
    zones = data.get('zones', [])
    is_default = data.get('is_default', False)
    
    if not name:
        return error_response('Name is required', 400)
    if not provider_type:
        return error_response('Provider type is required', 400)
    if not is_valid_provider_type(provider_type):
        return error_response(f'Invalid provider type: {provider_type}', 400)
    
    # Validate credentials against provider schema
    try:
        provider_class = get_provider_class(provider_type)
        if provider_class:
            # Check required credentials
            for key in provider_class.REQUIRED_CREDENTIALS:
                if not credentials.get(key):
                    return error_response(f'Missing required credential: {key}', 400)
    except Exception as e:
        return error_response(f'Invalid credentials: {str(e)}', 400)
    
    # If setting as default, unset any existing default
    if is_default:
        DnsProvider.query.filter_by(is_default=True).update({'is_default': False})
    
    provider = DnsProvider(
        name=name,
        provider_type=provider_type,
        credentials=json.dumps(credentials) if credentials else None,
        zones=json.dumps(zones) if zones else None,
        is_default=is_default,
        enabled=data.get('enabled', True)
    )
    
    db.session.add(provider)
    db.session.commit()
    
    AuditService.log_action(
        action='dns_provider_create',
        resource_type='dns_provider',
        resource_id=str(provider.id),
        resource_name=provider.name,
        details=f'Created DNS provider: {provider.name} ({provider_type})',
        success=True
    )
    
    return success_response(
        data=provider.to_dict(),
        message='DNS provider created',
        status=201
    )


@bp.route('/api/v2/dns-providers/<int:provider_id>', methods=['GET'])
@require_auth(['read:acme'])
def get_provider(provider_id):
    """Get a specific DNS provider"""
    provider = DnsProvider.query.get(provider_id)
    if not provider:
        return error_response('Provider not found', 404)
    
    return success_response(data=provider.to_dict(include_credentials=True))


@bp.route('/api/v2/dns-providers/<int:provider_id>', methods=['PATCH'])
@require_auth(['write:acme'])
def update_provider(provider_id):
    """Update a DNS provider configuration"""
    provider = DnsProvider.query.get(provider_id)
    if not provider:
        return error_response('Provider not found', 404)
    
    data = request.json
    if not data:
        return error_response('Request body required', 400)
    
    # Update fields
    if 'name' in data:
        provider.name = data['name']
    
    if 'credentials' in data:
        credentials = data['credentials']
        # Skip if credentials is empty or not a dict
        if credentials and isinstance(credentials, dict):
            # Merge with existing credentials (for partial updates)
            if provider.credentials:
                existing = json.loads(provider.credentials)
                # Only update with non-empty values
                for key, value in credentials.items():
                    if value:  # Don't overwrite with empty values
                        existing[key] = value
                credentials = existing
            provider.credentials = json.dumps(credentials) if credentials else None
    
    if 'zones' in data:
        provider.zones = json.dumps(data['zones']) if data['zones'] else None
    
    if 'enabled' in data:
        provider.enabled = data['enabled']
    
    if 'is_default' in data:
        if data['is_default']:
            # Unset any existing default
            DnsProvider.query.filter(
                DnsProvider.id != provider_id,
                DnsProvider.is_default == True
            ).update({'is_default': False})
        provider.is_default = data['is_default']
    
    db.session.commit()
    
    AuditService.log_action(
        action='dns_provider_update',
        resource_type='dns_provider',
        resource_id=str(provider_id),
        resource_name=provider.name,
        details=f'Updated DNS provider: {provider.name}',
        success=True
    )
    
    return success_response(
        data=provider.to_dict(),
        message='DNS provider updated'
    )


@bp.route('/api/v2/dns-providers/<int:provider_id>', methods=['DELETE'])
@require_auth(['write:acme'])
def delete_provider(provider_id):
    """Delete a DNS provider"""
    provider = DnsProvider.query.get(provider_id)
    if not provider:
        return error_response('Provider not found', 404)
    
    # Check if provider is in use
    if provider.client_orders.count() > 0:
        return error_response(
            'Cannot delete provider: it is used by existing orders. '
            'Disable it instead.',
            400
        )
    
    provider_name = provider.name
    db.session.delete(provider)
    db.session.commit()
    
    AuditService.log_action(
        action='dns_provider_delete',
        resource_type='dns_provider',
        resource_id=str(provider_id),
        resource_name=provider_name,
        details=f'Deleted DNS provider: {provider_name}',
        success=True
    )
    
    return success_response(message='DNS provider deleted')


@bp.route('/api/v2/dns-providers/<int:provider_id>/test', methods=['POST'])
@require_auth(['write:acme'])
def test_provider(provider_id):
    """Test DNS provider connection"""
    provider_model = DnsProvider.query.get(provider_id)
    if not provider_model:
        return error_response('Provider not found', 404)
    
    try:
        credentials = json.loads(provider_model.credentials) if provider_model.credentials else {}
        provider = create_provider(provider_model.provider_type, credentials)
        
        success, message = provider.test_connection()
        
        return success_response(
            data={
                'success': success,
                'message': message
            },
            message='Connection test completed'
        )
    except Exception as e:
        return success_response(
            data={
                'success': False,
                'message': str(e)
            },
            message='Connection test failed'
        )
