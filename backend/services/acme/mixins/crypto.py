"""Cryptographic utility mixin for ACME service"""
import logging
from typing import Dict, Any

from services.acme.jwk_thumbprint import jwk_thumbprint

logger = logging.getLogger(__name__)


class CryptoMixin:
    def _compute_jwk_thumbprint(self, jwk: Dict[str, Any]) -> str:
        """Compute JWK thumbprint per RFC 7638

        Args:
            jwk: JSON Web Key

        Returns:
            Base64url-encoded SHA-256 thumbprint

        Raises:
            ValueError: unsupported key type, or a required member missing.
            Callers that catch it report a malformed key; the proxy wants a
            None instead and calls jwk_thumbprint_or_none for that.
        """
        return jwk_thumbprint(jwk)


    def _compute_key_authorization(self, token: str, jwk_thumbprint: str) -> str:
        """Compute key authorization for challenges
        
        Args:
            token: Challenge token
            jwk_thumbprint: JWK thumbprint
            
        Returns:
            Key authorization string (token.thumbprint)
        """
        return f"{token}.{jwk_thumbprint}"

    def _acme_allow_private_ips(self) -> bool:
        """Whether HTTP-01 / TLS-ALPN-01 may target private/internal IPs.

        Local ACME is typically used to issue certificates for INTERNAL
        infrastructure (.lan, .local, .corp, etc.) which by definition
        resolves to RFC 1918 / link-local addresses. Blocking those would
        make the local ACME server unusable for its main use case.

        Defaults to True. Operators who only want to issue for public
        domains can flip ``acme.allow_private_ips`` to ``false``.
        """
        try:
            from models import SystemConfig
            setting = SystemConfig.query.filter_by(key='acme.allow_private_ips').first()
            if setting is None:
                return True
            return str(setting.value).strip().lower() in ('1', 'true', 'yes', 'on')
        except Exception:
            return True
    
    def _acme_dns01_resolver(self):
        """Resolver for DNS-01 validation per ``acme.dns01_resolver_mode``, or None for the system one."""
        from utils.dns_txt_lookup import configured_resolver
        return configured_resolver()
