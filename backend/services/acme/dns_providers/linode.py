"""
Linode DNS Provider
Akamai Cloud (formerly Linode) DNS API
https://www.linode.com/docs/api/domains/
"""
import requests
from typing import Tuple, Dict, Any, Optional
import logging

from .base import BaseDnsProvider

logger = logging.getLogger(__name__)


class LinodeDnsProvider(BaseDnsProvider):
    """
    Linode (Akamai Cloud) DNS Provider.
    
    Required credentials:
    - api_token: Linode Personal Access Token
    
    Get token at: cloud.linode.com > Account > API Tokens
    Requires: domains:read_write scope
    """
    
    PROVIDER_TYPE = "linode"
    PROVIDER_NAME = "Linode"
    PROVIDER_DESCRIPTION = "Linode/Akamai Cloud DNS API"
    REQUIRED_CREDENTIALS = ["api_token"]
    
    BASE_URL = "https://api.linode.com/v4"
    
    def __init__(self, credentials: Dict[str, Any]):
        super().__init__(credentials)
        self._domain_cache: Dict[str, Dict] = {}
    
    def _get_headers(self) -> Dict[str, str]:
        return {
            'Authorization': f"Bearer {self.credentials['api_token']}",
            'Content-Type': 'application/json',
        }
    
    def _request(
        self, 
        method: str, 
        path: str, 
        data: Optional[Dict] = None,
        params: Optional[Dict] = None
    ) -> Tuple[bool, Any]:
        """Make Linode API request"""
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
                    errors = error.get('errors', [])
                    if errors:
                        error_msg = errors[0].get('reason', str(error))
                    else:
                        error_msg = str(error)
                except:
                    error_msg = response.reason
                return False, error_msg
            
            if response.text:
                return True, response.json()
            return True, None
            
        except requests.RequestException as e:
            logger.error(f"Linode API request failed: {e}")
            return False, str(e)
    
    def _get_domain(self, domain: str) -> Optional[Dict]:
        """Get domain info for a domain name"""
        if domain in self._domain_cache:
            return self._domain_cache[domain]
        
        success, result = self._request('GET', '/domains')
        if not success:
            return None
        
        domains = result.get('data', [])
        
        # Find best matching domain
        domain_parts = domain.split('.')
        for i in range(len(domain_parts) - 1):
            domain_name = '.'.join(domain_parts[i:])
            for d in domains:
                if d.get('domain') == domain_name:
                    self._domain_cache[domain] = d
                    return d
        
        return None
    
    def create_txt_record(
        self, 
        domain: str, 
        record_name: str, 
        record_value: str, 
        ttl: int = 300
    ) -> Tuple[bool, str]:
        """Create TXT record via Linode API"""
        domain_info = self._get_domain(domain)
        if not domain_info:
            return False, f"Could not find domain for {domain}"
        
        domain_id = domain_info['id']
        domain_name = domain_info['domain']
        
        # Get relative name
        if record_name.endswith('.' + domain_name):
            name = record_name[:-len(domain_name) - 1]
        elif record_name == domain_name:
            name = ''
        else:
            name = record_name
        
        data = {
            'type': 'TXT',
            'name': name,
            'target': record_value,
            'ttl_sec': ttl
        }
        
        success, result = self._request(
            'POST',
            f'/domains/{domain_id}/records',
            data
        )
        
        if not success:
            return False, f"Failed to create record: {result}"
        
        logger.info(f"Linode: Created TXT record {record_name}")
        return True, "Record created successfully"
    
    def delete_txt_record(self, domain: str, record_name: str) -> Tuple[bool, str]:
        """Delete TXT record via Linode API"""
        domain_info = self._get_domain(domain)
        if not domain_info:
            return False, f"Could not find domain for {domain}"
        
        domain_id = domain_info['id']
        domain_name = domain_info['domain']
        
        # Get relative name
        if record_name.endswith('.' + domain_name):
            name = record_name[:-len(domain_name) - 1]
        elif record_name == domain_name:
            name = ''
        else:
            name = record_name
        
        # Find the record
        success, result = self._request('GET', f'/domains/{domain_id}/records')
        if not success:
            return False, f"Failed to list records: {result}"
        
        records = result.get('data', [])
        record_id = None
        for r in records:
            if r.get('type') == 'TXT' and r.get('name', '') == name:
                record_id = r.get('id')
                break
        
        if not record_id:
            return True, "Record not found (already deleted?)"
        
        success, result = self._request('DELETE', f'/domains/{domain_id}/records/{record_id}')
        
        if not success:
            if 'not found' in str(result).lower():
                return True, "Record not found (already deleted?)"
            return False, f"Failed to delete record: {result}"
        
        logger.info(f"Linode: Deleted TXT record {record_name}")
        return True, "Record deleted successfully"
    
    def test_connection(self) -> Tuple[bool, str]:
        """Test Linode API connection"""
        success, result = self._request('GET', '/domains')
        if success:
            domains = result.get('data', [])
            domain_names = [d.get('domain', '') for d in domains]
            return True, f"Connected successfully. Found {len(domains)} domain(s): {', '.join(domain_names[:5])}"
        return False, f"Connection failed: {result}"
    
    @classmethod
    def get_credential_schema(cls):
        return [
            {'name': 'api_token', 'label': 'Personal Access Token', 'type': 'password', 'required': True,
             'help': 'cloud.linode.com > Account > API Tokens (requires domains:read_write)'},
        ]
