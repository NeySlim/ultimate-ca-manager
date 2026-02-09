"""
HSM Management Routes v2.0
/api/v2/hsm/* - Hardware Security Module management

Supports:
- PKCS#11 (SoftHSM, Thales, nCipher, AWS CloudHSM)
- Azure Key Vault
- Google Cloud KMS
"""

from flask import Blueprint, request, g
from auth.unified import require_auth
from utils.response import success_response, error_response, created_response, no_content_response
from services.hsm import HsmService
from services.hsm.base_provider import HsmError, HsmConnectionError, HsmOperationError, HsmConfigError
from models.hsm import HsmProvider, HsmKey
from services.audit_service import AuditService
import logging

bp = Blueprint('hsm_v2', __name__)
logger = logging.getLogger(__name__)


# =============================================================================
# PROVIDERS CRUD
# =============================================================================

@bp.route('/api/v2/hsm/providers', methods=['GET'])
@require_auth(['read:hsm'])
def list_providers():
    """
    List all HSM providers
    
    Returns:
        List of provider objects with status and key counts
    """
    providers = HsmService.list_providers()
    return success_response(data=providers)


@bp.route('/api/v2/hsm/providers', methods=['POST'])
@require_auth(['write:hsm'])
def create_provider():
    """
    Create a new HSM provider
    
    Body:
        name: Unique provider name
        type: Provider type (pkcs11, azure-keyvault, google-kms, aws-cloudhsm)
        config: Provider-specific configuration
    """
    data = request.get_json()
    
    if not data:
        return error_response('Request body required', 400)
    
    name = data.get('name', '').strip()
    provider_type = data.get('type', '').strip()
    config = data.get('config', {})
    
    # Validation
    if not name:
        return error_response('Provider name is required', 400)
    
    if len(name) > 255:
        return error_response('Provider name must be 255 characters or less', 400)
    
    if not provider_type:
        return error_response('Provider type is required', 400)
    
    if provider_type not in HsmProvider.VALID_TYPES:
        return error_response(
            f"Invalid provider type. Valid types: {', '.join(HsmProvider.VALID_TYPES)}",
            400
        )
    
    if not isinstance(config, dict):
        return error_response('Config must be an object', 400)
    
    try:
        user_id = getattr(g, 'user', {}).get('id') if hasattr(g, 'user') else None
        
        provider = HsmService.create_provider(
            name=name,
            provider_type=provider_type,
            config=config,
            created_by=user_id
        )
        
        AuditService.log_action(
            action='hsm_provider_created',
            resource_type='hsm_provider',
            resource_id=provider.id,
            resource_name=name,
            details=f'Created HSM provider: {name} ({provider_type})',
            success=True
        )
        
        return created_response(data=provider.to_dict())
        
    except ValueError as e:
        return error_response(str(e), 400)
    except Exception as e:
        logger.exception(f"Failed to create HSM provider: {name}")
        return error_response(f'Failed to create provider: {str(e)}', 500)


@bp.route('/api/v2/hsm/providers/<int:provider_id>', methods=['GET'])
@require_auth(['read:hsm'])
def get_provider(provider_id):
    """Get HSM provider details"""
    provider = HsmService.get_provider(provider_id)
    
    if not provider:
        return error_response('Provider not found', 404)
    
    # Include masked config in single-provider view
    return success_response(data=provider.to_dict(include_config=True))


@bp.route('/api/v2/hsm/providers/<int:provider_id>', methods=['PUT'])
@require_auth(['write:hsm'])
def update_provider(provider_id):
    """
    Update an HSM provider
    
    Body:
        name: New name (optional)
        config: New configuration (optional)
    """
    provider = HsmService.get_provider(provider_id)
    if not provider:
        return error_response('Provider not found', 404)
    
    data = request.get_json()
    if not data:
        return error_response('Request body required', 400)
    
    name = data.get('name')
    config = data.get('config')
    
    if name is not None:
        name = name.strip()
        if not name:
            return error_response('Provider name cannot be empty', 400)
        if len(name) > 255:
            return error_response('Provider name must be 255 characters or less', 400)
    
    if config is not None and not isinstance(config, dict):
        return error_response('Config must be an object', 400)
    
    try:
        updated = HsmService.update_provider(
            provider_id=provider_id,
            name=name,
            config=config
        )
        
        AuditService.log_action(
            action='hsm_provider_updated',
            resource_type='hsm_provider',
            resource_id=provider_id,
            resource_name=updated.name,
            details=f'Updated HSM provider: {updated.name}',
            success=True
        )
        
        return success_response(data=updated.to_dict(include_config=True))
        
    except ValueError as e:
        return error_response(str(e), 400)
    except Exception as e:
        logger.exception(f"Failed to update HSM provider: {provider_id}")
        return error_response(f'Failed to update provider: {str(e)}', 500)


