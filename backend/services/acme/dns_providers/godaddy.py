"""
GoDaddy DNS Provider
https://developer.godaddy.com/doc/endpoint/domains
"""
import requests
from typing import Tuple, Dict, Any, Optional
import logging

from .base import BaseDnsProvider

logger = logging.getLogger(__name__)


class GoDaddyDnsProvider(BaseDnsProvider):
    """
    GoDaddy DNS Provider.
    
    Required credentials:
    - api_key: GoDaddy API Key
    - api_secret: GoDaddy API Secret
    
    Get credentials at: developer.godaddy.com > API Keys
    
    Note: GoDaddy requires 10+ domains or Discount Domain Club for API access.
    """
    
    PROVIDER_TYPE = "godaddy"
    PROVIDER_NAME = "GoDaddy"
    PROVIDER_DESCRIPTION = "GoDaddy DNS API"
    REQUIRED_CREDENTIALS = ["api_key", "api_secret"]
    
    BASE_URL = "https://api.godaddy.com/v1"
    
    def __init__(self, credentials: Dict[str, Any]):
        super().__init__(credentials)
        self._domain_cache: Dict[str, str] = {}
    
    def _get_headers(self) -> Dict[str, str]:
        return {
            'Authorization': f"sso-key {self.credentials['api_key']}:{self.credentials['api_secret']}",
            'Content-Type': 'application/json',
        }
    
    def _request(
        self, 
        method: str, 
        path: str, 
        data: Optional[Any] = None
    ) -> Tuple[bool, Any]:
        """Make GoDaddy API request"""
        url = f"{self.BASE_URL}{path}"
        
        try:
            response = requests.request(
                method=method,
                url=url,
                headers=self._get_headers(),
                json=data,
                timeout=30
            )
            
            if response.status_code >= 400:
                try:
                    error = response.json()
                    error_msg = error.get('message', str(error))
                except:
                    error_msg = response.reason
                return False, error_msg
            
            if response.text:
                return True, response.json()
            return True, None
            
        except requests.RequestException as e:
            logger.error(f"GoDaddy API request failed: {e}")
            return False, str(e)
    
    def _get_domain(self, domain: str) -> Optional[str]:
        """Get root domain for a subdomain"""
        if domain in self._domain_cache:
            return self._domain_cache[domain]
        
        success, result = self._request('GET', '/domains')
        if not success:
            return None
        
        domains = result if isinstance(result, list) else []
        domain_names = [d.get('domain') for d in domains]
        
        # Find best matching domain
        domain_parts = domain.split('.')
        for i in range(len(domain_parts) - 1):
            domain_name = '.'.join(domain_parts[i:])
            if domain_name in domain_names:
                self._domain_cache[domain] = domain_name
                return domain_name
        
        return None
    
    def create_txt_record(
        self, 
        domain: str, 
        record_name: str, 
        record_value: str, 
        ttl: int = 600
    ) -> Tuple[bool, str]:
        """Create TXT record via GoDaddy API"""
        domain_name = self._get_domain(domain)
        if not domain_name:
            return False, f"Could not find domain for {domain}"
        
        # Get relative name
        if record_name.endswith('.' + domain_name):
            name = record_name[:-len(domain_name) - 1]
        elif record_name == domain_name:
            name = '@'
        else:
            name = record_name
        
        # GoDaddy uses PATCH to add records (keeps existing)
        data = [{
            'data': record_value,
            'ttl': max(ttl, 600),  # GoDaddy minimum TTL is 600
        }]
        
        success, result = self._request(
            'PATCH',
            f'/domains/{domain_name}/records/TXT/{name}',
            data
        )
        
        if not success:
            return False, f"Failed to create record: {result}"
        
        logger.info(f"GoDaddy: Created TXT record {record_name}")
        return True, "Record created successfully"
    
    def delete_txt_record(self, domain: str, record_name: str) -> Tuple[bool, str]:
        """Delete TXT record via GoDaddy API"""
        domain_name = self._get_domain(domain)
        if not domain_name:
            return False, f"Could not find domain for {domain}"
        
        # Get relative name
        if record_name.endswith('.' + domain_name):
            name = record_name[:-len(domain_name) - 1]
        elif record_name == domain_name:
            name = '@'
        else:
            name = record_name
        
        # GoDaddy doesn't have a direct delete - we need to PUT empty array
        # or PUT all records except the one to delete
        success, result = self._request(
            'PUT',
            f'/domains/{domain_name}/records/TXT/{name}',
            []  # Empty array removes all TXT records for this name
        )
        
        if not success:
            if 'not found' in str(result).lower():
                return True, "Record not found (already deleted?)"
            return False, f"Failed to delete record: {result}"
        
        logger.info(f"GoDaddy: Deleted TXT record {record_name}")
        return True, "Record deleted successfully"
    
    def test_connection(self) -> Tuple[bool, str]:
        """Test GoDaddy API connection"""
        success, result = self._request('GET', '/domains')
        if success:
            domains = result if isinstance(result, list) else []
            domain_names = [d.get('domain', '') for d in domains]
            return True, f"Connected successfully. Found {len(domains)} domain(s): {', '.join(domain_names[:5])}"
        return False, f"Connection failed: {result}"
    
    @classmethod
    def get_credential_schema(cls):
        return [
            {'name': 'api_key', 'label': 'API Key', 'type': 'text', 'required': True,
             'help': 'developer.godaddy.com > API Keys'},
            {'name': 'api_secret', 'label': 'API Secret', 'type': 'password', 'required': True,
             'help': 'GoDaddy API Secret'},
        ]
