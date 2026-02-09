"""
DNS Providers Package
Registry and factory for DNS provider implementations.

To add a new provider:
1. Create a new file (e.g., newprovider.py)
2. Inherit from BaseDnsProvider
3. Implement required methods
4. Add to PROVIDER_REGISTRY below
"""
from typing import Dict, Type, Optional, List, Any
import logging

from .base import BaseDnsProvider
from .manual import ManualDnsProvider
from .ovh import OvhDnsProvider
from .cloudflare import CloudflareDnsProvider
from .hetzner import HetznerDnsProvider
from .gandi import GandiDnsProvider
from .digitalocean import DigitalOceanDnsProvider
from .infomaniak import InfomaniakDnsProvider
from .route53 import Route53DnsProvider
from .scaleway import ScalewayDnsProvider
from .ionos import IonosDnsProvider
from .desec import DesecDnsProvider
from .linode import LinodeDnsProvider
from .bookmyname import BookMyNameDnsProvider
from .vultr import VultrDnsProvider
from .godaddy import GoDaddyDnsProvider
from .namecheap import NamecheapDnsProvider
from .netcup import NetcupDnsProvider
from .inwx import InwxDnsProvider

logger = logging.getLogger(__name__)

# =============================================================================
# Provider Registry
# Add new providers here after implementing them
# =============================================================================

PROVIDER_REGISTRY: Dict[str, Type[BaseDnsProvider]] = {
    'manual': ManualDnsProvider,
    # European providers (priority)
    'ovh': OvhDnsProvider,
    'hetzner': HetznerDnsProvider,
    'gandi': GandiDnsProvider,
    'infomaniak': InfomaniakDnsProvider,
    'scaleway': ScalewayDnsProvider,
    'ionos': IonosDnsProvider,
    'netcup': NetcupDnsProvider,
    'inwx': InwxDnsProvider,
    'bookmyname': BookMyNameDnsProvider,
    # International providers
    'cloudflare': CloudflareDnsProvider,
    'digitalocean': DigitalOceanDnsProvider,
    'route53': Route53DnsProvider,
    'linode': LinodeDnsProvider,
    'vultr': VultrDnsProvider,
    'godaddy': GoDaddyDnsProvider,
    'namecheap': NamecheapDnsProvider,
    'desec': DesecDnsProvider,
}


def get_provider_class(provider_type: str) -> Optional[Type[BaseDnsProvider]]:
    """
    Get provider class by type.
    
    Args:
        provider_type: Provider type identifier (e.g., 'cloudflare')
    
    Returns:
        Provider class or None if not found
    """
    return PROVIDER_REGISTRY.get(provider_type)


def create_provider(provider_type: str, credentials: Dict[str, Any]) -> BaseDnsProvider:
    """
    Factory function to create a provider instance.
    
    Args:
        provider_type: Provider type identifier
        credentials: API credentials dict
    
    Returns:
        Provider instance
    
    Raises:
        ValueError: If provider type is unknown
    """
    provider_class = get_provider_class(provider_type)
    if not provider_class:
        available = ', '.join(PROVIDER_REGISTRY.keys())
        raise ValueError(f"Unknown DNS provider type: {provider_type}. Available: {available}")
    
    return provider_class(credentials)


def get_available_providers() -> List[Dict[str, Any]]:
    """
    Get list of all available provider types with their info.
    
    Returns:
        List of provider info dicts
    """
    providers = []
    for provider_type, provider_class in PROVIDER_REGISTRY.items():
        providers.append(provider_class.to_dict())
    return providers


def get_provider_types() -> List[str]:
    """
    Get list of available provider type identifiers.
    
    Returns:
        List of provider type strings
    """
    return list(PROVIDER_REGISTRY.keys())


def is_valid_provider_type(provider_type: str) -> bool:
    """
    Check if a provider type is valid/registered.
    
    Args:
        provider_type: Provider type to check
    
    Returns:
        True if valid, False otherwise
    """
    return provider_type in PROVIDER_REGISTRY


# =============================================================================
# Helper to register providers dynamically (for plugins/extensions)
# =============================================================================

def register_provider(provider_type: str, provider_class: Type[BaseDnsProvider]) -> None:
    """
    Register a new provider type.
    
    Args:
        provider_type: Type identifier
        provider_class: Provider class (must inherit BaseDnsProvider)
    """
    if not issubclass(provider_class, BaseDnsProvider):
        raise TypeError(f"Provider class must inherit from BaseDnsProvider")
    
    PROVIDER_REGISTRY[provider_type] = provider_class
    logger.info(f"Registered DNS provider: {provider_type}")


def unregister_provider(provider_type: str) -> bool:
    """
    Unregister a provider type.
    
    Args:
        provider_type: Type to unregister
    
    Returns:
        True if removed, False if not found
    """
    if provider_type in PROVIDER_REGISTRY:
        del PROVIDER_REGISTRY[provider_type]
        logger.info(f"Unregistered DNS provider: {provider_type}")
        return True
    return False


# Export public API
__all__ = [
    'BaseDnsProvider',
    'ManualDnsProvider',
    'PROVIDER_REGISTRY',
    'get_provider_class',
    'create_provider',
    'get_available_providers',
    'get_provider_types',
    'is_valid_provider_type',
    'register_provider',
    'unregister_provider',
]