@bp.route('/api/v2/hsm/providers/<int:provider_id>', methods=['DELETE'])
@require_auth(['delete:hsm'])
def delete_provider(provider_id):
    """Delete an HSM provider and all its keys"""
    provider = HsmService.get_provider(provider_id)
    if not provider:
        return error_response('Provider not found', 404)
    
    name = provider.name
    
    try:
        HsmService.delete_provider(provider_id)
        
        AuditService.log_action(
            action='hsm_provider_deleted',
            resource_type='hsm_provider',
            resource_id=provider_id,
            resource_name=name,
            details=f'Deleted HSM provider: {name}',
            success=True
        )
        
        return no_content_response()
        
    except ValueError as e:
        return error_response(str(e), 400)
    except Exception as e:
        logger.exception(f"Failed to delete HSM provider: {provider_id}")
        return error_response(f'Failed to delete provider: {str(e)}', 500)


@bp.route('/api/v2/hsm/providers/<int:provider_id>/test', methods=['POST'])
@require_auth(['write:hsm'])
def test_provider(provider_id):
    """Test connection to an HSM provider"""
    provider = HsmService.get_provider(provider_id)
    if not provider:
        return error_response('Provider not found', 404)
    
    try:
        result = HsmService.test_provider(provider_id)
        
        AuditService.log_action(
            action='hsm_provider_tested',
            resource_type='hsm_provider',
            resource_id=provider_id,
            resource_name=provider.name,
            details=f"HSM test: {'success' if result.get('success') else 'failed'}",
            success=result.get('success', False)
        )
        
        return success_response(data=result)
        
    except HsmConfigError as e:
        return error_response(str(e), 400)
    except Exception as e:
        logger.exception(f"Failed to test HSM provider: {provider_id}")
        return error_response(f'Failed to test provider: {str(e)}', 500)


@bp.route('/api/v2/hsm/providers/<int:provider_id>/sync', methods=['POST'])
@require_auth(['write:hsm'])
def sync_provider_keys(provider_id):
    """Sync keys from HSM to database"""
    provider = HsmService.get_provider(provider_id)
    if not provider:
        return error_response('Provider not found', 404)
    
    try:
        result = HsmService.sync_keys(provider_id)
        
        AuditService.log_action(
            action='hsm_keys_synced',
            resource_type='hsm_provider',
            resource_id=provider_id,
            resource_name=provider.name,
            details=f"Synced keys: +{result['added']} -{result['removed']} ={result['unchanged']}",
            success=True
        )
        
        return success_response(data=result)
        
    except HsmError as e:
        return error_response(str(e), 500)
    except Exception as e:
        logger.exception(f"Failed to sync HSM keys: {provider_id}")
        return error_response(f'Failed to sync keys: {str(e)}', 500)


# =============================================================================
# KEYS CRUD
# =============================================================================

@bp.route('/api/v2/hsm/keys', methods=['GET'])
@require_auth(['read:hsm'])
def list_keys():
    """
    List HSM keys
    
    Query params:
        provider_id: Filter by provider (optional)
    """
    provider_id = request.args.get('provider_id', type=int)
    
    if provider_id:
        provider = HsmService.get_provider(provider_id)
        if not provider:
            return error_response('Provider not found', 404)
    
    keys = HsmService.list_keys(provider_id=provider_id)
    return success_response(data=keys)


