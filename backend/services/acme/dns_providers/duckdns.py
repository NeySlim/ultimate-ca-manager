"""
DuckDNS Provider
Free dynamic DNS with ACME TXT support
https://www.duckdns.org/
"""
import requests
from typing import Tuple, Dict, Any
import logging

from .base import BaseDnsProvider

logger = logging.getLogger(__name__)


class DuckDnsDnsProvider(BaseDnsProvider):
    """
    DuckDNS Provider - Free Dynamic DNS with Let's Encrypt support.
    
    Required credentials:
    - token: DuckDNS Token
    
    Get token at: duckdns.org after login (shown on main page)
    
    Note: DuckDNS domains are subdomains of duckdns.org (e.g., myname.duckdns.org)
    """
    
    PROVIDER_TYPE = "duckdns"
    PROVIDER_NAME = "DuckDNS"
    PROVIDER_DESCRIPTION = "DuckDNS (Free Dynamic DNS)"
    REQUIRED_CREDENTIALS = ["token"]
    
    BASE_URL = "https://www.duckdns.org/update"
    
    def __init__(self, credentials: Dict[str, Any]):
        super().__init__(credentials)
    
    def _extract_subdomain(self, domain: str) -> str:
        """Extract subdomain from full domain name"""
        # DuckDNS domains are like: subdomain.duckdns.org
        if domain.endswith('.duckdns.org'):
            return domain[:-12]  # Remove .duckdns.org
        return domain
    
    def create_txt_record(
        self, 
        domain: str, 
        record_name: str, 
        record_value: str, 
        ttl: int = 300
    ) -> Tuple[bool, str]:
        """Create TXT record via DuckDNS API"""
        # For ACME challenges, record_name is _acme-challenge.subdomain.duckdns.org
        # We need to extract just the subdomain part
        
        # Remove _acme-challenge. prefix if present
        clean_name = record_name
        if clean_name.startswith('_acme-challenge.'):
            clean_name = clean_name[16:]
        
        subdomain = self._extract_subdomain(clean_name)
        
        params = {
            'domains': subdomain,
            'token': self.credentials['token'],
            'txt': record_value
        }
        
        try:
            response = requests.get(
                self.BASE_URL,
                params=params,
                timeout=30
            )
            
            result = response.text.strip()
            
            if result == 'OK':
                logger.info(f"DuckDNS: Created TXT record for {subdomain}")
                return True, "Record created successfully"
            elif result == 'KO':
                return False, "DuckDNS returned KO - check token and domain"
            else:
                return False, f"Unexpected response: {result}"
                
        except requests.RequestException as e:
            logger.error(f"DuckDNS API request failed: {e}")
            return False, str(e)
    
    def delete_txt_record(self, domain: str, record_name: str) -> Tuple[bool, str]:
        """Delete TXT record via DuckDNS API (set to empty)"""
        # Remove _acme-challenge. prefix if present
        clean_name = record_name
        if clean_name.startswith('_acme-challenge.'):
            clean_name = clean_name[16:]
        
        subdomain = self._extract_subdomain(clean_name)
        
        # DuckDNS clears TXT by setting it to empty string
        params = {
            'domains': subdomain,
            'token': self.credentials['token'],
            'txt': '',
            'clear': 'true'
        }
        
        try:
            response = requests.get(
                self.BASE_URL,
                params=params,
                timeout=30
            )
            
            result = response.text.strip()
            
            if result == 'OK':
                logger.info(f"DuckDNS: Cleared TXT record for {subdomain}")
                return True, "Record deleted successfully"
            elif result == 'KO':
                return False, "DuckDNS returned KO - check token and domain"
            else:
                return False, f"Unexpected response: {result}"
                
        except requests.RequestException as e:
            logger.error(f"DuckDNS API request failed: {e}")
            return False, str(e)
    
    def test_connection(self) -> Tuple[bool, str]:
        """Test DuckDNS API connection"""
        # DuckDNS doesn't have a list endpoint, so we just verify the token format
        token = self.credentials.get('token', '')
        
        if not token:
            return False, "No token provided"
        
        if len(token) < 30:
            return False, "Token appears too short"
        
        # Try to get current IP (this validates the token)
        try:
            # We can't really test without a domain, so just validate token format
            return True, "Token format validated. Use with your duckdns.org subdomain."
        except Exception as e:
            return False, f"Connection test failed: {str(e)}"
    
    @classmethod
    def get_credential_schema(cls):
        return [
            {'name': 'token', 'label': 'Token', 'type': 'password', 'required': True,
             'help': 'Your DuckDNS token (shown on duckdns.org after login)'},
        ]
