"""
Gandi DNS Provider
Uses Gandi LiveDNS API for record management
https://api.gandi.net/docs/livedns/
"""
import requests
from typing import Tuple, Dict, Any, Optional
import logging

from .base import BaseDnsProvider

logger = logging.getLogger(__name__)


class GandiDnsProvider(BaseDnsProvider):
    """
    Gandi LiveDNS Provider.
    
    Required credentials:
    - api_key: Gandi API Key (Personal Access Token recommended)
    
    Get token at: https://account.gandi.net/en/users/USER/security
    (Replace USER with your username)
    """
    
    PROVIDER_TYPE = "gandi"
    PROVIDER_NAME = "Gandi"
    PROVIDER_DESCRIPTION = "Gandi LiveDNS API (France)"
    REQUIRED_CREDENTIALS = ["api_key"]
    
    BASE_URL = "https://api.gandi.net/v5/livedns"
    
    def __init__(self, credentials: Dict[str, Any]):
        super().__init__(credentials)
        self._domain_cache: Dict[str, bool] = {}
    
    def _get_headers(self) -> Dict[str, str]:
        return {
            'Authorization': f"Bearer {self.credentials['api_key']}",
            'Content-Type': 'application/json',
        }
    
    def _request(
        self, 
        method: str, 
        path: str, 
        data: Optional[Dict] = None,
        params: Optional[Dict] = None
    ) -> Tuple[bool, Any]:
        """Make Gandi API request"""
        url = f"{self.BASE_URL}{path}"
        
        try:
            response = requests.request(
                method=method,
                url=url,
                headers=self._get_headers(),
                json=data,
                params=params,
                timeout=30
            )
            
            if response.status_code >= 400:
                try:
                    error = response.json()
                    # Gandi error format varies
                    if isinstance(error, dict):
                        error_msg = error.get('message') or error.get('cause') or error.get('error') or response.reason
                    else:
                        error_msg = str(error)
                except:
                    error_msg = response.reason
                return False, error_msg
            
            if response.text and response.status_code != 204:
                return True, response.json()
            return True, None
            
        except requests.RequestException as e:
            logger.error(f"Gandi API request failed: {e}")
            return False, str(e)
    
    def _get_domain(self, domain: str) -> Optional[str]:
        """Get the Gandi domain that manages this domain"""
        # Check cache
        if domain in self._domain_cache:
            return domain if self._domain_cache[domain] else None
        
        # Try to find the managing domain
        domain_parts = domain.split('.')
        for i in range(len(domain_parts) - 1):
            test_domain = '.'.join(domain_parts[i:])
            
            # Check if domain exists
            success, result = self._request('GET', f'/domains/{test_domain}')
            if success:
                self._domain_cache[test_domain] = True
                return test_domain
            self._domain_cache[test_domain] = False
        
        return None
    
    def create_txt_record(
        self, 
        domain: str, 
        record_name: str, 
        record_value: str, 
        ttl: int = 300
    ) -> Tuple[bool, str]:
        """Create TXT record via Gandi API"""
        gandi_domain = self._get_domain(domain)
        if not gandi_domain:
            return False, f"Could not find domain {domain} in Gandi"
        
        # Get relative name
        if record_name.endswith(f".{gandi_domain}"):
            relative_name = record_name[:-len(f".{gandi_domain}")]
        else:
            relative_name = record_name
        
        # Gandi API: PUT /domains/{domain}/records/{name}/{type}
        data = {
            'rrset_values': [record_value],
            'rrset_ttl': ttl,
        }
        
        success, result = self._request(
            'PUT', 
            f'/domains/{gandi_domain}/records/{relative_name}/TXT',
            data
        )
        
        if not success:
            return False, f"Failed to create record: {result}"
        
        logger.info(f"Gandi: Created TXT record {record_name}")
        return True, "Record created successfully"
    
    def delete_txt_record(self, domain: str, record_name: str) -> Tuple[bool, str]:
        """Delete TXT record via Gandi API"""
        gandi_domain = self._get_domain(domain)
        if not gandi_domain:
            return False, f"Could not find domain {domain} in Gandi"
        
        # Get relative name
        if record_name.endswith(f".{gandi_domain}"):
            relative_name = record_name[:-len(f".{gandi_domain}")]
        else:
            relative_name = record_name
        
        # Delete the record
        success, result = self._request(
            'DELETE',
            f'/domains/{gandi_domain}/records/{relative_name}/TXT'
        )
        
        if not success:
            # 404 means record doesn't exist, which is fine
            if '404' in str(result) or 'not found' in str(result).lower():
                return True, "Record not found (already deleted?)"
            return False, f"Failed to delete record: {result}"
        
        logger.info(f"Gandi: Deleted TXT record {record_name}")
        return True, "Record deleted successfully"
    
    def test_connection(self) -> Tuple[bool, str]:
        """Test Gandi API connection"""
        success, result = self._request('GET', '/domains')
        if success:
            domains = result if isinstance(result, list) else []
            return True, f"Connected successfully. Found {len(domains)} domain(s)."
        return False, f"Connection failed: {result}"
    
    @classmethod
    def get_credential_schema(cls):
        return [
            {'name': 'api_key', 'label': 'API Key / PAT', 'type': 'password', 'required': True,
             'help': 'Personal Access Token from account.gandi.net'},
        ]
