"""
Key operations mixin for TrustStoreService
"""
from utils import key_algorithms

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
            return key_algorithms.generate_rsa(param)
        elif algo == 'ec':
            return key_algorithms.generate_ec(param)
        elif algo == 'registry':
            return key_algorithms.generate(param)

        raise ValueError(f"Unknown algorithm: {algo}")
