"""
Hetzner DNS Provider - Cloud API
Uses Hetzner Cloud API (api.hetzner.cloud) for DNS record management
https://docs.hetzner.cloud
"""
import requests
from typing import Tuple, Dict, Any, Optional
import logging

from .base import BaseDnsProvider

logger = logging.getLogger(__name__)


class HetznerDnsProvider(BaseDnsProvider):
    """
    Hetzner DNS Provider using Cloud API.
    
    Required credentials:
    - api_token: Hetzner Cloud API Token
    
    Get token at: console.hetzner.cloud > Project > Security > API Tokens
    """
    
    PROVIDER_TYPE = "hetzner"
    PROVIDER_NAME = "Hetzner"
    PROVIDER_DESCRIPTION = "Hetzner Cloud DNS API (Germany)"
    REQUIRED_CREDENTIALS = ["api_token"]
    
    BASE_URL = "https://api.hetzner.cloud/v1"
    
    def __init__(self, credentials: Dict[str, Any]):
        super().__init__(credentials)
        self._zone_cache: Dict[str, Dict] = {}
    
    def _get_headers(self) -> Dict[str, str]:
        return {
            'Authorization': f'Bearer {self.credentials["api_token"]}',
            'Content-Type': 'application/json',
        }
    
    def _request(
        self, 
        method: str, 
        path: str, 
        data: Optional[Dict] = None,
    ) -> Tuple[bool, Any]:
        """Make Hetzner Cloud API request"""
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
                    error_msg = error.get('error', {}).get('message', response.reason)
                except:
                    error_msg = response.reason
                return False, error_msg
            
            if response.text:
                return True, response.json()
            return True, None
            
        except requests.RequestException as e:
            logger.error(f"Hetzner Cloud API request failed: {e}")
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
        
        # Find best matching zone (longest suffix match)
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
        """Create TXT record via Hetzner Cloud API"""
        zone = self._get_zone(domain)
        if not zone:
            return False, f"Could not find zone for domain {domain}"
        
        zone_id = zone['id']
        
        # Get relative name (without zone suffix)
        relative_name = self.get_relative_record_name(record_name, zone['name'])
        
        # Cloud API requires value to be quoted for TXT records
        quoted_value = f'"{record_value}"'
        
        # First check if rrset already exists
        success, result = self._request('GET', f'/zones/{zone_id}/rrsets/{relative_name}/TXT')
        
        if success and result.get('rrset'):
            # RRset exists, add record to it via PATCH
            existing_records = result['rrset'].get('records', [])
            existing_records.append({'value': quoted_value})
            
            data = {
                'records': existing_records,
                'ttl': ttl,
            }
            success, result = self._request('PATCH', f'/zones/{zone_id}/rrsets/{relative_name}/TXT', data)
        else:
            # Create new rrset
            data = {
                'name': relative_name,
                'type': 'TXT',
                'ttl': ttl,
                'records': [{'value': quoted_value}],
            }
            success, result = self._request('POST', f'/zones/{zone_id}/rrsets', data)
        
        if not success:
            return False, f"Failed to create record: {result}"
        
        logger.info(f"Hetzner: Created TXT record {record_name}")
        return True, f"Record created successfully"
    
    def delete_txt_record(self, domain: str, record_name: str) -> Tuple[bool, str]:
        """Delete TXT record via Hetzner Cloud API"""
        zone = self._get_zone(domain)
        if not zone:
            return False, f"Could not find zone for domain {domain}"
        
        zone_id = zone['id']
        relative_name = self.get_relative_record_name(record_name, zone['name'])
        
        # Delete the entire TXT rrset for this name
        success, result = self._request('DELETE', f'/zones/{zone_id}/rrsets/{relative_name}/TXT')
        
        if not success:
            if 'not found' in str(result).lower():
                return True, "Record not found (already deleted?)"
            return False, f"Failed to delete record: {result}"
        
        logger.info(f"Hetzner: Deleted TXT record {record_name}")
        return True, "Record deleted successfully"
    
    def test_connection(self) -> Tuple[bool, str]:
        """Test Hetzner Cloud API connection"""
        success, result = self._request('GET', '/zones')
        if success:
            zones = result.get('zones', [])
            zone_names = [z['name'] for z in zones]
            return True, f"Connected successfully. Found {len(zones)} zone(s): {', '.join(zone_names)}"
        return False, f"Connection failed: {result}"
    
    @classmethod
    def get_credential_schema(cls):
        return [
            {'name': 'api_token', 'label': 'API Token', 'type': 'password', 'required': True,
             'help': 'console.hetzner.cloud > Project > Security > API Tokens'},
        ]
