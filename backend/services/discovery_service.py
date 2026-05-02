"""Backward-compatible shim — DiscoveryService now lives in services/discovery/."""
from services.discovery import DiscoveryService

__all__ = ['DiscoveryService']
