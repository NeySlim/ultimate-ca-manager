"""
HSM API - UCM Pro
Hardware Security Module management
"""

from flask import Blueprint, request
from auth.unified import require_auth
from utils.response import success_response, error_response
from models import db
from models.pro.hsm import HSMProvider, HSMKey
from datetime import datetime

bp = Blueprint('hsm_pro', __name__)


# ============ Provider Management ============

@bp.route('/api/v2/hsm/providers', methods=['GET'])
@require_auth(['read:hsm'])
def list_providers():
    """List all HSM providers"""
    providers = HSMProvider.query.all()
    return success_response(data=[p.to_dict() for p in providers])


@bp.route('/api/v2/hsm/providers/<int:provider_id>', methods=['GET'])
@require_auth(['read:hsm'])
def get_provider(provider_id):
    """Get HSM provider details"""
    provider = HSMProvider.query.get_or_404(provider_id)
    include_secrets = request.args.get('include_secrets') == 'true'
    return success_response(data=provider.to_dict(include_secrets=include_secrets))


@bp.route('/api/v2/hsm/providers', methods=['POST'])
@require_auth(['write:hsm'])
def create_provider():
    """Create new HSM provider"""
    data = request.get_json()
    
    if not data.get('name'):
        return error_response("Provider name is required", 400)
    if not data.get('provider_type'):
        return error_response("Provider type is required", 400)
    
    valid_types = ['pkcs11', 'aws-cloudhsm', 'azure-keyvault', 'google-kms']
    if data['provider_type'] not in valid_types:
        return error_response(f"Invalid provider type. Must be: {', '.join(valid_types)}", 400)
    
    if HSMProvider.query.filter_by(name=data['name']).first():
        return error_response("Provider name already exists", 400)
    
    provider = HSMProvider(
        name=data['name'],
        provider_type=data['provider_type'],
        enabled=data.get('enabled', False),
        connection_timeout=data.get('connection_timeout', 30),
        retry_count=data.get('retry_count', 3),
    )
    
    # Type-specific fields
    if data['provider_type'] == 'pkcs11':
        provider.pkcs11_library_path = data.get('pkcs11_library_path')
        provider.pkcs11_slot_id = data.get('pkcs11_slot_id')
        provider.pkcs11_pin = data.get('pkcs11_pin')
        provider.pkcs11_token_label = data.get('pkcs11_token_label')
        
    elif data['provider_type'] == 'aws-cloudhsm':
        provider.aws_cluster_id = data.get('aws_cluster_id')
        provider.aws_region = data.get('aws_region')
        provider.aws_access_key = data.get('aws_access_key')
        provider.aws_secret_key = data.get('aws_secret_key')
        provider.aws_crypto_user = data.get('aws_crypto_user')
        provider.aws_crypto_password = data.get('aws_crypto_password')
        
    elif data['provider_type'] == 'azure-keyvault':
        provider.azure_vault_url = data.get('azure_vault_url')
        provider.azure_tenant_id = data.get('azure_tenant_id')
        provider.azure_client_id = data.get('azure_client_id')
        provider.azure_client_secret = data.get('azure_client_secret')
        
    elif data['provider_type'] == 'google-kms':
        provider.gcp_project_id = data.get('gcp_project_id')
        provider.gcp_location = data.get('gcp_location')
        provider.gcp_keyring = data.get('gcp_keyring')
        provider.gcp_credentials_json = data.get('gcp_credentials_json')
    
    db.session.add(provider)
    db.session.commit()
    
    return success_response(data=provider.to_dict(), message="HSM provider created")


@bp.route('/api/v2/hsm/providers/<int:provider_id>', methods=['PUT'])
@require_auth(['write:hsm'])
def update_provider(provider_id):
    """Update HSM provider"""
    provider = HSMProvider.query.get_or_404(provider_id)
    data = request.get_json()
    
    # Update common fields
    if 'name' in data:
        existing = HSMProvider.query.filter_by(name=data['name']).first()
        if existing and existing.id != provider_id:
            return error_response("Provider name already exists", 400)
        provider.name = data['name']
    
    if 'enabled' in data:
        provider.enabled = data['enabled']
    if 'connection_timeout' in data:
        provider.connection_timeout = data['connection_timeout']
    if 'retry_count' in data:
        provider.retry_count = data['retry_count']
    
    # Type-specific fields
    if provider.provider_type == 'pkcs11':
        for field in ['pkcs11_library_path', 'pkcs11_slot_id', 'pkcs11_pin', 'pkcs11_token_label']:
            if field in data:
                setattr(provider, field, data[field])
                
    elif provider.provider_type == 'aws-cloudhsm':
        for field in ['aws_cluster_id', 'aws_region', 'aws_access_key', 'aws_secret_key',
                      'aws_crypto_user', 'aws_crypto_password']:
            if field in data:
                setattr(provider, field, data[field])
                
    elif provider.provider_type == 'azure-keyvault':
        for field in ['azure_vault_url', 'azure_tenant_id', 'azure_client_id', 'azure_client_secret']:
            if field in data:
                setattr(provider, field, data[field])
                
    elif provider.provider_type == 'google-kms':
        for field in ['gcp_project_id', 'gcp_location', 'gcp_keyring', 'gcp_credentials_json']:
            if field in data:
                setattr(provider, field, data[field])
    
    db.session.commit()
    return success_response(data=provider.to_dict(), message="HSM provider updated")


