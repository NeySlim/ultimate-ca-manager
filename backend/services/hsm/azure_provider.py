"""
Azure Key Vault HSM Provider

Based on azure-keyvault-keys and azure-identity libraries.
Supports Azure Key Vault Premium (HSM-backed keys) and Standard tiers.
"""

import logging
from typing import Dict, List, Optional, Any

from services.hsm.base_provider import (
    BaseHsmProvider, HsmKeyInfo,
    HsmConnectionError, HsmOperationError, HsmKeyNotFoundError, HsmConfigError
)

logger = logging.getLogger(__name__)

# Try to import Azure libraries - they're optional
AZURE_AVAILABLE = False
ALGORITHM_TO_AZURE = {}
SIGN_ALGORITHMS = {}

try:
    from azure.keyvault.keys import KeyClient, KeyType, KeyCurveName
    from azure.keyvault.keys.crypto import CryptographyClient, SignatureAlgorithm
    from azure.identity import DefaultAzureCredential, ClientSecretCredential
    from azure.core.exceptions import AzureError, ResourceNotFoundError
    AZURE_AVAILABLE = True
    
    # Algorithm mappings (only defined if azure is available)
    ALGORITHM_TO_AZURE = {
        'RSA-2048': (KeyType.rsa_hsm, 2048),
        'RSA-3072': (KeyType.rsa_hsm, 3072),
        'RSA-4096': (KeyType.rsa_hsm, 4096),
        'EC-P256': (KeyType.ec_hsm, KeyCurveName.p256),
        'EC-P384': (KeyType.ec_hsm, KeyCurveName.p384),
        'EC-P521': (KeyType.ec_hsm, KeyCurveName.p521),
    }
    
    # Signature algorithms
    SIGN_ALGORITHMS = {
        'RSA-2048': SignatureAlgorithm.rs256,
        'RSA-3072': SignatureAlgorithm.rs384,
        'RSA-4096': SignatureAlgorithm.rs512,
        'EC-P256': SignatureAlgorithm.es256,
        'EC-P384': SignatureAlgorithm.es384,
        'EC-P521': SignatureAlgorithm.es512,
    }
except ImportError:
    pass


