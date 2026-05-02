"""
Trust Store Service - Backward Compatibility Wrapper

This file maintains backward compatibility by importing from the new package structure.
All functionality has been moved to services/trust_store/ package.
"""

from services.trust_store import TrustStoreService

__all__ = ['TrustStoreService']
