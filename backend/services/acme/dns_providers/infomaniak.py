"""
Infomaniak DNS Provider
Uses Infomaniak API for DNS record management
https://developer.infomaniak.com/docs/api
"""
import requests
from typing import Tuple, Dict, Any, Optional
import logging

from .base import BaseDnsProvider

logger = logging.getLogger(__name__)


class InfomaniakDnsProvider(BaseDnsProvider):
    """
    Infomaniak DNS Provider (Switzerland).
    
    Required credentials:
    - api_token: Infomaniak API Token
    
    Get token at: https://manager.infomaniak.com/v3/ng/accounts/token
    Required scope: domain
    """
    
    PROVIDER_TYPE = "infomaniak"
    PROVIDER_NAME = "Infomaniak"
    PROVIDER_DESCRIPTION = "Infomaniak DNS API (Switzerland)"
    REQUIRED_CREDENTIALS = ["api_token"]
    
    BASE_URL = "https://api.infomaniak.com"
    
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
        """Make Infomaniak API request"""
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
            
            result = response.json() if response.text else {}
            
            if response.status_code >= 400 or result.get('result') == 'error':
                error_msg = result.get('error', {}).get('description', response.reason)
                return False, error_msg
            
            return True, result.get('data', result)
            
        except requests.RequestException as e:
            logger.error(f"Infomaniak API request failed: {e}")
            return False, str(e)
    
    def _get_domain_info(self, domain: str) -> Optional[Dict]:
        """Get domain info from Infomaniak"""
        if domain in self._domain_cache:
            return self._domain_cache[domain]
        
        # List all domains
        success, domains = self._request('GET', '/1/product', params={'service_name': 'domain'})
        if not success:
            return None
        
        domain_parts = domain.split('.')
        for i in range(len(domain_parts) - 1):
            test_domain = '.'.join(domain_parts[i:])
            for d in (domains if isinstance(domains, list) else []):
                if d.get('customer_name') == test_domain:
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
        """Create TXT record via Infomaniak API"""
        domain_info = self._get_domain_info(domain)
        if not domain_info:
            return False, f"Could not find domain {domain} in Infomaniak"
        
        domain_id = domain_info.get('id')
        ik_domain = domain_info.get('customer_name')
        
        # Get relative name
        relative_name = self.get_relative_record_name(record_name, ik_domain)
        
        data = {
            'type': 'TXT',
            'source': relative_name,
            'target': record_value,
            'ttl': ttl,
        }
        
        success, result = self._request('POST', f'/1/domain/{domain_id}/dns/record', data)
        if not success:
            return False, f"Failed to create record: {result}"
        
        record_id = result.get('id', 'unknown') if isinstance(result, dict) else 'unknown'
        logger.info(f"Infomaniak: Created TXT record {record_name} (ID: {record_id})")
        return True, f"Record created successfully (ID: {record_id})"
    
    def delete_txt_record(self, domain: str, record_name: str) -> Tuple[bool, str]:
        """Delete TXT record via Infomaniak API"""
        domain_info = self._get_domain_info(domain)
        if not domain_info:
            return False, f"Could not find domain {domain} in Infomaniak"
        
        domain_id = domain_info.get('id')
        ik_domain = domain_info.get('customer_name')
        relative_name = self.get_relative_record_name(record_name, ik_domain)
        
        # Get all DNS records
        success, records = self._request('GET', f'/1/domain/{domain_id}/dns/record')
        if not success:
            return False, f"Failed to list records: {records}"
        
        # Find and delete matching TXT records
        deleted = 0
        record_list = records if isinstance(records, list) else []
        for record in record_list:
            if record.get('type') == 'TXT' and record.get('source') == relative_name:
                success, _ = self._request('DELETE', f'/1/domain/{domain_id}/dns/record/{record["id"]}')
                if success:
                    deleted += 1
        
        if deleted == 0:
            return True, "Record not found (already deleted?)"
        
        logger.info(f"Infomaniak: Deleted {deleted} TXT record(s) for {record_name}")
        return True, f"Deleted {deleted} record(s)"
    
    def test_connection(self) -> Tuple[bool, str]:
        """Test Infomaniak API connection"""
        success, result = self._request('GET', '/1/product', params={'service_name': 'domain'})
        if success:
            domains = result if isinstance(result, list) else []
            return True, f"Connected successfully. Found {len(domains)} domain(s)."
        return False, f"Connection failed: {result}"
    
    @classmethod
    def get_credential_schema(cls):
        return [
            {'name': 'api_token', 'label': 'API Token', 'type': 'password', 'required': True,
             'help': 'Get at manager.infomaniak.com/v3/ng/accounts/token'},
        ]
