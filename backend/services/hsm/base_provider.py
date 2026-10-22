"""
Base HSM Provider - Abstract interface for all HSM providers
All provider implementations must inherit from this class.
"""

from abc import ABC, abstractmethod
from typing import Dict, List, Optional, Any
from dataclasses import dataclass


@dataclass
class HsmKeyInfo:
    """Information about a key stored in HSM"""
    key_identifier: str
    label: str
    algorithm: str
    key_type: str  # asymmetric, symmetric
    purpose: str   # signing, encryption, wrapping, all
    public_key_pem: Optional[str] = None
    is_extractable: bool = False
    metadata: Optional[Dict[str, Any]] = None


class BaseHsmProvider(ABC):
    """
    Abstract base class for HSM providers.
    Implementations: PKCS11Provider, AzureKeyVaultProvider, GcpKmsProvider
    """

    # True when sign() honours padding='pss' (RSASSA-PSS, salt = digest length)
    SIGNS_PSS = False

    # True when the provider generates and signs with Brainpool curves (RFC 5639)
    SIGNS_BRAINPOOL = False

    def refuse_unsupported_curve(self, algorithm: str) -> None:
        """Raise HsmOperationError for a Brainpool label this provider cannot handle."""
        message = brainpool_refusal(type(self).__name__, algorithm, self.SIGNS_BRAINPOOL)
        if message:
            raise HsmOperationError(message)
    
    def __init__(self, config: Dict[str, Any]):
        """
        Initialize provider with configuration.
        
        Args:
            config: Provider-specific configuration dict
        """
        self.config = config
        self._connected = False
    
    @property
    def is_connected(self) -> bool:
        """Check if provider is connected"""
        return self._connected
    
    @abstractmethod
    def connect(self) -> bool:
        """
        Establish connection to HSM.
        
        Returns:
            True if connection successful
            
        Raises:
            HsmConnectionError: If connection fails
        """
        pass
    
    @abstractmethod
    def disconnect(self) -> None:
        """Close connection to HSM"""
        pass
    
    @abstractmethod
    def test_connection(self) -> Dict[str, Any]:
        """
        Test HSM connection and return status info.
        
        Returns:
            Dict with 'success', 'message', and optional 'details'
        """
        pass
    
    @abstractmethod
    def list_keys(self) -> List[HsmKeyInfo]:
        """
        List all keys in the HSM/token.
        
        Returns:
            List of HsmKeyInfo objects
        """
        pass
    
    @abstractmethod
    def generate_key(
        self,
        label: str,
        algorithm: str,
        purpose: str = 'signing',
        extractable: bool = False
    ) -> HsmKeyInfo:
        """
        Generate a new key in the HSM.
        
        Args:
            label: Human-readable key label
            algorithm: Key algorithm (RSA-2048, EC-P256, etc.)
            purpose: Key purpose (signing, encryption, wrapping, all)
            extractable: Whether key can be exported (default: False for security)
            
        Returns:
            HsmKeyInfo for the generated key
            
        Raises:
            HsmOperationError: If key generation fails
        """
        pass
    
    @abstractmethod
    def delete_key(self, key_identifier: str) -> bool:
        """
        Delete a key from the HSM.
        
        Args:
            key_identifier: HSM-internal key identifier
            
        Returns:
            True if deletion successful
            
        Raises:
            HsmOperationError: If deletion fails
        """
        pass
    
    @abstractmethod
    def get_public_key(self, key_identifier: str) -> str:
        """
        Get public key in PEM format (for asymmetric keys).
        
        Args:
            key_identifier: HSM-internal key identifier
            
        Returns:
            Public key in PEM format
            
        Raises:
            HsmOperationError: If key not found or not asymmetric
        """
        pass
    
    def hash_for_key(self, key_identifier: str, key_algorithm: Optional[str],
                     requested: str = 'sha256') -> str:
        """The digest this provider signs with for the key when *requested*
        is asked for. A provider that hashes with any digest returns the
        request; one that binds the digest to the key overrides this."""
        return requested

    @abstractmethod
    def sign(
        self,
        key_identifier: str,
        data: bytes,
        algorithm: Optional[str] = None,
        hash_algorithm: Optional[str] = None,
        padding: Optional[str] = None
    ) -> bytes:
        """
        Sign data using HSM key.
        
        Args:
            key_identifier: HSM-internal key identifier
            data: Data to sign (or hash of data)
            algorithm: Key algorithm (RSA-2048, EC-P384, ...)
            hash_algorithm: Digest to sign with ('sha256', 'sha384', 'sha512');
                it is what the signature's AlgorithmIdentifier will name, so
                a provider that can hash with it must
            padding: 'pss' for RSASSA-PSS with a salt as long as the digest
                (only passed to providers with SIGNS_PSS), else PKCS#1 v1.5
            
        Returns:
            Signature bytes
            
        Raises:
            HsmOperationError: If signing fails
        """
        pass
    
    def __enter__(self):
        """Context manager entry"""
        self.connect()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit"""
        self.disconnect()
        return False


class HsmError(Exception):
    """Base exception for HSM operations"""
    pass


class HsmConnectionError(HsmError):
    """HSM connection failed"""
    pass


BRAINPOOL_ALGORITHMS = ('EC-BP256', 'EC-BP384', 'EC-BP512')


def brainpool_refusal(provider: str, algorithm: Optional[str], supported: bool = False) -> Optional[str]:
    """Why *provider* cannot take the Brainpool *algorithm*, or None."""
    if supported or algorithm not in BRAINPOOL_ALGORITHMS:
        return None
    return (f"Brainpool key {algorithm} is not supported by {provider}: "
            f"only PKCS#11 HSMs generate and sign with Brainpool curves")


class HsmOperationError(HsmError):
    """HSM operation failed"""
    pass


class HsmKeyNotFoundError(HsmError):
    """HSM key not found"""
    pass


class HsmConfigError(HsmError):
    """HSM configuration invalid"""
    pass
