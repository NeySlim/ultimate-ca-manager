"""
Base DNS Provider - Abstract class for all DNS providers
Extensible architecture for adding new providers easily
"""
from abc import ABC, abstractmethod
from typing import Tuple, List, Dict, Any, Optional
import logging

logger = logging.getLogger(__name__)


class BaseDnsProvider(ABC):
    """
    Abstract base class for DNS providers.
    
    To add a new provider:
    1. Create a new file in dns_providers/ (e.g., newprovider.py)
    2. Inherit from BaseDnsProvider
    3. Set PROVIDER_TYPE, PROVIDER_NAME, REQUIRED_CREDENTIALS
    4. Implement abstract methods
    5. Register in __init__.py PROVIDER_REGISTRY
    """
    
    # Override in subclass
    PROVIDER_TYPE: str = "base"
    PROVIDER_NAME: str = "Base Provider"
    PROVIDER_DESCRIPTION: str = "Base DNS provider class"
    REQUIRED_CREDENTIALS: List[str] = []
    OPTIONAL_CREDENTIALS: List[str] = []

    # How much of a failing response body an error message may quote. The body
    # is attacker-influenced text on its way to a log line and to the browser.
    MAX_ERROR_BODY_CHARS: int = 500

    def __init__(self, credentials: Dict[str, Any]):
        """
        Initialize provider with credentials.
        
        Args:
            credentials: Dict with API keys and secrets
        """
        self.credentials = credentials or {}
        self._transient_secrets: List[str] = []
        self._validate_credentials()

    def _validate_credentials(self) -> None:
        """Validate that all required credentials are present"""
        missing = []
        for key in self.REQUIRED_CREDENTIALS:
            if not self.credentials.get(key):
                missing.append(key)

        if missing:
            raise ValueError(f"Missing required credentials: {', '.join(missing)}")

    def remember_secret(self, value: Optional[str]) -> Optional[str]:
        """Register a secret obtained at run time so it is redacted too.

        A provider that trades its credentials for a bearer token holds a
        secret that is not in ``self.credentials``, so redaction could not see
        it — and the token is what the next request puts in its Authorization
        header, which is what a connection error quotes back. Returns *value*
        so it can be used inline: ``self._token = self.remember_secret(...)``.
        """
        if isinstance(value, str) and len(value) >= 6:
            self._transient_secrets.append(value)
        return value

    def redact_secrets(self, message) -> str:
        """Replace credential values in *message* with '***'.

        Providers that send secrets as URL query parameters must pass any
        requests exception text through this before logging or returning it —
        ConnectionError/Timeout messages embed the full URL.
        """
        msg = str(message)
        values = list(self.credentials.values())
        values.extend(getattr(self, '_transient_secrets', ()))
        for value in values:
            if isinstance(value, str) and len(value) >= 6 and value in msg:
                msg = msg.replace(value, '***')
        return msg

    def _error(self, resp, prefix: str = '') -> str:
        """The message for an HTTP response the provider treats as a failure.

        Says what the server answered — status and reason — and quotes a bound
        slice of the body, redacted. Returning ``resp.text`` whole was the
        habit: unbounded, and an API that echoes the request it refused (or a
        token endpoint that quotes the assertion) hands the secret straight
        back to the browser through the provider-test route.
        """
        status = getattr(resp, 'status_code', '?')
        reason = (getattr(resp, 'reason', '') or '').strip()
        head = f"{prefix}HTTP {status}" + (f" {reason}" if reason else '')

        body = (getattr(resp, 'text', '') or '').strip()
        if not body:
            return head
        body = self.redact_secrets(body)
        if len(body) > self.MAX_ERROR_BODY_CHARS:
            body = body[:self.MAX_ERROR_BODY_CHARS] + '…'
        return f"{head}: {body}"

    def _failure(self, exc, prefix: str = '') -> str:
        """The message for a transport-level failure, with secrets removed.

        ``str(exc)`` on a requests exception embeds the full URL, so for the
        providers that authenticate with query parameters it embeds the
        credentials as well.
        """
        return f"{prefix}{self.redact_secrets(exc)}"

    @abstractmethod
    def create_txt_record(
        self, 
        domain: str, 
        record_name: str, 
        record_value: str, 
        ttl: int = 300
    ) -> Tuple[bool, str]:
        """
        Create a TXT record for ACME DNS-01 challenge.
        
        Args:
            domain: The base domain (e.g., 'example.com')
            record_name: Full record name (e.g., '_acme-challenge.example.com')
            record_value: The challenge value to set
            ttl: Time to live in seconds (default 300)
        
        Returns:
            Tuple of (success: bool, message: str)
        """
        pass
    
    @abstractmethod
    def delete_txt_record(
        self, 
        domain: str, 
        record_name: str
    ) -> Tuple[bool, str]:
        """
        Delete a TXT record after ACME validation.
        
        Args:
            domain: The base domain
            record_name: Full record name to delete
        
        Returns:
            Tuple of (success: bool, message: str)
        """
        pass
    
    @abstractmethod
    def test_connection(self) -> Tuple[bool, str]:
        """
        Test API connection and credentials.
        
        Returns:
            Tuple of (success: bool, message: str)
        """
        pass
    
    # Registry suffixes that take two labels, so the registrable domain under
    # them takes three. Without this, `example.co.uk` reads as `co.uk` and the
    # record is aimed at a zone nobody can hold. Kept here rather than in one
    # provider because every provider that has no zone API needs it.
    _MULTI_PART_TLDS = {
        'co.uk', 'org.uk', 'ac.uk', 'me.uk', 'net.uk',  # UK
        'com.au', 'net.au', 'org.au', 'edu.au',  # Australia
        'co.jp', 'or.jp', 'ne.jp', 'ac.jp', 'go.jp',  # Japan
        'co.nz', 'org.nz', 'net.nz', 'govt.nz',  # New Zealand
        'com.br', 'net.br', 'org.br',  # Brazil
        'co.in', 'co.za', 'co.ke', 'co.zw',  # India/South Africa/Kenya/Zimbabwe
        'com.hk', 'net.hk', 'org.hk',  # Hong Kong
        'com.sg', 'net.sg', 'org.sg', 'gov.sg',  # Singapore
        'com.tw', 'org.tw', 'edu.tw', 'gov.tw', 'idv.tw',  # Taiwan
        'com.vn', 'net.vn', 'org.vn',  # Vietnam
        'com.my', 'net.my', 'org.my',  # Malaysia
        'com.mx', 'net.mx', 'org.mx',  # Mexico
        'com.ar', 'net.ar', 'org.ar',  # Argentina
        'com.pe', 'net.pe', 'org.pe',  # Peru
        'com.co', 'net.co', 'org.co',  # Colombia
        'com.ec', 'net.ec', 'org.ec',  # Ecuador
        'com.ve', 'net.ve', 'org.ve',  # Venezuela
    }

    @staticmethod
    def _normalise_name(name) -> str:
        """Lowercase, no trailing root dot, no wildcard label."""
        if not name or not isinstance(name, str):
            return ''
        name = name.strip().lower().rstrip('.')
        if name.startswith('*.'):
            name = name[2:]
        return name

    @classmethod
    def find_zone(cls, fqdn: str, candidates, key=None):
        """The most specific zone in `candidates` that holds `fqdn`.

        A dns-01 record only answers from the zone that is authoritative for
        it. When an operator holds both `example.co.uk` and a delegated
        `sub.example.co.uk`, the record for a name under the child belongs in
        the child; written to the parent it is never served, the CA keeps
        retrying and the order expires with nothing in UCM explaining why.

        Selection is therefore by longest match, not by whichever candidate
        the provider's API happened to list first. `endswith` alone is not
        enough either: it has no label boundary, so zone `example.com` would
        capture `notexample.com`, and an empty candidate name matches
        everything.

        Args:
            fqdn: the name being validated (a leading `*.` is ignored)
            candidates: zone names, or objects to read a name out of
            key: how to read the name from a candidate (default: itself)

        Returns:
            The winning candidate exactly as it was given, or None.
        """
        target = cls._normalise_name(fqdn)
        if not target:
            return None

        best = None
        best_len = -1
        for candidate in candidates or []:
            raw = key(candidate) if key else candidate
            zone = cls._normalise_name(raw)
            if not zone:
                continue
            if target != zone and not target.endswith('.' + zone):
                continue
            if len(zone) > best_len:
                best, best_len = candidate, len(zone)
        return best

    def get_zone_for_domain(self, domain: str) -> Optional[str]:
        """
        Guess the registrable zone for a domain, for providers with no zone API.

        Override if provider needs special zone detection.

        Args:
            domain: The domain to find zone for

        Returns:
            Zone name or None if not found
        """
        domain = self._normalise_name(domain)
        if not domain:
            return None
        parts = domain.split('.')
        if len(parts) >= 3 and '.'.join(parts[-2:]) in self._MULTI_PART_TLDS:
            return '.'.join(parts[-3:])
        if len(parts) >= 2:
            return '.'.join(parts[-2:])
        return domain

    def get_acme_challenge_name(self, domain: str) -> str:
        """
        Get the full record name for ACME challenge.
        
        Args:
            domain: The domain being validated
        
        Returns:
            Full record name (e.g., '_acme-challenge.example.com')
        """
        # Remove wildcard prefix if present
        if domain.startswith('*.'):
            domain = domain[2:]
        return f"_acme-challenge.{domain}"
    
    def get_relative_record_name(self, record_name: str, zone: str) -> str:
        """
        Get record name relative to zone.
        Some APIs want just '_acme-challenge', others want the full name.
        
        Args:
            record_name: Full record name
            zone: Zone name
        
        Returns:
            Relative record name
        """
        if record_name.endswith(f".{zone}"):
            return record_name[:-len(f".{zone}")]
        return record_name
    
    @classmethod
    def get_credential_schema(cls) -> List[Dict[str, Any]]:
        """
        Get schema for required and optional credentials.
        Override for custom field types (password, select, etc.)
        
        Returns:
            List of credential field definitions
        """
        schema = []
        for key in cls.REQUIRED_CREDENTIALS:
            schema.append({
                'name': key,
                'label': key.replace('_', ' ').title(),
                'type': 'password' if 'secret' in key.lower() or 'key' in key.lower() else 'text',
                'required': True,
            })
        for key in cls.OPTIONAL_CREDENTIALS:
            schema.append({
                'name': key,
                'label': key.replace('_', ' ').title(),
                'type': 'text',
                'required': False,
            })
        return schema
    
    @classmethod
    def validate_credentials(cls, credentials: Dict[str, Any]) -> None:
        """Raise FipsRestricted (a ValueError) for credentials a mode refuses."""

    @classmethod
    def to_dict(cls) -> Dict[str, Any]:
        """
        Get provider info for API responses.
        
        Returns:
            Provider type information
        """
        return {
            'type': cls.PROVIDER_TYPE,
            'name': cls.PROVIDER_NAME,
            'description': cls.PROVIDER_DESCRIPTION,
            'credentials_schema': cls.get_credential_schema(),
        }