@bp.route('/api/v2/hsm/providers/<int:provider_id>/keys', methods=['POST'])
@require_auth(['write:hsm'])
def generate_key(provider_id):
    """
    Generate a new key in the HSM
    
    Body:
        label: Human-readable key label
        algorithm: Key algorithm (RSA-2048, RSA-4096, EC-P256, EC-P384, AES-256, etc.)
        purpose: Key purpose (signing, encryption, wrapping, all)
        extractable: Whether key can be exported (default: false)
    """
    provider = HsmService.get_provider(provider_id)
    if not provider:
        return error_response('Provider not found', 404)
    
    data = request.get_json()
    if not data:
        return error_response('Request body required', 400)
    
    label = data.get('label', '').strip()
    algorithm = data.get('algorithm', '').strip()
    purpose = data.get('purpose', 'signing').strip()
    extractable = data.get('extractable', False)
    
    # Validation
    if not label:
        return error_response('Key label is required', 400)
    
    if len(label) > 255:
        return error_response('Key label must be 255 characters or less', 400)
    
    if not algorithm:
        return error_response('Algorithm is required', 400)
    
    if algorithm not in HsmKey.VALID_ALGORITHMS:
        return error_response(
            f"Invalid algorithm. Valid algorithms: {', '.join(HsmKey.VALID_ALGORITHMS)}",
            400
        )
    
    if purpose not in HsmKey.VALID_PURPOSES:
        return error_response(
            f"Invalid purpose. Valid purposes: {', '.join(HsmKey.VALID_PURPOSES)}",
            400
        )
    
    try:
        key = HsmService.generate_key(
            provider_id=provider_id,
            label=label,
            algorithm=algorithm,
            purpose=purpose,
            extractable=bool(extractable)
        )
        
        AuditService.log_action(
            action='hsm_key_generated',
            resource_type='hsm_key',
            resource_id=key.id,
            resource_name=label,
            details=f'Generated HSM key: {label} ({algorithm}) in {provider.name}',
            success=True
        )
        
        return created_response(data=key.to_dict())
        
    except ValueError as e:
        return error_response(str(e), 400)
    except HsmError as e:
        return error_response(str(e), 500)
    except Exception as e:
        logger.exception(f"Failed to generate HSM key: {label}")
        return error_response(f'Failed to generate key: {str(e)}', 500)


@bp.route('/api/v2/hsm/keys/<int:key_id>', methods=['GET'])
@require_auth(['read:hsm'])
def get_key(key_id):
    """Get HSM key details"""
    key = HsmService.get_key(key_id)
    
    if not key:
        return error_response('Key not found', 404)
    
    return success_response(data=key.to_dict())


@bp.route('/api/v2/hsm/keys/<int:key_id>', methods=['DELETE'])
@require_auth(['delete:hsm'])
def delete_key(key_id):
    """Delete a key from the HSM"""
    key = HsmService.get_key(key_id)
    if not key:
        return error_response('Key not found', 404)
    
    label = key.label
    provider_name = key.provider.name
    
    try:
        HsmService.delete_key(key_id)
        
        AuditService.log_action(
            action='hsm_key_deleted',
            resource_type='hsm_key',
            resource_id=key_id,
            resource_name=label,
            details=f'Deleted HSM key: {label} from {provider_name}',
            success=True
        )
        
        return no_content_response()
        
    except HsmError as e:
        return error_response(str(e), 500)
    except Exception as e:
        logger.exception(f"Failed to delete HSM key: {key_id}")
        return error_response(f'Failed to delete key: {str(e)}', 500)


@bp.route('/api/v2/hsm/keys/<int:key_id>/public', methods=['GET'])
@require_auth(['read:hsm'])
def get_public_key(key_id):
    """Get public key in PEM format (for asymmetric keys only)"""
    key = HsmService.get_key(key_id)
    if not key:
        return error_response('Key not found', 404)
    
    if key.key_type != 'asymmetric':
        return error_response('Public key only available for asymmetric keys', 400)
    
    try:
        pem = HsmService.get_public_key(key_id)
        return success_response(data={'pem': pem})
        
    except HsmError as e:
        return error_response(str(e), 500)
    except Exception as e:
        logger.exception(f"Failed to get public key: {key_id}")
        return error_response(f'Failed to get public key: {str(e)}', 500)


