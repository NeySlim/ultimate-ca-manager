"""Zones for which the DNS UPDATE listener is authoritative (plan 2.3, U3)."""

import logging
import threading
import time
from typing import Optional

import dns.exception
import dns.name

logger = logging.getLogger(__name__)

_RETRY_S = 2.0


class ZoneIndex:
    def __init__(self, max_age_s: float = 10.0, clock=time.monotonic):
        self._max_age = max_age_s
        self._clock = clock
        self._lock = threading.Lock()
        self._zones: frozenset = frozenset()
        self._ancestors: frozenset = frozenset()
        self._loaded_at: Optional[float] = None
        self._retry_at: Optional[float] = None

    def invalidate(self) -> None:
        with self._lock:
            self._loaded_at = None
            self._retry_at = None

    def _ensure(self) -> None:
        with self._lock:
            now = self._clock()
            if self._loaded_at is not None and (now - self._loaded_at) < self._max_age:
                return
            if self._retry_at is not None and now < self._retry_at:
                return
            try:
                zones = self._load()
            except Exception as e:
                # Keep the previous zones (availability), retry after _RETRY_S.
                self._retry_at = now + _RETRY_S
                logger.warning("DNS UPDATE zone reload failed, keeping previous cache: %s",
                               type(e).__name__)
                return
            self._retry_at = None
            ancestors = set()
            for zone in zones:
                parent = zone
                while len(parent.labels) > 3:  # stop before a TLD and the root
                    parent = parent.parent()
                    ancestors.add(parent)
            self._zones = zones
            self._ancestors = frozenset(ancestors)
            self._loaded_at = now

    @staticmethod
    def _load() -> frozenset:
        from models import db
        from models.acme_models import AcmeDomain
        from services.acme import domain_match

        zones = set()
        try:
            for (stored,) in db.session.query(AcmeDomain.domain).all():
                bare = domain_match.normalize(stored)
                if not bare:
                    continue
                try:
                    zone = dns.name.from_text(bare + '.')
                except (dns.exception.DNSException, UnicodeError):
                    continue
                if len(zone.labels) < 3:  # a single-label entry is a TLD
                    continue
                zones.add(zone)
        finally:
            db.session.rollback()
        return frozenset(zones)

    def zones(self) -> frozenset:
        self._ensure()
        with self._lock:
            return self._zones

    def is_authoritative(self, zname: dns.name.Name) -> bool:
        """A zone of ours, or a proper ancestor of one that is no TLD."""
        # labels include the trailing empty root label: 'net.' has 2 labels.
        if not zname.is_absolute() or len(zname.labels) < 3:
            return False
        zname = zname.canonicalize()
        self._ensure()
        with self._lock:
            return zname in self._zones or zname in self._ancestors


zone_index = ZoneIndex()
