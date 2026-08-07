"""Cryptographic utility mixin for ACME service"""
import json
import hashlib
import base64
import logging
from typing import Dict, Any

logger = logging.getLogger(__name__)


class CryptoMixin:
    def _compute_jwk_thumbprint(self, jwk: Dict[str, Any]) -> str:
        """Compute JWK thumbprint per RFC 7638
        
        Args:
            jwk: JSON Web Key
            
        Returns:
            Base64url-encoded SHA-256 thumbprint
        """
        # Extract required fields in lexicographic order
        if jwk.get("kty") == "RSA":
            thumbprint_input = {
                "e": jwk["e"],
                "kty": jwk["kty"],
                "n": jwk["n"]
            }
        elif jwk.get("kty") == "EC":
            thumbprint_input = {
                "crv": jwk["crv"],
                "kty": jwk["kty"],
                "x": jwk["x"],
                "y": jwk["y"]
            }
        else:
            raise ValueError(f"Unsupported key type: {jwk.get('kty')}")
        
        # Serialize to JSON (no whitespace)
        json_str = json.dumps(thumbprint_input, sort_keys=True, separators=(',', ':'))
        
        # Compute SHA-256
        digest = hashlib.sha256(json_str.encode()).digest()
        
        # Base64url encode
        return base64.urlsafe_b64encode(digest).decode().rstrip('=')
    
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
    
    def _acme_dns01_nameservers(self) -> list:
        """Optional list of DNS servers to use for DNS-01 challenge validation.

        When set (SystemConfig key ``acme.dns01_nameservers``, comma-separated
        IPs, optionally ``host:port``), DNS-01 validation queries those
        resolvers instead of the system resolver. Useful when the
        authoritative DNS for the validation zone (e.g. a local BIND9 driven
        by cert-manager rfc2136) is not reachable via the OS
        /etc/resolv.conf chain.

        Returns an empty list when unset.
        """
        try:
            from models import SystemConfig
            setting = SystemConfig.query.filter_by(key='acme.dns01_nameservers').first()
            if not setting or not setting.value:
                return []
            return [ip.strip() for ip in str(setting.value).split(',') if ip.strip()]
        except Exception:
            return []

    def _acme_dns01_resolver(self):
        """dns.resolver.Resolver honoring ``acme.dns01_nameservers``, or None.

        Supports 'host:port' entries; the port of the first entry carrying
        one wins (dnspython resolvers expose a single shared port).
        """
        custom_ns = [e for e in self._acme_dns01_nameservers() if e]
        if not custom_ns:
            return None
        import dns.resolver
        resolver = dns.resolver.Resolver(configure=False)
        hosts, port = [], None
        for entry in custom_ns:
            if ':' in entry and entry.count(':') == 1:  # ipv4:port
                host, _, p = entry.rpartition(':')
                hosts.append(host)
                if port is None:
                    try:
                        port = int(p)
                    except ValueError:
                        port = 53
            else:
                hosts.append(entry)
        resolver.nameservers = hosts
        if port:
            resolver.port = port
        resolver.timeout = 5
        resolver.lifetime = 10
        return resolver
