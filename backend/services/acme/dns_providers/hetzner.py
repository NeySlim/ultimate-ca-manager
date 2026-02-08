"""
Hetzner DNS Provider
Uses Hetzner DNS API for record management
https://dns.hetzner.com/api-docs
"""
import requests
from typing import Tuple, Dict, Any, Optional
import logging

from .base import BaseDnsProvider

logger = logging.getLogger(__name__)


class HetznerDnsProvider(BaseDnsProvider):
    """
    Hetzner DNS Provider.
    
    Required credentials:
    - api_token: Hetzner DNS API Token
    
    Get token at: https://dns.hetzner.com/settings/api-token
    """
    
    PROVIDER_TYPE = "hetzner"
    PROVIDER_NAME = "Hetzner"
    PROVIDER_DESCRIPTION = "Hetzner DNS API (Germany)"
    REQUIRED_CREDENTIALS = ["api_token"]
    
    BASE_URL = "https://dns.hetzner.com/api/v1"
    
    def __init__(self, credentials: Dict[str, Any]):
        super().__init__(credentials)
        self._zone_cache: Dict[str, Dict] = {}
    
    def _get_headers(self) -> Dict[str, str]:
        return {
            'Auth-API-Token': self.credentials['api_token'],
            'Content-Type': 'application/json',
        }
    
    def _request(
        self, 
        method: str, 
        path: str, 
        data: Optional[Dict] = None,
        params: Optional[Dict] = None
    ) -> Tuple[bool, Any]:
        """Make Hetzner DNS API request"""
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
                    error_msg = error.get('error', {}).get('message', response.reason)
                except:
                    error_msg = response.reason
                return False, error_msg
            
            if response.text:
                return True, response.json()
            return True, None
            
        except requests.RequestException as e:
            logger.error(f"Hetzner DNS API request failed: {e}")
            return False, str(e)
    
    def _get_zone(self, domain: str) -> Optional[Dict]:
        """Get zone info for domain"""
        # Check cache
        if domain in self._zone_cache:
            return self._zone_cache[domain]
        
        # Get all zones
        success, result = self._request('GET', '/zones')
        if not success:
            return None
        
        zones = result.get('zones', [])
        
        # Find best matching zone
        domain_parts = domain.split('.')
        for i in range(len(domain_parts) - 1):
            zone_name = '.'.join(domain_parts[i:])
            for zone in zones:
                if zone['name'] == zone_name:
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
        """Create TXT record via Hetzner API"""
        zone = self._get_zone(domain)
        if not zone:
            return False, f"Could not find zone for domain {domain}"
        
        # Hetzner wants relative name (without zone)
        relative_name = self.get_relative_record_name(record_name, zone['name'])
        
        data = {
            'zone_id': zone['id'],
            'type': 'TXT',
            'name': relative_name,
            'value': record_value,
            'ttl': ttl,
        }
        
        success, result = self._request('POST', '/records', data)
        if not success:
            return False, f"Failed to create record: {result}"
        
        record_id = result.get('record', {}).get('id', 'unknown')
        logger.info(f"Hetzner: Created TXT record {record_name} (ID: {record_id})")
        return True, f"Record created successfully (ID: {record_id})"
    
    def delete_txt_record(self, domain: str, record_name: str) -> Tuple[bool, str]:
        """Delete TXT record via Hetzner API"""
        zone = self._get_zone(domain)
        if not zone:
            return False, f"Could not find zone for domain {domain}"
        
        relative_name = self.get_relative_record_name(record_name, zone['name'])
        
        # Get all records for zone
        success, result = self._request('GET', '/records', params={'zone_id': zone['id']})
        if not success:
            return False, f"Failed to list records: {result}"
        
        records = result.get('records', [])
        
        # Find and delete matching TXT records
        deleted = 0
        for record in records:
            if record['type'] == 'TXT' and record['name'] == relative_name:
                success, _ = self._request('DELETE', f'/records/{record["id"]}')
                if success:
                    deleted += 1
        
        if deleted == 0:
            return True, "Record not found (already deleted?)"
        
        logger.info(f"Hetzner: Deleted {deleted} TXT record(s) for {record_name}")
        return True, f"Deleted {deleted} record(s)"
    
    def test_connection(self) -> Tuple[bool, str]:
        """Test Hetzner DNS API connection"""
        success, result = self._request('GET', '/zones')
        if success:
            zones = result.get('zones', [])
            return True, f"Connected successfully. Found {len(zones)} zone(s)."
        return False, f"Connection failed: {result}"
    
    @classmethod
    def get_credential_schema(cls):
        return [
            {'name': 'api_token', 'label': 'API Token', 'type': 'password', 'required': True,
             'help': 'Get at dns.hetzner.com/settings/api-token'},
        ]