class AzureKeyVaultProvider(BaseHsmProvider):
    """
    Azure Key Vault HSM Provider
    
    Config:
        vault_url: Key Vault URL (https://<vault-name>.vault.azure.net/)
        tenant_id: Azure AD tenant ID (optional if using managed identity)
        client_id: Azure AD application ID (optional if using managed identity)
        client_secret: Azure AD client secret (optional if using managed identity)
        use_managed_identity: Use Azure Managed Identity (default: True)
    """
    
    def __init__(self, config: Dict[str, Any]):
        if not AZURE_AVAILABLE:
            raise HsmConfigError(
                "Azure libraries not installed. "
                "Install with: pip install azure-keyvault-keys azure-identity"
            )
        
        super().__init__(config)
        
        # Validate config
        self.vault_url = config.get('vault_url')
        if not self.vault_url:
            raise HsmConfigError("vault_url is required")
        
        self.use_managed_identity = config.get('use_managed_identity', True)
        self.tenant_id = config.get('tenant_id')
        self.client_id = config.get('client_id')
        self.client_secret = config.get('client_secret')
        
        # If not using managed identity, require credentials
        if not self.use_managed_identity:
            if not self.tenant_id or not self.client_id or not self.client_secret:
                raise HsmConfigError(
                    "tenant_id, client_id, and client_secret are required "
                    "when not using managed identity"
                )
        
        self._credential = None
        self._key_client: Optional[KeyClient] = None
    
    def connect(self) -> bool:
        """Connect to Azure Key Vault"""
        try:
            # Create credential
            if self.use_managed_identity:
                self._credential = DefaultAzureCredential()
            else:
                self._credential = ClientSecretCredential(
                    tenant_id=self.tenant_id,
                    client_id=self.client_id,
                    client_secret=self.client_secret
                )
            
            # Create key client
            self._key_client = KeyClient(
                vault_url=self.vault_url,
                credential=self._credential
            )
            
            # Test connection by listing keys (limited)
            list(self._key_client.list_properties_of_keys(max_page_size=1))
            
            self._connected = True
            logger.info(f"Connected to Azure Key Vault: {self.vault_url}")
            return True
            
        except AzureError as e:
            self._connected = False
            raise HsmConnectionError(f"Azure Key Vault connection failed: {str(e)}")
        except Exception as e:
            self._connected = False
            raise HsmConnectionError(f"Connection failed: {str(e)}")
    
    def disconnect(self) -> None:
        """Disconnect from Azure Key Vault"""
        self._key_client = None
        self._credential = None
        self._connected = False
        logger.debug(f"Disconnected from Azure Key Vault: {self.vault_url}")
    
    def test_connection(self) -> Dict[str, Any]:
        """Test connection to Azure Key Vault"""
        try:
            self.connect()
            
            # Get vault info via a simple operation
            key_count = sum(1 for _ in self._key_client.list_properties_of_keys())
            
            info = {
                'success': True,
                'message': 'Connection successful',
                'details': {
                    'vault_url': self.vault_url,
                    'key_count': key_count,
                    'auth_method': 'managed_identity' if self.use_managed_identity else 'client_secret'
                }
            }
            
            self.disconnect()
            return info
            
        except HsmConnectionError as e:
            return {
                'success': False,
                'message': str(e)
            }
        except Exception as e:
            return {
                'success': False,
                'message': f"Test failed: {str(e)}"
            }
    
    def list_keys(self) -> List[HsmKeyInfo]:
        """List all keys in the Key Vault"""
        if not self._key_client:
            raise HsmOperationError("Not connected")
        
        keys = []
        
        try:
            for key_properties in self._key_client.list_properties_of_keys():
                # Get full key to access key type info
                try:
                    key = self._key_client.get_key(key_properties.name)
                    key_info = self._key_to_key_info(key)
                    if key_info:
                        keys.append(key_info)
                except Exception as e:
                    logger.warning(f"Failed to get key {key_properties.name}: {e}")
            
            return keys
            
        except AzureError as e:
            raise HsmOperationError(f"Failed to list keys: {str(e)}")
    
    def _key_to_key_info(self, key) -> Optional[HsmKeyInfo]:
        """Convert Azure Key to HsmKeyInfo"""
        try:
            key_type = key.key_type
            
            # Determine algorithm
            if key_type in (KeyType.rsa, KeyType.rsa_hsm):
                algorithm = f'RSA-{key.key.n.bit_length() if hasattr(key.key, "n") else 2048}'
            elif key_type in (KeyType.ec, KeyType.ec_hsm):
                curve = key.key.crv if hasattr(key.key, 'crv') else 'P-256'
                curve_map = {
                    KeyCurveName.p256: 'EC-P256',
                    KeyCurveName.p384: 'EC-P384',
                    KeyCurveName.p521: 'EC-P521',
                    'P-256': 'EC-P256',
                    'P-384': 'EC-P384',
                    'P-521': 'EC-P521',
                }
                algorithm = curve_map.get(curve, 'EC-P256')
            else:
                algorithm = str(key_type)
            
            # Determine purpose from key operations
            ops = key.key_operations or []
            can_sign = 'sign' in ops
            can_encrypt = 'encrypt' in ops or 'wrapKey' in ops
            
            if can_sign and can_encrypt:
                purpose = 'all'
            elif can_sign:
                purpose = 'signing'
            elif can_encrypt:
                purpose = 'encryption'
            else:
                purpose = 'all'
            
            # HSM keys are never extractable
            is_hsm = 'hsm' in str(key_type).lower()
            
            return HsmKeyInfo(
                key_identifier=key.id,
                label=key.name,
                algorithm=algorithm,
                key_type='asymmetric',  # Azure Key Vault mainly handles asymmetric
                purpose=purpose,
                is_extractable=not is_hsm
            )
            
        except Exception as e:
            logger.warning(f"Failed to parse key: {e}")
            return None
    
    def generate_key(
        self,
        label: str,
        algorithm: str,
        purpose: str = 'signing',
        extractable: bool = False
    ) -> HsmKeyInfo:
        """Generate a new key in Azure Key Vault"""
        if not self._key_client:
            raise HsmOperationError("Not connected")
        
        if algorithm not in ALGORITHM_TO_AZURE:
            raise HsmOperationError(f"Unsupported algorithm: {algorithm}")
        
        key_type, param = ALGORITHM_TO_AZURE[algorithm]
        
        try:
            # Determine key operations
            key_ops = []
            if purpose in ('signing', 'all'):
                key_ops.extend(['sign', 'verify'])
            if purpose in ('encryption', 'all'):
                key_ops.extend(['encrypt', 'decrypt', 'wrapKey', 'unwrapKey'])
            
            # Generate key
            if key_type in (KeyType.rsa, KeyType.rsa_hsm):
                key = self._key_client.create_rsa_key(
                    name=label,
                    size=param,
                    hsm=True,  # Always use HSM-backed
                    key_operations=key_ops,
                    exportable=extractable
                )
            elif key_type in (KeyType.ec, KeyType.ec_hsm):
                key = self._key_client.create_ec_key(
                    name=label,
                    curve=param,
                    hsm=True,
                    key_operations=key_ops,
                    exportable=extractable
                )
            else:
                raise HsmOperationError(f"Unsupported key type: {key_type}")
            
            # Export public key
            public_key_pem = self._export_public_key(key)
            
            logger.info(f"Generated key '{label}' ({algorithm}) in Azure Key Vault")
            
            return HsmKeyInfo(
                key_identifier=key.id,
                label=label,
                algorithm=algorithm,
                key_type='asymmetric',
                purpose=purpose,
                public_key_pem=public_key_pem,
                is_extractable=extractable
            )
            
        except AzureError as e:
            raise HsmOperationError(f"Failed to generate key: {str(e)}")
    
    def _export_public_key(self, key) -> Optional[str]:
        """Export public key as PEM"""
        try:
            from cryptography.hazmat.primitives import serialization
            from cryptography.hazmat.backends import default_backend
            
            jwk = key.key
            
            if key.key_type in (KeyType.rsa, KeyType.rsa_hsm):
                # Reconstruct RSA public key
                from cryptography.hazmat.primitives.asymmetric import rsa
                
                n = int.from_bytes(jwk.n, 'big')
                e = int.from_bytes(jwk.e, 'big')
                
                public_key = rsa.RSAPublicNumbers(e, n).public_key(default_backend())
                
            elif key.key_type in (KeyType.ec, KeyType.ec_hsm):
                # Reconstruct EC public key
                from cryptography.hazmat.primitives.asymmetric import ec
                
                curve_map = {
                    KeyCurveName.p256: ec.SECP256R1(),
                    KeyCurveName.p384: ec.SECP384R1(),
                    KeyCurveName.p521: ec.SECP521R1(),
                }
                
                x = int.from_bytes(jwk.x, 'big')
                y = int.from_bytes(jwk.y, 'big')
                curve = curve_map.get(jwk.crv, ec.SECP256R1())
                
                public_key = ec.EllipticCurvePublicNumbers(x, y, curve).public_key(default_backend())
            else:
                return None
            
            pem = public_key.public_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.PublicFormat.SubjectPublicKeyInfo
            )
            return pem.decode('utf-8')
            
        except Exception as e:
            logger.warning(f"Failed to export public key: {e}")
            return None
    
    def delete_key(self, key_identifier: str) -> bool:
        """Delete a key from Azure Key Vault"""
        if not self._key_client:
            raise HsmOperationError("Not connected")
        
        try:
            # Extract key name from identifier
            # Format: https://<vault>.vault.azure.net/keys/<name>/<version>
            key_name = key_identifier.split('/keys/')[-1].split('/')[0]
            
            # Delete key (soft delete)
            poller = self._key_client.begin_delete_key(key_name)
            poller.result()  # Wait for deletion
            
            # Purge if needed
            try:
                self._key_client.purge_deleted_key(key_name)
            except Exception:
                pass  # Purge may fail if not supported
            
            logger.info(f"Deleted key {key_name} from Azure Key Vault")
            return True
            
        except ResourceNotFoundError:
            raise HsmKeyNotFoundError(f"Key not found: {key_identifier}")
        except AzureError as e:
            raise HsmOperationError(f"Failed to delete key: {str(e)}")
    
    def get_public_key(self, key_identifier: str) -> str:
        """Get public key in PEM format"""
        if not self._key_client:
            raise HsmOperationError("Not connected")
        
        try:
            # Extract key name
            key_name = key_identifier.split('/keys/')[-1].split('/')[0]
            
            key = self._key_client.get_key(key_name)
            pem = self._export_public_key(key)
            
            if not pem:
                raise HsmOperationError("Failed to export public key")
            
            return pem
            
        except ResourceNotFoundError:
            raise HsmKeyNotFoundError(f"Key not found: {key_identifier}")
        except AzureError as e:
            raise HsmOperationError(f"Failed to get public key: {str(e)}")
    
    def sign(
        self,
        key_identifier: str,
        data: bytes,
        algorithm: Optional[str] = None
    ) -> bytes:
        """Sign data using Azure Key Vault key"""
        if not self._key_client:
            raise HsmOperationError("Not connected")
        
        try:
            # Extract key name
            key_name = key_identifier.split('/keys/')[-1].split('/')[0]
            
            # Get key to determine algorithm
            key = self._key_client.get_key(key_name)
            
            # Determine signature algorithm
            if algorithm and algorithm in SIGN_ALGORITHMS:
                sign_alg = SIGN_ALGORITHMS[algorithm]
            else:
                # Default based on key type
                if key.key_type in (KeyType.rsa, KeyType.rsa_hsm):
                    sign_alg = SignatureAlgorithm.rs256
                elif key.key_type in (KeyType.ec, KeyType.ec_hsm):
                    sign_alg = SignatureAlgorithm.es256
                else:
                    raise HsmOperationError(f"Unsupported key type: {key.key_type}")
            
            # Hash the data first (Azure expects a digest)
            import hashlib
            if 'rs256' in str(sign_alg).lower() or 'es256' in str(sign_alg).lower():
                digest = hashlib.sha256(data).digest()
            elif 'rs384' in str(sign_alg).lower() or 'es384' in str(sign_alg).lower():
                digest = hashlib.sha384(data).digest()
            else:
                digest = hashlib.sha512(data).digest()
            
            # Create crypto client and sign
            crypto_client = CryptographyClient(key, credential=self._credential)
            result = crypto_client.sign(sign_alg, digest)
            
            logger.debug(f"Signed {len(data)} bytes with key {key_name}")
            return result.signature
            
        except ResourceNotFoundError:
            raise HsmKeyNotFoundError(f"Key not found: {key_identifier}")
        except AzureError as e:
            raise HsmOperationError(f"Signing failed: {str(e)}")


def is_available() -> bool:
    """Check if Azure Key Vault provider is available"""
    return AZURE_AVAILABLE