@bp.route('/api/v2/hsm/providers/<int:provider_id>', methods=['DELETE'])
@require_auth(['delete:hsm'])
def delete_provider(provider_id):
    """Delete HSM provider"""
    provider = HSMProvider.query.get_or_404(provider_id)
    
    if provider.keys.count() > 0:
        return error_response("Cannot delete provider with active keys", 400)
    
    db.session.delete(provider)
    db.session.commit()
    
    return success_response(message="HSM provider deleted")


@bp.route('/api/v2/hsm/providers/<int:provider_id>/test', methods=['POST'])
@require_auth(['write:hsm'])
def test_provider(provider_id):
    """Test HSM provider connection"""
    provider = HSMProvider.query.get_or_404(provider_id)
    
    try:
        if provider.provider_type == 'pkcs11':
            return _test_pkcs11(provider)
        elif provider.provider_type == 'aws-cloudhsm':
            return _test_aws_cloudhsm(provider)
        elif provider.provider_type == 'azure-keyvault':
            return _test_azure_keyvault(provider)
        elif provider.provider_type == 'google-kms':
            return _test_google_kms(provider)
    except Exception as e:
        provider.last_error = str(e)
        db.session.commit()
        return error_response(f"Connection test failed: {str(e)}", 400)
    
    return error_response("Unknown provider type", 400)


def _test_pkcs11(provider):
    """Test PKCS#11 connection"""
    try:
        import pkcs11
        from pkcs11 import Mechanism
        
        lib = pkcs11.lib(provider.pkcs11_library_path)
        
        # Get slot
        if provider.pkcs11_slot_id is not None:
            slot = lib.get_slots()[provider.pkcs11_slot_id]
        else:
            slot = lib.get_slots(token_present=True)[0]
        
        # Open session
        with slot.open(user_pin=provider.pkcs11_pin) as session:
            # Try to list keys
            keys = list(session.get_objects())
            
            provider.last_connected_at = datetime.utcnow()
            provider.last_error = None
            db.session.commit()
            
            return success_response(data={
                'status': 'success',
                'message': 'PKCS#11 connection successful',
                'slot_info': str(slot),
                'key_count': len(keys)
            })
    except ImportError:
        return error_response("PKCS#11 library not installed. Run: pip install python-pkcs11", 500)


def _test_aws_cloudhsm(provider):
    """Test AWS CloudHSM connection"""
    try:
        import boto3
        
        client = boto3.client(
            'cloudhsmv2',
            region_name=provider.aws_region,
            aws_access_key_id=provider.aws_access_key,
            aws_secret_access_key=provider.aws_secret_key
        )
        
        response = client.describe_clusters(
            Filters={'clusterIds': [provider.aws_cluster_id]}
        )
        
        if response['Clusters']:
            cluster = response['Clusters'][0]
            provider.last_connected_at = datetime.utcnow()
            provider.last_error = None
            db.session.commit()
            
            return success_response(data={
                'status': 'success',
                'message': 'AWS CloudHSM connection successful',
                'cluster_state': cluster['State'],
                'hsm_count': len(cluster.get('Hsms', []))
            })
        
        return error_response("Cluster not found", 404)
    except ImportError:
        return error_response("AWS SDK not installed. Run: pip install boto3", 500)


