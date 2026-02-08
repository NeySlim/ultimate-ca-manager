"""
Base DNS Provider - Abstract class for all DNS providers
Extensible architecture for adding new providers easily
"""
from abc import ABC, abstractmethod
from typing import Tuple, List, Dict, Any, Optional
import logging

logger = logging.getLogger(__name__)


class BaseDnsProvider(ABC):
    """
    Abstract base class for DNS providers.
    
    To add a new provider:
    1. Create a new file in dns_providers/ (e.g., newprovider.py)
    2. Inherit from BaseDnsProvider
    3. Set PROVIDER_TYPE, PROVIDER_NAME, REQUIRED_CREDENTIALS
    4. Implement abstract methods
    5. Register in __init__.py PROVIDER_REGISTRY
    """
    
    # Override in subclass
    PROVIDER_TYPE: str = "base"
    PROVIDER_NAME: str = "Base Provider"
    PROVIDER_DESCRIPTION: str = "Base DNS provider class"
    REQUIRED_CREDENTIALS: List[str] = []
    OPTIONAL_CREDENTIALS: List[str] = []
    
    def __init__(self, credentials: Dict[str, Any]):
        """
        Initialize provider with credentials.
        
        Args:
            credentials: Dict with API keys and secrets
        """
        self.credentials = credentials or {}
        self._validate_credentials()
    
    def _validate_credentials(self) -> None:
        """Validate that all required credentials are present"""
        missing = []
        for key in self.REQUIRED_CREDENTIALS:
            if not self.credentials.get(key):
                missing.append(key)
        
        if missing:
            raise ValueError(f"Missing required credentials: {', '.join(missing)}")
    
    @abstractmethod
    def create_txt_record(
        self, 
        domain: str, 
        record_name: str, 
        record_value: str, 
        ttl: int = 300
    ) -> Tuple[bool, str]:
        """
        Create a TXT record for ACME DNS-01 challenge.
        
        Args:
            domain: The base domain (e.g., 'example.com')
            record_name: Full record name (e.g., '_acme-challenge.example.com')
            record_value: The challenge value to set
            ttl: Time to live in seconds (default 300)
        
        Returns:
            Tuple of (success: bool, message: str)
        """
        pass
    
    @abstractmethod
    def delete_txt_record(
        self, 
        domain: str, 
        record_name: str
    ) -> Tuple[bool, str]:
        """
        Delete a TXT record after ACME validation.
        
        Args:
            domain: The base domain
            record_name: Full record name to delete
        
        Returns:
            Tuple of (success: bool, message: str)
        """
        pass
    
    @abstractmethod
    def test_connection(self) -> Tuple[bool, str]:
        """
        Test API connection and credentials.
        
        Returns:
            Tuple of (success: bool, message: str)
        """
        pass
    
    def get_zone_for_domain(self, domain: str) -> Optional[str]:
        """
        Find the appropriate zone for a domain.
        Override if provider needs special zone detection.
        
        Args:
            domain: The domain to find zone for
        
        Returns:
            Zone name or None if not found
        """
        # Default: return the domain itself or parent domain
        parts = domain.split('.')
        if len(parts) >= 2:
            return '.'.join(parts[-2:])
        return domain
    
    def get_acme_challenge_name(self, domain: str) -> str:
        """
        Get the full record name for ACME challenge.
        
        Args:
            domain: The domain being validated
        
        Returns:
            Full record name (e.g., '_acme-challenge.example.com')
        """
        # Remove wildcard prefix if present
        if domain.startswith('*.'):
            domain = domain[2:]
        return f"_acme-challenge.{domain}"
    
    def get_relative_record_name(self, record_name: str, zone: str) -> str:
        """
        Get record name relative to zone.
        Some APIs want just '_acme-challenge', others want the full name.
        
        Args:
            record_name: Full record name
            zone: Zone name
        
        Returns:
            Relative record name
        """
        if record_name.endswith(f".{zone}"):
            return record_name[:-len(f".{zone}")]
        return record_name
    
    @classmethod
    def get_credential_schema(cls) -> List[Dict[str, Any]]:
        """
        Get schema for required and optional credentials.
        Override for custom field types (password, select, etc.)
        
        Returns:
            List of credential field definitions
        """
        schema = []
        for key in cls.REQUIRED_CREDENTIALS:
            schema.append({
                'name': key,
                'label': key.replace('_', ' ').title(),
                'type': 'password' if 'secret' in key.lower() or 'key' in key.lower() else 'text',
                'required': True,
            })
        for key in cls.OPTIONAL_CREDENTIALS:
            schema.append({
                'name': key,
                'label': key.replace('_', ' ').title(),
                'type': 'text',
                'required': False,
            })
        return schema
    
    @classmethod
    def to_dict(cls) -> Dict[str, Any]:
        """
        Get provider info for API responses.
        
        Returns:
            Provider type information
        """
        return {
            'type': cls.PROVIDER_TYPE,
            'name': cls.PROVIDER_NAME,
            'description': cls.PROVIDER_DESCRIPTION,
            'credentials_schema': cls.get_credential_schema(),
        }
