"""
HSM Service Package
Hardware Security Module integration for UCM

Supports:
- PKCS#11 (SoftHSM, Thales, nCipher, AWS CloudHSM)
- Azure Key Vault (Premium tier with HSM)
- Google Cloud KMS (Cloud HSM)
"""

from .hsm_service import HsmService
from .base_provider import BaseHsmProvider

__all__ = ['HsmService', 'BaseHsmProvider']


# Auto-register available providers
def _register_providers():
    """Register all available HSM providers"""
    
    # PKCS#11 Provider (SoftHSM, Thales, nCipher, AWS CloudHSM)
    try:
        from .pkcs11_provider import Pkcs11Provider, is_available
        if is_available():
            HsmService.register_provider('pkcs11', Pkcs11Provider)
            HsmService.register_provider('aws-cloudhsm', Pkcs11Provider)  # AWS CloudHSM uses PKCS#11
    except ImportError:
        pass
    
    # Azure Key Vault Provider
    try:
        from .azure_provider import AzureKeyVaultProvider, is_available
        if is_available():
            HsmService.register_provider('azure-keyvault', AzureKeyVaultProvider)
    except ImportError:
        pass
    
    # Google Cloud KMS Provider
    try:
        from .gcp_provider import GcpKmsProvider, is_available
        if is_available():
            HsmService.register_provider('google-kms', GcpKmsProvider)
    except ImportError:
        pass


# Register providers on import
_register_providers()
