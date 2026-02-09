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
    
    @abstractmethod
    def sign(
        self,
        key_identifier: str,
        data: bytes,
        algorithm: Optional[str] = None
    ) -> bytes:
        """
        Sign data using HSM key.
        
        Args:
            key_identifier: HSM-internal key identifier
            data: Data to sign (or hash of data)
            algorithm: Signature algorithm (SHA256withRSA, SHA384withECDSA, etc.)
            
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


class HsmOperationError(HsmError):
    """HSM operation failed"""
    pass


class HsmKeyNotFoundError(HsmError):
    """HSM key not found"""
    pass


class HsmConfigError(HsmError):
    """HSM configuration invalid"""
    pass