@bp.route('/api/v2/hsm/keys/<int:key_id>/sign', methods=['POST'])
@require_auth(['write:hsm'])
def sign_data(key_id):
    """
    Sign data using HSM key
    
    Body:
        data: Base64-encoded data to sign
        algorithm: Signature algorithm (optional, uses default for key type)
    """
    key = HsmService.get_key(key_id)
    if not key:
        return error_response('Key not found', 404)
    
    if key.purpose not in ('signing', 'all'):
        return error_response('This key is not authorized for signing', 400)
    
    data = request.get_json()
    if not data:
        return error_response('Request body required', 400)
    
    data_b64 = data.get('data')
    algorithm = data.get('algorithm')
    
    if not data_b64:
        return error_response('Data is required (base64-encoded)', 400)
    
    try:
        import base64
        data_bytes = base64.b64decode(data_b64)
    except Exception:
        return error_response('Invalid base64 data', 400)
    
    try:
        signature = HsmService.sign(key_id, data_bytes, algorithm)
        
        import base64
        signature_b64 = base64.b64encode(signature).decode('ascii')
        
        AuditService.log_action(
            action='hsm_key_used_sign',
            resource_type='hsm_key',
            resource_id=key_id,
            resource_name=key.label,
            details=f'Signed {len(data_bytes)} bytes with {key.label}',
            success=True
        )
        
        return success_response(data={'signature': signature_b64})
        
    except HsmError as e:
        return error_response(str(e), 500)
    except Exception as e:
        logger.exception(f"Failed to sign with HSM key: {key_id}")
        return error_response(f'Failed to sign: {str(e)}', 500)


# =============================================================================
# PROVIDER INFO
# =============================================================================

@bp.route('/api/v2/hsm/provider-types', methods=['GET'])
@require_auth(['read:hsm'])
def get_provider_types():
    """Get available HSM provider types and their configuration schemas"""
    
    available = HsmService.get_available_providers()
    
    types = [
        {
            'type': 'pkcs11',
            'label': 'PKCS#11 (Local HSM)',
            'description': 'PKCS#11 compatible HSM including SoftHSM, Thales, nCipher',
            'available': 'pkcs11' in available,
            'config_schema': {
                'module_path': {'type': 'string', 'required': True, 'description': 'Path to PKCS#11 library'},
                'token_label': {'type': 'string', 'required': True, 'description': 'Token label'},
                'user_pin': {'type': 'password', 'required': True, 'description': 'User PIN'},
                'slot_index': {'type': 'number', 'required': False, 'description': 'Slot index (default: 0)'}
            }
        },
        {
            'type': 'aws-cloudhsm',
            'label': 'AWS CloudHSM',
            'description': 'AWS CloudHSM via PKCS#11 library',
            'available': 'pkcs11' in available,  # Uses PKCS#11
            'config_schema': {
                'module_path': {'type': 'string', 'required': True, 'description': 'Path to CloudHSM PKCS#11 library'},
                'hsm_user': {'type': 'string', 'required': True, 'description': 'HSM crypto user name'},
                'hsm_password': {'type': 'password', 'required': True, 'description': 'HSM user password'},
                'cluster_id': {'type': 'string', 'required': False, 'description': 'CloudHSM cluster ID'}
            }
        },
        {
            'type': 'azure-keyvault',
            'label': 'Azure Key Vault',
            'description': 'Azure Key Vault for cloud key management',
            'available': 'azure-keyvault' in available,
            'config_schema': {
                'vault_url': {'type': 'string', 'required': True, 'description': 'Key Vault URL'},
                'tenant_id': {'type': 'string', 'required': True, 'description': 'Azure AD tenant ID'},
                'client_id': {'type': 'string', 'required': True, 'description': 'Application client ID'},
                'client_secret': {'type': 'password', 'required': True, 'description': 'Application client secret'},
                'use_managed_identity': {'type': 'boolean', 'required': False, 'description': 'Use managed identity instead of client credentials'}
            }
        },
        {
            'type': 'google-kms',
            'label': 'Google Cloud KMS',
            'description': 'Google Cloud Key Management Service',
            'available': 'google-kms' in available,
            'config_schema': {
                'project_id': {'type': 'string', 'required': True, 'description': 'GCP project ID'},
                'location': {'type': 'string', 'required': True, 'description': 'Key ring location (e.g., us-east1)'},
                'key_ring': {'type': 'string', 'required': True, 'description': 'Key ring name'},
                'service_account_json': {'type': 'textarea', 'required': True, 'description': 'Service account JSON key'}
            }
        }
    ]
    
    return success_response(data=types)


