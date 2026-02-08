"""
DigitalOcean DNS Provider
Uses DigitalOcean API v2 for DNS record management
https://docs.digitalocean.com/reference/api/api-reference/#tag/Domain-Records
"""
import requests
from typing import Tuple, Dict, Any, Optional
import logging

from .base import BaseDnsProvider

logger = logging.getLogger(__name__)


class DigitalOceanDnsProvider(BaseDnsProvider):
    """
    DigitalOcean DNS Provider.
    
    Required credentials:
    - api_token: DigitalOcean Personal Access Token
    
    Get token at: https://cloud.digitalocean.com/account/api/tokens
    Required scope: Read/Write
    """
    
    PROVIDER_TYPE = "digitalocean"
    PROVIDER_NAME = "DigitalOcean"
    PROVIDER_DESCRIPTION = "DigitalOcean DNS API"
    REQUIRED_CREDENTIALS = ["api_token"]
    
    BASE_URL = "https://api.digitalocean.com/v2"
    
    def __init__(self, credentials: Dict[str, Any]):
        super().__init__(credentials)
        self._domain_cache: Dict[str, bool] = {}
    
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
        """Make DigitalOcean API request"""
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
                    error_msg = error.get('message', response.reason)
                except:
                    error_msg = response.reason
                return False, error_msg
            
            if response.text and response.status_code != 204:
                return True, response.json()
            return True, None
            
        except requests.RequestException as e:
            logger.error(f"DigitalOcean API request failed: {e}")
            return False, str(e)
    
    def _get_domain(self, domain: str) -> Optional[str]:
        """Find the DO domain that manages this domain"""
        domain_parts = domain.split('.')
        for i in range(len(domain_parts) - 1):
            test_domain = '.'.join(domain_parts[i:])
            
            if test_domain in self._domain_cache:
                if self._domain_cache[test_domain]:
                    return test_domain
                continue
            
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
        """Create TXT record via DigitalOcean API"""
        do_domain = self._get_domain(domain)
        if not do_domain:
            return False, f"Could not find domain {domain} in DigitalOcean"
        
        # Get relative name (DO uses @ for apex, name without domain suffix)
        relative_name = self.get_relative_record_name(record_name, do_domain)
        if not relative_name:
            relative_name = '@'
        
        data = {
            'type': 'TXT',
            'name': relative_name,
            'data': record_value,
            'ttl': ttl,
        }
        
        success, result = self._request('POST', f'/domains/{do_domain}/records', data)
        if not success:
            return False, f"Failed to create record: {result}"
        
        record_id = result.get('domain_record', {}).get('id', 'unknown')
        logger.info(f"DigitalOcean: Created TXT record {record_name} (ID: {record_id})")
        return True, f"Record created successfully (ID: {record_id})"
    
    def delete_txt_record(self, domain: str, record_name: str) -> Tuple[bool, str]:
        """Delete TXT record via DigitalOcean API"""
        do_domain = self._get_domain(domain)
        if not do_domain:
            return False, f"Could not find domain {domain} in DigitalOcean"
        
        relative_name = self.get_relative_record_name(record_name, do_domain)
        if not relative_name:
            relative_name = '@'
        
        # Get all records for domain
        success, result = self._request('GET', f'/domains/{do_domain}/records')
        if not success:
            return False, f"Failed to list records: {result}"
        
        records = result.get('domain_records', [])
        
        # Find and delete matching TXT records
        deleted = 0
        for record in records:
            if record['type'] == 'TXT' and record['name'] == relative_name:
                success, _ = self._request('DELETE', f'/domains/{do_domain}/records/{record["id"]}')
                if success:
                    deleted += 1
        
        if deleted == 0:
            return True, "Record not found (already deleted?)"
        
        logger.info(f"DigitalOcean: Deleted {deleted} TXT record(s) for {record_name}")
        return True, f"Deleted {deleted} record(s)"
    
    def test_connection(self) -> Tuple[bool, str]:
        """Test DigitalOcean API connection"""
        success, result = self._request('GET', '/domains')
        if success:
            domains = result.get('domains', [])
            return True, f"Connected successfully. Found {len(domains)} domain(s)."
        return False, f"Connection failed: {result}"
    
    @classmethod
    def get_credential_schema(cls):
        return [
            {'name': 'api_token', 'label': 'Personal Access Token', 'type': 'password', 'required': True,
             'help': 'Get at cloud.digitalocean.com/account/api/tokens'},
        ]
