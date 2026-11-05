"""
Google Cloud KMS HSM Provider

Based on google-cloud-kms library.
Supports Google Cloud HSM (Cloud HSM) and software-backed keys.
"""

import logging
from typing import Dict, List, Optional, Any

from utils import key_algorithms
from services.hsm.base_provider import (
    BaseHsmProvider, HsmKeyInfo,
    HsmConnectionError, HsmOperationError, HsmKeyExistsError, HsmKeyNotFoundError, HsmConfigError
)

logger = logging.getLogger(__name__)

# Try to import Google Cloud libraries - they're optional
GCP_AVAILABLE = False
ALGORITHM_TO_GCP = {}
PURPOSE_TO_GCP = {}
GCP_ALGORITHM_NAMES = {}
# Mapped from the KMS API, not run against the service (google-cloud-kms 3.4+ names them)
UNTESTED_ALGORITHMS = frozenset({'ML-DSA-44', 'ML-DSA-65', 'ML-DSA-87'})
# AsymmetricSignRequest.data is capped at 64 KiB (the gcloud CLI enforces 65536 bytes):
# an ML-DSA version signs the data itself, so a CRL past that size cannot be signed.
KMS_SIGN_DATA_MAX = 64 * 1024
ML_DSA_VERSIONS = {}  # KMS algorithm -> label, versions that sign the data itself

try:
    from google.cloud import kms_v1
    from google.cloud.kms_v1 import types as kms_types
    from google.api_core import exceptions as gcp_exceptions
    from google.oauth2 import service_account
    GCP_AVAILABLE = True
    
    # Algorithm mappings (only defined if GCP is available)
    ALGORITHM_TO_GCP = {
        'RSA-2048': kms_types.CryptoKeyVersion.CryptoKeyVersionAlgorithm.RSA_SIGN_PKCS1_2048_SHA256,
        'RSA-3072': kms_types.CryptoKeyVersion.CryptoKeyVersionAlgorithm.RSA_SIGN_PKCS1_3072_SHA256,
        'RSA-4096': kms_types.CryptoKeyVersion.CryptoKeyVersionAlgorithm.RSA_SIGN_PKCS1_4096_SHA512,
        'EC-P256': kms_types.CryptoKeyVersion.CryptoKeyVersionAlgorithm.EC_SIGN_P256_SHA256,
        'EC-P384': kms_types.CryptoKeyVersion.CryptoKeyVersionAlgorithm.EC_SIGN_P384_SHA384,
    }
    
    # Purpose mappings
    PURPOSE_TO_GCP = {
        'signing': kms_types.CryptoKey.CryptoKeyPurpose.ASYMMETRIC_SIGN,
        'encryption': kms_types.CryptoKey.CryptoKeyPurpose.ASYMMETRIC_DECRYPT,
    }
    
    # Algorithm names for reverse lookup
    GCP_ALGORITHM_NAMES = {
        kms_types.CryptoKeyVersion.CryptoKeyVersionAlgorithm.RSA_SIGN_PKCS1_2048_SHA256: 'RSA-2048',
        kms_types.CryptoKeyVersion.CryptoKeyVersionAlgorithm.RSA_SIGN_PKCS1_3072_SHA256: 'RSA-3072',
        kms_types.CryptoKeyVersion.CryptoKeyVersionAlgorithm.RSA_SIGN_PKCS1_4096_SHA512: 'RSA-4096',
        kms_types.CryptoKeyVersion.CryptoKeyVersionAlgorithm.EC_SIGN_P256_SHA256: 'EC-P256',
        kms_types.CryptoKeyVersion.CryptoKeyVersionAlgorithm.EC_SIGN_P384_SHA384: 'EC-P384',
        kms_types.CryptoKeyVersion.CryptoKeyVersionAlgorithm.RSA_DECRYPT_OAEP_2048_SHA256: 'RSA-2048',
        kms_types.CryptoKeyVersion.CryptoKeyVersionAlgorithm.RSA_DECRYPT_OAEP_3072_SHA256: 'RSA-3072',
        kms_types.CryptoKeyVersion.CryptoKeyVersionAlgorithm.RSA_DECRYPT_OAEP_4096_SHA512: 'RSA-4096',
    }

    for _label in sorted(UNTESTED_ALGORITHMS):
        _version = getattr(kms_types.CryptoKeyVersion.CryptoKeyVersionAlgorithm,
                           f"PQ_SIGN_{_label.replace('-', '_')}", None)
        if _version is not None:
            ALGORITHM_TO_GCP[_label] = _version
            GCP_ALGORITHM_NAMES[_version] = _label
            ML_DSA_VERSIONS[_version] = _label
except ImportError:
    kms_v1 = None
    kms_types = None
    gcp_exceptions = None


