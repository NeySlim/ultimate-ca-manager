"""
IONOS DNS Provider
Uses IONOS DNS API
https://developer.hosting.ionos.com/docs/dns
"""
import requests
from typing import Tuple, Dict, Any, Optional
import logging

from .base import BaseDnsProvider

logger = logging.getLogger(__name__)


class IonosDnsProvider(BaseDnsProvider):
    """
    IONOS DNS Provider.
    
    Required credentials:
    - public_prefix: IONOS API Public Prefix
    - api_key: IONOS API Key (Secret)
    
    Get credentials at: developer.hosting.ionos.com > API keys
    Format: {publicPrefix}.{secret}
    """
    
    PROVIDER_TYPE = "ionos"
    PROVIDER_NAME = "IONOS"
    PROVIDER_DESCRIPTION = "IONOS DNS API (Germany)"
    REQUIRED_CREDENTIALS = ["public_prefix", "api_key"]
    
    BASE_URL = "https://api.hosting.ionos.com/dns/v1"
    
    def __init__(self, credentials: Dict[str, Any]):
        super().__init__(credentials)
        self._zone_cache: Dict[str, Dict] = {}
    
    def _get_headers(self) -> Dict[str, str]:
        api_key = f"{self.credentials['public_prefix']}.{self.credentials['api_key']}"
        return {
            'X-API-Key': api_key,
            'Content-Type': 'application/json',
        }
    
    def _request(
        self, 
        method: str, 
        path: str, 
        data: Optional[Any] = None,
        params: Optional[Dict] = None
    ) -> Tuple[bool, Any]:
        """Make IONOS API request"""
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
            logger.error(f"IONOS API request failed: {e}")
            return False, str(e)
    
    def _get_zone(self, domain: str) -> Optional[Dict]:
        """Get zone for domain"""
        if domain in self._zone_cache:
            return self._zone_cache[domain]
        
        success, result = self._request('GET', '/zones')
        if not success:
            return None
        
        zones = result if isinstance(result, list) else result.get('zones', [])
        
        # Find best matching zone
        domain_parts = domain.split('.')
        for i in range(len(domain_parts) - 1):
            zone_name = '.'.join(domain_parts[i:])
            for zone in zones:
                if zone.get('name', '') == zone_name:
                    self._zone_cache[domain] = zone
                    return zone
        
        return None
    
    def create_txt_record(
        self, 
        domain: str, 
        record_name: str, 
        record_value: str, 
        ttl: int = 300
    ) -> Tuple[bool, str]:
        """Create TXT record via IONOS API"""
        zone = self._get_zone(domain)
        if not zone:
            return False, f"Could not find zone for domain {domain}"
        
        zone_id = zone['id']
        
        # IONOS expects full record name
        data = [{
            'name': record_name,
            'type': 'TXT',
            'content': record_value,
            'ttl': ttl,
            'prio': 0,
            'disabled': False
        }]
        
        success, result = self._request('POST', f'/zones/{zone_id}/records', data)
        
        if not success:
            return False, f"Failed to create record: {result}"
        
        logger.info(f"IONOS: Created TXT record {record_name}")
        return True, "Record created successfully"
    
    def delete_txt_record(self, domain: str, record_name: str) -> Tuple[bool, str]:
        """Delete TXT record via IONOS API"""
        zone = self._get_zone(domain)
        if not zone:
            return False, f"Could not find zone for domain {domain}"
        
        zone_id = zone['id']
        
        # First, find the record
        success, result = self._request('GET', f'/zones/{zone_id}')
        if not success:
            return False, f"Failed to get zone records: {result}"
        
        records = result.get('records', [])
        record_id = None
        for r in records:
            if r.get('name') == record_name and r.get('type') == 'TXT':
                record_id = r.get('id')
                break
        
        if not record_id:
            return True, "Record not found (already deleted?)"
        
        # Delete the record
        success, result = self._request('DELETE', f'/zones/{zone_id}/records/{record_id}')
        
        if not success:
            if 'not found' in str(result).lower():
                return True, "Record not found (already deleted?)"
            return False, f"Failed to delete record: {result}"
        
        logger.info(f"IONOS: Deleted TXT record {record_name}")
        return True, "Record deleted successfully"
    
    def test_connection(self) -> Tuple[bool, str]:
        """Test IONOS API connection"""
        success, result = self._request('GET', '/zones')
        if success:
            zones = result if isinstance(result, list) else result.get('zones', [])
            zone_names = [z.get('name', 'unknown') for z in zones]
            return True, f"Connected successfully. Found {len(zones)} zone(s): {', '.join(zone_names[:5])}"
        return False, f"Connection failed: {result}"
    
    @classmethod
    def get_credential_schema(cls):
        return [
            {'name': 'public_prefix', 'label': 'Public Prefix', 'type': 'text', 'required': True,
             'help': 'IONOS API Public Prefix (e.g., abc123)'},
            {'name': 'api_key', 'label': 'API Secret', 'type': 'password', 'required': True,
             'help': 'IONOS API Secret Key'},
        ]
