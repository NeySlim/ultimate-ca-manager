"""
BookMyName DNS Provider
French domain registrar with DynDNS API
https://fr.faqs.bookmyname.com/frfaqs/dyndns
"""
import requests
from typing import Tuple, Dict, Any
import logging
from urllib.parse import quote

from .base import BaseDnsProvider

logger = logging.getLogger(__name__)


class BookMyNameDnsProvider(BaseDnsProvider):
    """
    BookMyName DNS Provider (France).
    
    Required credentials:
    - username: BookMyName Handle (e.g., HANDLE-FREE)
    - password: Handle password or domain Authinfo
    
    Uses the DynDNS API for TXT record management.
    """
    
    PROVIDER_TYPE = "bookmyname"
    PROVIDER_NAME = "BookMyName"
    PROVIDER_DESCRIPTION = "BookMyName DNS API (France)"
    REQUIRED_CREDENTIALS = ["username", "password"]
    
    BASE_URL = "https://www.bookmyname.com/dyndns/"
    
    def __init__(self, credentials: Dict[str, Any]):
        super().__init__(credentials)
    
    def _make_request(
        self, 
        hostname: str,
        record_type: str,
        action: str,
        value: str,
        ttl: int = 300
    ) -> Tuple[bool, str]:
        """
        Make BookMyName DynDNS API request.
        
        API format:
        https://USERNAME:PASSWORD@www.bookmyname.com/dyndns/
            ?hostname=HOSTNAME&type=txt&ttl=TTL&do=add|remove&value="VALUE"
        """
        params = {
            'hostname': hostname,
            'type': record_type.lower(),
            'ttl': ttl,
            'do': action,
            'value': f'"{value}"' if record_type.lower() == 'txt' else value
        }
        
        try:
            response = requests.get(
                self.BASE_URL,
                params=params,
                auth=(self.credentials['username'], self.credentials['password']),
                timeout=30
            )
            
            # BookMyName returns text responses
            result_text = response.text.strip()
            
            if response.status_code >= 400:
                return False, f"HTTP {response.status_code}: {result_text}"
            
            # Check for success indicators
            if 'ok' in result_text.lower() or 'good' in result_text.lower():
                return True, result_text
            elif 'error' in result_text.lower() or 'badauth' in result_text.lower():
                return False, result_text
            else:
                # Assume success if no error
                return True, result_text
            
        except requests.RequestException as e:
            logger.error(f"BookMyName API request failed: {e}")
            return False, str(e)
    
    def create_txt_record(
        self, 
        domain: str, 
        record_name: str, 
        record_value: str, 
        ttl: int = 300
    ) -> Tuple[bool, str]:
        """Create TXT record via BookMyName DynDNS API"""
        # BookMyName expects the full hostname
        success, result = self._make_request(
            hostname=record_name,
            record_type='txt',
            action='add',
            value=record_value,
            ttl=ttl
        )
        
        if success:
            logger.info(f"BookMyName: Created TXT record {record_name}")
            return True, "Record created successfully"
        else:
            return False, f"Failed to create record: {result}"
    
    def delete_txt_record(self, domain: str, record_name: str) -> Tuple[bool, str]:
        """Delete TXT record via BookMyName DynDNS API"""
        # For deletion, we need the value - try with empty first
        # BookMyName might require the exact value to delete
        # We'll try a generic delete approach
        
        # Note: BookMyName requires the exact value to delete a TXT record
        # This is a limitation - we'd need to store the value somewhere
        # For ACME challenges, we can try to delete by record name
        
        success, result = self._make_request(
            hostname=record_name,
            record_type='txt',
            action='remove',
            value='*',  # Attempt wildcard removal
            ttl=300
        )
        
        if success:
            logger.info(f"BookMyName: Deleted TXT record {record_name}")
            return True, "Record deleted successfully"
        else:
            # If wildcard doesn't work, consider it already deleted
            if 'not found' in result.lower() or 'nohost' in result.lower():
                return True, "Record not found (already deleted?)"
            return False, f"Failed to delete record: {result}"
    
    def test_connection(self) -> Tuple[bool, str]:
        """Test BookMyName API connection"""
        # BookMyName doesn't have a dedicated test endpoint
        # We'll try a simple IP check that requires auth
        try:
            response = requests.get(
                "https://www.bookmyname.com/myip.cgi",
                auth=(self.credentials['username'], self.credentials['password']),
                timeout=10
            )
            
            if response.status_code == 200:
                return True, f"Connected successfully (your IP: {response.text.strip()})"
            elif response.status_code == 401:
                return False, "Authentication failed: invalid username or password"
            else:
                return False, f"Connection failed: HTTP {response.status_code}"
                
        except requests.RequestException as e:
            return False, f"Connection failed: {str(e)}"
    
    @classmethod
    def get_credential_schema(cls):
        return [
            {'name': 'username', 'label': 'Handle', 'type': 'text', 'required': True,
             'placeholder': 'HANDLE-FREE',
             'help': 'Your BookMyName handle (e.g., HANDLE-FREE)'},
            {'name': 'password', 'label': 'Password', 'type': 'password', 'required': True,
             'help': 'Handle password or domain Authinfo'},
        ]