@bp.route('/api/v2/hsm/dependencies', methods=['GET'])
@require_auth(['read:hsm'])
def get_dependencies_status():
    """
    Get HSM dependencies installation status
    
    Returns status for each provider type:
    - installed: True if Python packages are installed
    - packages: List of required pip packages
    - install_command: Command to install the packages
    """
    
    dependencies = []
    
    # Check PKCS#11
    try:
        import pkcs11
        pkcs11_installed = True
    except ImportError:
        pkcs11_installed = False
    
    dependencies.append({
        'provider': 'pkcs11',
        'label': 'PKCS#11 (SoftHSM, Thales, nCipher, AWS CloudHSM)',
        'installed': pkcs11_installed,
        'packages': ['python-pkcs11>=0.7.0'],
        'install_command': 'pip install python-pkcs11',
        'system_packages': {
            'debian': 'apt install softhsm2',
            'rhel': 'dnf install softhsm'
        }
    })
    
    # Check Azure
    try:
        from azure.keyvault.keys import KeyClient
        from azure.identity import DefaultAzureCredential
        azure_installed = True
    except ImportError:
        azure_installed = False
    
    dependencies.append({
        'provider': 'azure-keyvault',
        'label': 'Azure Key Vault',
        'installed': azure_installed,
        'packages': ['azure-keyvault-keys>=4.9.0', 'azure-identity>=1.15.0'],
        'install_command': 'pip install azure-keyvault-keys azure-identity'
    })
    
    # Check GCP
    try:
        from google.cloud import kms_v1
        gcp_installed = True
    except ImportError:
        gcp_installed = False
    
    dependencies.append({
        'provider': 'google-kms',
        'label': 'Google Cloud KMS',
        'installed': gcp_installed,
        'packages': ['google-cloud-kms>=2.21.0'],
        'install_command': 'pip install google-cloud-kms'
    })
    
    return success_response(data={
        'dependencies': dependencies,
        'install_script': '/opt/ucm/backend/scripts/install_hsm_deps.py'
    })


@bp.route('/api/v2/hsm/dependencies/install', methods=['POST'])
@require_auth(['admin'])
def install_dependencies():
    """
    Install HSM dependencies (requires admin)
    
    Body:
        provider: Provider type to install (pkcs11, azure, gcp, all)
    
    Note: This runs pip install which may take a moment.
    In production, prefer installing via system packages.
    """
    import subprocess
    import sys
    
    data = request.get_json() or {}
    provider = data.get('provider', '').lower()
    
    if not provider:
        return error_response('Provider type required (pkcs11, azure, gcp, all)', 400)
    
    packages_map = {
        'pkcs11': ['python-pkcs11'],
        'azure': ['azure-keyvault-keys', 'azure-identity'],
        'gcp': ['google-cloud-kms'],
    }
    
    if provider == 'all':
        packages = []
        for pkgs in packages_map.values():
            packages.extend(pkgs)
    elif provider in packages_map:
        packages = packages_map[provider]
    else:
        return error_response(f'Unknown provider: {provider}. Use: pkcs11, azure, gcp, all', 400)
    
    try:
        # Run pip install
        result = subprocess.run(
            [sys.executable, '-m', 'pip', 'install', '--quiet'] + packages,
            capture_output=True,
            text=True,
            timeout=120
        )
        
        if result.returncode == 0:
            # Log the action
            AuditService.log(
                action='hsm.dependencies.install',
                user_id=g.current_user.id if hasattr(g, 'current_user') else None,
                details={'provider': provider, 'packages': packages}
            )
            
            return success_response(
                message=f'Successfully installed {provider} dependencies',
                data={'packages': packages}
            )
        else:
            return error_response(
                f'Installation failed: {result.stderr}',
                500
            )
            
    except subprocess.TimeoutExpired:
        return error_response('Installation timed out', 504)
    except Exception as e:
        logger.exception(f"Failed to install HSM dependencies: {e}")
        return error_response(f'Installation error: {str(e)}', 500)
