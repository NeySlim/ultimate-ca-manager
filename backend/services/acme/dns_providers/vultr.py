"""
Vultr DNS Provider
Vultr Cloud DNS API
https://www.vultr.com/api/#dns
"""
import requests
from typing import Tuple, Dict, Any, Optional
import logging

from .base import BaseDnsProvider

logger = logging.getLogger(__name__)


class VultrDnsProvider(BaseDnsProvider):
    """
    Vultr DNS Provider.
    
    Required credentials:
    - api_key: Vultr API Key
    
    Get key at: my.vultr.com > Account > API
    """
    
    PROVIDER_TYPE = "vultr"
    PROVIDER_NAME = "Vultr"
    PROVIDER_DESCRIPTION = "Vultr Cloud DNS API"
    REQUIRED_CREDENTIALS = ["api_key"]
    
    BASE_URL = "https://api.vultr.com/v2"
    MAX_PAGES = 50
    
    def __init__(self, credentials: Dict[str, Any]):
        super().__init__(credentials)
        self._domain_cache: Dict[str, str] = {}
    
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
        """Make Vultr API request"""
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
                    error_msg = error.get('error', str(error))
                except Exception:
                    error_msg = response.reason
                return False, error_msg
            
            if response.text:
                return True, response.json()
            return True, None
            
        except (requests.RequestException, ValueError) as e:
            logger.error(f"Vultr API request failed: {self._failure(e)}")
            return False, self._failure(e)
    
    def _list(self, path: str, key: str) -> Tuple[bool, Any]:
        """Every item of a cursor-paginated listing: `meta.links.next` is empty on the last page."""
        items = []
        params = {'per_page': 500}
        for _ in range(self.MAX_PAGES):
            success, result = self._request('GET', path, params=params)
            if not success:
                return False, result
            items.extend((result or {}).get(key) or [])
            cursor = (((result or {}).get('meta') or {}).get('links') or {}).get('next')
            if not cursor:
                return True, items
            params = {'per_page': 500, 'cursor': cursor}
        return False, f"More than {self.MAX_PAGES} pages at {path}"

    def _get_domain(self, domain: str) -> Optional[str]:
        """Get domain name for a subdomain"""
        if domain in self._domain_cache:
            return self._domain_cache[domain]
        
        success, domains = self._list('/domains', 'domains')
        if not success:
            return None
        found = self.find_zone(domain, domains, key=lambda d: d.get('domain'))
        if not found:
            return None
        self._domain_cache[domain] = found['domain']
        return found['domain']
    
    def create_txt_record(
        self, 
        domain: str, 
        record_name: str, 
        record_value: str, 
        ttl: int = 300
    ) -> Tuple[bool, str]:
        """Create TXT record via Vultr API"""
        domain_name = self._get_domain(domain)
        if not domain_name:
            return False, f"Could not find domain for {domain}"
        
        # Get relative name
        if record_name.endswith('.' + domain_name):
            name = record_name[:-len(domain_name) - 1]
        elif record_name == domain_name:
            name = ''
        else:
            name = record_name
        
        data = {
            'name': name,
            'type': 'TXT',
            'data': f'"{record_value}"',
            'ttl': ttl
        }
        
        success, result = self._request(
            'POST',
            f'/domains/{domain_name}/records',
            data
        )
        
        if not success:
            return False, f"Failed to create record: {result}"
        
        logger.info(f"Vultr: Created TXT record {record_name}")
        return True, "Record created successfully"
    
    def delete_txt_record(self, domain: str, record_name: str, record_value: str) -> Tuple[bool, str]:
        """Delete TXT record via Vultr API"""
        domain_name = self._get_domain(domain)
        if not domain_name:
            return False, f"Could not find domain for {domain}"
        
        # Get relative name
        if record_name.endswith('.' + domain_name):
            name = record_name[:-len(domain_name) - 1]
        elif record_name == domain_name:
            name = ''
        else:
            name = record_name
        
        # Find the record
        success, records = self._list(f'/domains/{domain_name}/records', 'records')
        if not success:
            msg = f"Failed to list records: {records}"
            logger.warning(f"Vultr: {msg}")
            return False, msg
        
        record_ids = [r.get('id') for r in records
                      if r.get('type') == 'TXT' and r.get('name', '') == name
                      and self.txt_matches(r.get('data'), record_value)]
        
        if not record_ids:
            return True, "Record not found (already deleted?)"
        
        for record_id in record_ids:
            success, result = self._request('DELETE', f'/domains/{domain_name}/records/{record_id}')
            if not success and 'not found' not in str(result).lower():
                logger.warning(f"Vultr: failed to delete TXT value of {record_name}: {result}")
                return False, f"Failed to delete record: {result}"
        
        logger.info(f"Vultr: Deleted TXT record {record_name}")
        return True, "Record deleted successfully"
    
    def test_connection(self) -> Tuple[bool, str]:
        """Test Vultr API connection"""
        success, domains = self._list('/domains', 'domains')
        if success:
            domain_names = [d.get('domain', '') for d in domains]
            return True, f"Connected successfully. Found {len(domains)} domain(s): {', '.join(domain_names[:5])}"
        return False, f"Connection failed: {domains}"
    
    @classmethod
    def get_credential_schema(cls):
        return [
            {'name': 'api_key', 'label': 'API Key', 'type': 'password', 'required': True,
             'help': 'my.vultr.com > Account > API'},
        ]
