"""
Discovery service package — certificate network discovery with async scanning
and fingerprint matching.
"""
from .tls_probe import TLSProbeMixin
from .fingerprint import FingerprintMixin
from .notifications import NotificationsMixin
from .scanner import ScannerMixin
from .query import QueryMixin
from .profiles import ProfilesMixin


class DiscoveryService(
    TLSProbeMixin,
    ScannerMixin,
    FingerprintMixin,
    NotificationsMixin,
    QueryMixin,
    ProfilesMixin,
):
    """Certificate network discovery with async scanning and fingerprint matching."""

    def __init__(self, max_workers: int = 20, timeout: int = 5):
        self.max_workers = max_workers
        self.timeout = timeout


__all__ = ['DiscoveryService']