class GcpKmsProvider(BaseHsmProvider):
    """
    Google Cloud KMS HSM Provider
    
    Config:
        project_id: GCP project ID
        location: KMS location (e.g., 'us-east1', 'global')
        key_ring: Key ring name
        service_account_json: Service account JSON (optional, uses default credentials if not provided)
        protection_level: 'HSM' or 'SOFTWARE' (default: 'HSM')
    """
    
    SIGNS_ML_DSA = bool(ML_DSA_VERSIONS)
    ML_DSA_LIBRARY = 'google-cloud-kms 3.11.0'

    def __init__(self, config: Dict[str, Any]):
        if not GCP_AVAILABLE:
            raise HsmConfigError(
                "Google Cloud KMS library not installed. "
                "Install with: pip install google-cloud-kms"
            )
        
        super().__init__(config)
        
        # Validate config
        self.project_id = config.get('project_id')
        self.location = config.get('location', 'global')
        self.key_ring = config.get('key_ring')
        self.service_account_json = config.get('service_account_json')
        self.protection_level = config.get('protection_level', 'HSM')
        
        if not self.project_id:
            raise HsmConfigError("project_id is required")
        if not self.key_ring:
            raise HsmConfigError("key_ring is required")
        
        self._client: Optional[kms_v1.KeyManagementServiceClient] = None
        self._key_ring_path: Optional[str] = None
    
    def connect(self) -> bool:
        """Connect to Google Cloud KMS"""
        try:
            # Create client
            if self.service_account_json:
                # Use provided service account
                import json
                sa_info = json.loads(self.service_account_json)
                credentials = service_account.Credentials.from_service_account_info(sa_info)
                self._client = kms_v1.KeyManagementServiceClient(credentials=credentials)
            else:
                # Use default credentials (ADC)
                self._client = kms_v1.KeyManagementServiceClient()
            
            # Build key ring path
            self._key_ring_path = self._client.key_ring_path(
                self.project_id, self.location, self.key_ring
            )
            
            # Test connection by getting key ring
            self._client.get_key_ring(name=self._key_ring_path)
            
            self._connected = True
            logger.info(f"Connected to GCP KMS key ring: {self._key_ring_path}")
            return True
            
        except gcp_exceptions.NotFound:
            self._connected = False
            raise HsmConnectionError(f"Key ring not found: {self.key_ring}")
        except gcp_exceptions.GoogleAPIError as e:
            self._connected = False
            raise HsmConnectionError(f"GCP KMS connection failed: {str(e)}")
        except Exception as e:
            self._connected = False
            raise HsmConnectionError(f"Connection failed: {str(e)}")
    
    def disconnect(self) -> None:
        """Disconnect from GCP KMS"""
        self._client = None
        self._key_ring_path = None
        self._connected = False
        logger.debug(f"Disconnected from GCP KMS")
    
    def test_connection(self) -> Dict[str, Any]:
        """Test connection to GCP KMS"""
        try:
            self.connect()
            
            # Count keys
            key_count = sum(1 for _ in self._client.list_crypto_keys(parent=self._key_ring_path))
            
            info = {
                'success': True,
                'message': 'Connection successful',
                'details': {
                    'project_id': self.project_id,
                    'location': self.location,
                    'key_ring': self.key_ring,
                    'key_count': key_count,
                    'protection_level': self.protection_level
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
        """List all keys in the key ring"""
        if not self._client:
            raise HsmOperationError("Not connected")
        
        keys = []
        self.list_errors = []  # an unread key is not an absent key (sync_keys)

        try:
            for crypto_key in self._client.list_crypto_keys(parent=self._key_ring_path):
                key_info = self._key_to_key_info(crypto_key)
                if key_info:
                    keys.append(key_info)
            
            return keys
            
        except gcp_exceptions.GoogleAPIError as e:
            raise HsmOperationError(f"Failed to list keys: {str(e)}")
    
    def _key_to_key_info(self, crypto_key) -> Optional[HsmKeyInfo]:
        """Convert GCP CryptoKey to HsmKeyInfo"""
        try:
            # Get primary version for algorithm info
            primary_version = crypto_key.primary
            
            if primary_version:
                version_path = f"{crypto_key.name}/cryptoKeyVersions/{primary_version.name.split('/')[-1]}"
                try:
                    version = self._client.get_crypto_key_version(name=version_path)
                    algorithm = GCP_ALGORITHM_NAMES.get(version.algorithm, str(version.algorithm))
                    protection = version.protection_level.name if hasattr(version, 'protection_level') else 'UNKNOWN'
                except Exception:
                    algorithm = 'UNKNOWN'
                    protection = 'UNKNOWN'
            else:
                algorithm = 'UNKNOWN'
                protection = 'UNKNOWN'
            
            # Determine purpose
            purpose_map = {
                kms_types.CryptoKey.CryptoKeyPurpose.ASYMMETRIC_SIGN: 'signing',
                kms_types.CryptoKey.CryptoKeyPurpose.ASYMMETRIC_DECRYPT: 'encryption',
                kms_types.CryptoKey.CryptoKeyPurpose.ENCRYPT_DECRYPT: 'encryption',
            }
            purpose = purpose_map.get(crypto_key.purpose, 'all')
            
            # Extract key name from path
            key_name = crypto_key.name.split('/')[-1]
            
            return HsmKeyInfo(
                key_identifier=crypto_key.name,
                label=key_name,
                algorithm=algorithm,
                key_type='asymmetric',
                purpose=purpose,
                is_extractable=False,  # GCP KMS keys are never extractable
                metadata={
                    'protection_level': protection,
                    'version_template': str(crypto_key.version_template.algorithm) if crypto_key.version_template else None
                }
            )
            
        except Exception as e:
            logger.warning(f"Failed to parse key: {e}")
            self.list_errors.append(f"{getattr(crypto_key, 'name', '?')}: {e}")
            return None
    
    def generate_key(
        self,
        label: str,
        algorithm: str,
        purpose: str = 'signing',
        extractable: bool = False
    ) -> HsmKeyInfo:
        """Generate a new key in GCP KMS"""
        self.refuse_unsupported_algorithm(algorithm)
        if not self._client:
            raise HsmOperationError("Not connected")
        
        if algorithm not in ALGORITHM_TO_GCP:
            raise HsmOperationError(f"Unsupported algorithm: {algorithm}")
        
        if extractable:
            logger.warning("GCP KMS keys cannot be extractable, ignoring extractable=True")
        
        try:
            # Determine purpose
            if purpose == 'signing':
                gcp_purpose = kms_types.CryptoKey.CryptoKeyPurpose.ASYMMETRIC_SIGN
            elif purpose == 'encryption':
                gcp_purpose = kms_types.CryptoKey.CryptoKeyPurpose.ASYMMETRIC_DECRYPT
            else:
                gcp_purpose = kms_types.CryptoKey.CryptoKeyPurpose.ASYMMETRIC_SIGN
            
            # Determine protection level
            if self.protection_level.upper() == 'HSM':
                protection = kms_types.ProtectionLevel.HSM
            else:
                protection = kms_types.ProtectionLevel.SOFTWARE
            
            # Create key
            crypto_key = kms_types.CryptoKey(
                purpose=gcp_purpose,
                version_template=kms_types.CryptoKeyVersionTemplate(
                    algorithm=ALGORITHM_TO_GCP[algorithm],
                    protection_level=protection
                )
            )
            
            created_key = self._client.create_crypto_key(
                parent=self._key_ring_path,
                crypto_key_id=label,
                crypto_key=crypto_key
            )
            
            # Get public key
            public_key_pem = self._get_primary_public_key(created_key.name)
            
            logger.info(f"Generated key '{label}' ({algorithm}) in GCP KMS")
            
            return HsmKeyInfo(
                key_identifier=created_key.name,
                label=label,
                algorithm=algorithm,
                key_type='asymmetric',
                purpose=purpose,
                public_key_pem=public_key_pem,
                is_extractable=False,
                metadata={'protection_level': protection.name}
            )
            
        except gcp_exceptions.AlreadyExists:
            raise HsmKeyExistsError(f"Key already exists: {label}")
        except gcp_exceptions.GoogleAPIError as e:
            raise HsmOperationError(f"Failed to generate key: {str(e)}")
    
    def _get_primary_public_key(self, crypto_key_name: str) -> Optional[str]:
        """Get public key PEM for the primary version"""
        try:
            # Get primary version
            crypto_key = self._client.get_crypto_key(name=crypto_key_name)
            if not crypto_key.primary:
                return None
            
            version_name = f"{crypto_key_name}/cryptoKeyVersions/{crypto_key.primary.name.split('/')[-1]}"

            label = ML_DSA_VERSIONS.get(getattr(crypto_key.primary, 'algorithm', None))
            if label is None:
                return self._client.get_public_key(name=version_name).pem
            # KMS serves no PEM for a post-quantum version: the raw FIPS 204 key, as SPKI here
            public_key = self._client.get_public_key(request={
                'name': version_name,
                'public_key_format': kms_types.PublicKey.PublicKeyFormat.NIST_PQC})
            registered = key_algorithms.get(label)
            if registered is None:
                raise HsmOperationError(f'{label} keys are not available on this build')
            from cryptography.hazmat.primitives import serialization
            return registered.public_class.from_public_bytes(bytes(public_key.public_key.data)).public_bytes(
                serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo).decode()
            
        except Exception as e:
            logger.warning(f"Failed to get public key: {e}")
            return None
    
    def delete_key(self, key_identifier: str) -> bool:
        """Delete a key from GCP KMS (destroys all versions)"""
        if not self._client:
            raise HsmOperationError("Not connected")
        
        try:
            # List and destroy all versions
            versions = self._client.list_crypto_key_versions(parent=key_identifier)
            
            for version in versions:
                if version.state != kms_types.CryptoKeyVersion.CryptoKeyVersionState.DESTROYED:
                    self._client.destroy_crypto_key_version(name=version.name)
            
            logger.info(f"Destroyed all versions of key: {key_identifier}")
            return True
            
        except gcp_exceptions.NotFound:
            raise HsmKeyNotFoundError(f"Key not found: {key_identifier}")
        except gcp_exceptions.GoogleAPIError as e:
            raise HsmOperationError(f"Failed to delete key: {str(e)}")
    
    def get_public_key(self, key_identifier: str) -> str:
        """Get public key in PEM format"""
        if not self._client:
            raise HsmOperationError("Not connected")
        
        try:
            pem = self._get_primary_public_key(key_identifier)
            if not pem:
                raise HsmOperationError("Failed to get public key or no primary version")
            return pem
            
        except gcp_exceptions.NotFound:
            raise HsmKeyNotFoundError(f"Key not found: {key_identifier}")
        except gcp_exceptions.GoogleAPIError as e:
            raise HsmOperationError(f"Failed to get public key: {str(e)}")
    
    @staticmethod
    def _digest_of_version(version) -> Optional[str]:
        """The digest a KMS key version signs with, from its algorithm name
        (RSA_SIGN_PKCS1_3072_SHA256 signs with SHA-256, not SHA-384); None
        for ML-DSA, which signs the data itself. A name with neither is refused."""
        algorithm = getattr(version, 'algorithm', None)
        if algorithm in ML_DSA_VERSIONS:
            return None
        name = getattr(algorithm, 'name', '') or str(algorithm or '')
        for digest in ('sha512', 'sha384', 'sha256'):
            if digest.upper() in name.upper():
                return digest
        raise HsmOperationError(f"KMS key version {name or '?'} names no digest UCM signs with")

    def hash_for_key(self, key_identifier, key_algorithm, requested='sha256'):
        """KMS binds the digest to the key version: the signature must name
        that digest whatever was requested."""
        if not self._client:
            self.connect()
        crypto_key = self._client.get_crypto_key(name=key_identifier)
        if not crypto_key.primary:
            raise HsmOperationError("Key has no primary version")
        version_name = f"{key_identifier}/cryptoKeyVersions/{crypto_key.primary.name.split('/')[-1]}"
        return self._digest_of_version(self._client.get_crypto_key_version(name=version_name)) or requested

    def sign(
        self,
        key_identifier: str,
        data: bytes,
        algorithm: Optional[str] = None,
        hash_algorithm: Optional[str] = None
    ) -> bytes:
        """Sign data using GCP KMS key"""
        if not self._client:
            raise HsmOperationError("Not connected")
        
        try:
            # Get primary version
            crypto_key = self._client.get_crypto_key(name=key_identifier)
            if not crypto_key.primary:
                raise HsmOperationError("Key has no primary version")
            
            version_name = f"{key_identifier}/cryptoKeyVersions/{crypto_key.primary.name.split('/')[-1]}"
            
            # Get version to determine algorithm
            version = self._client.get_crypto_key_version(name=version_name)
            digest_name = self._digest_of_version(version)
            if digest_name is None:
                # ML-DSA: KMS signs the data itself, pure with an empty context
                if hash_algorithm:
                    raise HsmOperationError("ML-DSA signs the data itself: no digest applies")
                if len(data) > KMS_SIGN_DATA_MAX:
                    raise HsmOperationError(
                        f"Google Cloud KMS signs at most 64 KiB with ML-DSA, which signs the data "
                        f"itself; this request carries {len(data)} bytes (a CRL this large needs "
                        f"another provider)")
                response = self._client.asymmetric_sign(name=version_name, data=data)
            else:
                # Hash the data with the digest the key version is bound to
                import hashlib
                digest = {digest_name: hashlib.new(digest_name, data).digest()}
                response = self._client.asymmetric_sign(
                    name=version_name,
                    digest=digest
                )
            
            logger.debug(f"Signed {len(data)} bytes with key {key_identifier}")
            return response.signature
            
        except gcp_exceptions.NotFound:
            raise HsmKeyNotFoundError(f"Key not found: {key_identifier}")
        except gcp_exceptions.GoogleAPIError as e:
            raise HsmOperationError(f"Signing failed: {str(e)}")


def is_available() -> bool:
    """Check if GCP KMS provider is available"""
    return GCP_AVAILABLE
