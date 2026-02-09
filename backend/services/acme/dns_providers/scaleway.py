"""
Scaleway DNS Provider
Uses Scaleway Domains and DNS API
https://www.scaleway.com/en/developers/api/domains-and-dns/
"""
import requests
from typing import Tuple, Dict, Any, Optional
import logging

from .base import BaseDnsProvider

logger = logging.getLogger(__name__)


class ScalewayDnsProvider(BaseDnsProvider):
    """
    Scaleway DNS Provider.
    
    Required credentials:
    - api_token: Scaleway API Token (Secret Key)
    
    Get token at: console.scaleway.com > IAM > API Keys
    """
    
    PROVIDER_TYPE = "scaleway"
    PROVIDER_NAME = "Scaleway"
    PROVIDER_DESCRIPTION = "Scaleway DNS API (France)"
    REQUIRED_CREDENTIALS = ["api_token"]
    
    BASE_URL = "https://api.scaleway.com/domain/v2beta1"
    
    def __init__(self, credentials: Dict[str, Any]):
        super().__init__(credentials)
        self._zone_cache: Dict[str, str] = {}
    
    def _get_headers(self) -> Dict[str, str]:
        return {
            'X-Auth-Token': self.credentials['api_token'],
            'Content-Type': 'application/json',
        }
    
    def _request(
        self, 
        method: str, 
        path: str, 
        data: Optional[Dict] = None,
        params: Optional[Dict] = None
    ) -> Tuple[bool, Any]:
        """Make Scaleway API request"""
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
            
            if response.text:
                return True, response.json()
            return True, None
            
        except requests.RequestException as e:
            logger.error(f"Scaleway API request failed: {e}")
            return False, str(e)
    
    def _get_zone_name(self, domain: str) -> Optional[str]:
        """Get DNS zone name for domain"""
        if domain in self._zone_cache:
            return self._zone_cache[domain]
        
        success, result = self._request('GET', '/dns-zones')
        if not success:
            return None
        
        zones = result.get('dns_zones', [])
        
        # Find best matching zone
        domain_parts = domain.split('.')
        for i in range(len(domain_parts) - 1):
            zone_name = '.'.join(domain_parts[i:])
            for zone in zones:
                if zone['domain'] == zone_name:
                    self._zone_cache[domain] = zone_name
                    return zone_name
        
        return None
    
    def create_txt_record(
        self, 
        domain: str, 
        record_name: str, 
        record_value: str, 
        ttl: int = 300
    ) -> Tuple[bool, str]:
        """Create TXT record via Scaleway API"""
        zone_name = self._get_zone_name(domain)
        if not zone_name:
            return False, f"Could not find zone for domain {domain}"
        
        # Get relative name
        relative_name = self.get_relative_record_name(record_name, zone_name)
        
        # Scaleway uses PATCH to add records
        data = {
            'changes': [{
                'add': {
                    'records': [{
                        'name': relative_name,
                        'type': 'TXT',
                        'ttl': ttl,
                        'data': f'"{record_value}"'
                    }]
                }
            }],
            'return_all_records': False
        }
        
        success, result = self._request('PATCH', f'/dns-zones/{zone_name}/records', data)
        
        if not success:
            return False, f"Failed to create record: {result}"
        
        logger.info(f"Scaleway: Created TXT record {record_name}")
        return True, "Record created successfully"
    
    def delete_txt_record(self, domain: str, record_name: str) -> Tuple[bool, str]:
        """Delete TXT record via Scaleway API"""
        zone_name = self._get_zone_name(domain)
        if not zone_name:
            return False, f"Could not find zone for domain {domain}"
        
        relative_name = self.get_relative_record_name(record_name, zone_name)
        
        # Scaleway uses PATCH with delete action
        data = {
            'changes': [{
                'delete': {
                    'id_fields': {
                        'name': relative_name,
                        'type': 'TXT'
                    }
                }
            }],
            'return_all_records': False
        }
        
        success, result = self._request('PATCH', f'/dns-zones/{zone_name}/records', data)
        
        if not success:
            if 'not found' in str(result).lower():
                return True, "Record not found (already deleted?)"
            return False, f"Failed to delete record: {result}"
        
        logger.info(f"Scaleway: Deleted TXT record {record_name}")
        return True, "Record deleted successfully"
    
    def test_connection(self) -> Tuple[bool, str]:
        """Test Scaleway API connection"""
        success, result = self._request('GET', '/dns-zones')
        if success:
            zones = result.get('dns_zones', [])
            zone_names = [z['domain'] for z in zones]
            return True, f"Connected successfully. Found {len(zones)} zone(s): {', '.join(zone_names[:5])}"
        return False, f"Connection failed: {result}"
    
    @classmethod
    def get_credential_schema(cls):
        return [
            {'name': 'api_token', 'label': 'API Secret Key', 'type': 'password', 'required': True,
             'help': 'console.scaleway.com > IAM > API Keys > Secret Key'},
        ]