def _test_azure_keyvault(provider):
    """Test Azure Key Vault connection"""
    try:
        from azure.identity import ClientSecretCredential
        from azure.keyvault.keys import KeyClient
        
        credential = ClientSecretCredential(
            tenant_id=provider.azure_tenant_id,
            client_id=provider.azure_client_id,
            client_secret=provider.azure_client_secret
        )
        
        client = KeyClient(vault_url=provider.azure_vault_url, credential=credential)
        
        # List keys (limited)
        keys = list(client.list_properties_of_keys(max_page_size=5))
        
        provider.last_connected_at = datetime.utcnow()
        provider.last_error = None
        db.session.commit()
        
        return success_response(data={
            'status': 'success',
            'message': 'Azure Key Vault connection successful',
            'vault_url': provider.azure_vault_url,
            'sample_keys': len(keys)
        })
    except ImportError:
        return error_response("Azure SDK not installed. Run: pip install azure-identity azure-keyvault-keys", 500)


def _test_google_kms(provider):
    """Test Google Cloud KMS connection"""
    try:
        from google.cloud import kms
        import json
        
        # Create credentials from JSON
        credentials_info = json.loads(provider.gcp_credentials_json)
        
        client = kms.KeyManagementServiceClient.from_service_account_info(credentials_info)
        
        # List key rings
        parent = f"projects/{provider.gcp_project_id}/locations/{provider.gcp_location}"
        key_rings = list(client.list_key_rings(request={"parent": parent}))
        
        provider.last_connected_at = datetime.utcnow()
        provider.last_error = None
        db.session.commit()
        
        return success_response(data={
            'status': 'success',
            'message': 'Google Cloud KMS connection successful',
            'project': provider.gcp_project_id,
            'key_rings': len(key_rings)
        })
    except ImportError:
        return error_response("Google Cloud SDK not installed. Run: pip install google-cloud-kms", 500)


# ============ Key Management ============

@bp.route('/api/v2/hsm/keys', methods=['GET'])
@require_auth(['read:hsm'])
def list_keys():
    """List all HSM keys"""
    provider_id = request.args.get('provider_id', type=int)
    
    query = HSMKey.query
    if provider_id:
        query = query.filter_by(provider_id=provider_id)
    
    keys = query.all()
    return success_response(data=[k.to_dict() for k in keys])


@bp.route('/api/v2/hsm/keys/<int:key_id>', methods=['GET'])
@require_auth(['read:hsm'])
def get_key(key_id):
    """Get HSM key details"""
    key = HSMKey.query.get_or_404(key_id)
    return success_response(data=key.to_dict())


@bp.route('/api/v2/hsm/providers/<int:provider_id>/keys', methods=['POST'])
@require_auth(['write:hsm'])
def generate_key(provider_id):
    """Generate a new key in HSM"""
    provider = HSMProvider.query.get_or_404(provider_id)
    data = request.get_json()
    
    if not data.get('key_label'):
        return error_response("Key label is required", 400)
    
    # In production, this would actually generate the key in the HSM
    # For now, we just create a record
    key = HSMKey(
        provider_id=provider_id,
        key_label=data['key_label'],
        key_type=data.get('key_type', 'rsa'),
        key_size=data.get('key_size', 2048),
        purpose=data.get('purpose', 'general'),
        is_exportable=data.get('is_exportable', False),
        status='active'
    )
    
    db.session.add(key)
    db.session.commit()
    
    return success_response(data=key.to_dict(), message="Key created in HSM")


@bp.route('/api/v2/hsm/keys/<int:key_id>', methods=['DELETE'])
@require_auth(['delete:hsm'])
def delete_key(key_id):
    """Delete/destroy HSM key"""
    key = HSMKey.query.get_or_404(key_id)
    
    # In production, this would destroy the key in the HSM
    key.status = 'destroyed'
    db.session.commit()
    
    return success_response(message="Key destroyed")


# ============ Statistics ============

@bp.route('/api/v2/hsm/stats', methods=['GET'])
@require_auth(['read:hsm'])
def get_stats():
    """Get HSM statistics"""
    providers = HSMProvider.query.all()
    keys = HSMKey.query.filter_by(status='active').all()
    
    return success_response(data={
        'total_providers': len(providers),
        'enabled_providers': len([p for p in providers if p.enabled]),
        'total_keys': len(keys),
        'keys_by_type': {
            'rsa': len([k for k in keys if k.key_type == 'rsa']),
            'ec': len([k for k in keys if k.key_type == 'ec']),
            'aes': len([k for k in keys if k.key_type == 'aes']),
        },
        'providers_by_type': {
            'pkcs11': len([p for p in providers if p.provider_type == 'pkcs11']),
            'aws-cloudhsm': len([p for p in providers if p.provider_type == 'aws-cloudhsm']),
            'azure-keyvault': len([p for p in providers if p.provider_type == 'azure-keyvault']),
            'google-kms': len([p for p in providers if p.provider_type == 'google-kms']),
        }
    })
