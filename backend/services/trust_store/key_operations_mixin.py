"""
Key operations mixin for TrustStoreService
"""
from cryptography.hazmat.primitives.asymmetric import rsa, ec
from cryptography.hazmat.backends import default_backend

from .constants import KEY_TYPES


class KeyOperationsMixin:
    """Private key generation operations"""
    
    @staticmethod
    def generate_private_key(key_type: str):
        """Generate a private key."""
        if key_type not in KEY_TYPES:
            raise ValueError(f"Unsupported key type: {key_type}")
        
        algo, param = KEY_TYPES[key_type]
        
        if algo == 'rsa':
            return rsa.generate_private_key(
                public_exponent=65537,
                key_size=param,
                backend=default_backend()
            )
        elif algo == 'ec':
            return ec.generate_private_key(param, default_backend())
        
        raise ValueError(f"Unknown algorithm: {algo}")
