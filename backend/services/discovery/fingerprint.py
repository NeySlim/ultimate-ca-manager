"""
Fingerprint cache mixin — builds and caches a SHA-256 → cert_id index.
"""
import base64
import hashlib
import logging
import time
from typing import Dict

from cryptography import x509
from cryptography.hazmat.primitives import serialization

from models import Certificate

logger = logging.getLogger(__name__)

# Module-level fingerprint cache
_fingerprint_cache: Dict[str, int] = {}
_cache_built_at = None
_CACHE_TTL_SECONDS = 300  # 5 min


class FingerprintMixin:

    def _build_fingerprint_index(self) -> Dict[str, int]:
        """Build { sha256_hex: cert_id } from UCM certificate inventory."""
        global _fingerprint_cache, _cache_built_at

        now = time.time()
        if _cache_built_at and (now - _cache_built_at) < _CACHE_TTL_SECONDS:
            return _fingerprint_cache

        logger.debug("Building certificate fingerprint index...")
        index = {}
        certs = Certificate.query.filter(
            Certificate.crt.isnot(None)
        ).with_entities(Certificate.id, Certificate.crt).all()

        for cert_id, crt_b64 in certs:
            try:
                pem_data = base64.b64decode(crt_b64).decode('utf-8')
                cert_obj = x509.load_pem_x509_certificate(pem_data.encode())
                der = cert_obj.public_bytes(serialization.Encoding.DER)
                fp = hashlib.sha256(der).hexdigest().upper()
                index[fp] = cert_id
            except Exception:
                continue

        _fingerprint_cache = index
        _cache_built_at = now
        logger.debug(f"Fingerprint index built: {len(index)} certificates")
        return index

    @staticmethod
    def invalidate_fingerprint_cache():
        """Call when UCM certs change (issue, import, delete)."""
        global _cache_built_at
        _cache_built_at = None
