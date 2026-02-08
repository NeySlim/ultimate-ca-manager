"""
Cloudflare DNS Provider
Uses Cloudflare API v4 for DNS record management
https://developers.cloudflare.com/api/
"""
import requests
from typing import Tuple, Dict, Any, Optional, List
import logging

from .base import BaseDnsProvider

logger = logging.getLogger(__name__)


class CloudflareDnsProvider(BaseDnsProvider):
    """
    Cloudflare DNS Provider using API v4.
    
    Required credentials:
    - api_token: Cloudflare API Token (recommended)
    
    OR (legacy, less secure):
    - api_key: Global API Key
    - email: Cloudflare account email
    
    Get API Token at: https://dash.cloudflare.com/profile/api-tokens
    Required permissions: Zone:DNS:Edit
    """
    
    PROVIDER_TYPE = "cloudflare"
    PROVIDER_NAME = "Cloudflare"
    PROVIDER_DESCRIPTION = "Cloudflare DNS API"
    REQUIRED_CREDENTIALS = ["api_token"]  # We'll handle legacy auth separately
    OPTIONAL_CREDENTIALS = ["api_key", "email"]
    
    BASE_URL = "https://api.cloudflare.com/client/v4"
    
    def __init__(self, credentials: Dict[str, Any]):
        # Custom validation - either api_token OR (api_key + email)
        self.credentials = credentials or {}
        self.use_token = bool(credentials.get('api_token'))
        
        if not self.use_token:
            if not credentials.get('api_key') or not credentials.get('email'):
                raise ValueError("Either api_token OR both api_key and email are required")
        
        self._zone_cache: Dict[str, str] = {}
    
    def _get_headers(self) -> Dict[str, str]:
        """Get authentication headers"""
        if self.use_token:
            return {
                'Authorization': f"Bearer {self.credentials['api_token']}",
                'Content-Type': 'application/json',
            }
        else:
            return {
                'X-Auth-Email': self.credentials['email'],
                'X-Auth-Key': self.credentials['api_key'],
                'Content-Type': 'application/json',
            }
    
    def _request(
        self, 
        method: str, 
        path: str, 
        data: Optional[Dict] = None,
        params: Optional[Dict] = None
    ) -> Tuple[bool, Any]:
        """Make Cloudflare API request"""
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
            
            result = response.json()
            
            if not result.get('success', False):
                errors = result.get('errors', [])
                error_msg = errors[0].get('message', 'Unknown error') if errors else 'Unknown error'
                return False, error_msg
            
            return True, result.get('result')
            
        except requests.RequestException as e:
            logger.error(f"Cloudflare API request failed: {e}")
            return False, str(e)
    
    def _get_zone_id(self, domain: str) -> Optional[str]:
        """Get zone ID for domain"""
        # Check cache
        if domain in self._zone_cache:
            return self._zone_cache[domain]
        
        # Try to find zone
        domain_parts = domain.split('.')
        for i in range(len(domain_parts) - 1):
            zone_name = '.'.join(domain_parts[i:])
            
            success, zones = self._request('GET', '/zones', params={'name': zone_name})
            if success and zones:
                zone_id = zones[0]['id']
                self._zone_cache[domain] = zone_id
                return zone_id
        
        return None
    
    def create_txt_record(
        self, 
        domain: str, 
        record_name: str, 
        record_value: str, 
        ttl: int = 300
    ) -> Tuple[bool, str]:
        """Create TXT record via Cloudflare API"""
        zone_id = self._get_zone_id(domain)
        if not zone_id:
            return False, f"Could not find zone for domain {domain}"
        
        data = {
            'type': 'TXT',
            'name': record_name,
            'content': record_value,
            'ttl': ttl if ttl > 0 else 1,  # 1 = automatic
        }
        
        success, result = self._request('POST', f'/zones/{zone_id}/dns_records', data)
        if not success:
            return False, f"Failed to create record: {result}"
        
        record_id = result.get('id', 'unknown')
        logger.info(f"Cloudflare: Created TXT record {record_name} (ID: {record_id})")
        return True, f"Record created successfully (ID: {record_id})"
    
    def delete_txt_record(self, domain: str, record_name: str) -> Tuple[bool, str]:
        """Delete TXT record via Cloudflare API"""
        zone_id = self._get_zone_id(domain)
        if not zone_id:
            return False, f"Could not find zone for domain {domain}"
        
        # Find records matching name and type
        success, records = self._request(
            'GET', 
            f'/zones/{zone_id}/dns_records',
            params={'type': 'TXT', 'name': record_name}
        )
        
        if not success:
            return False, f"Failed to list records: {records}"
        
        if not records:
            return True, "Record not found (already deleted?)"
        
        # Delete all matching records
        deleted = 0
        for record in records:
            success, _ = self._request('DELETE', f'/zones/{zone_id}/dns_records/{record["id"]}')
            if success:
                deleted += 1
        
        logger.info(f"Cloudflare: Deleted {deleted} TXT record(s) for {record_name}")
        return True, f"Deleted {deleted} record(s)"
    
    def test_connection(self) -> Tuple[bool, str]:
        """Test Cloudflare API connection"""
        if self.use_token:
            success, result = self._request('GET', '/user/tokens/verify')
            if success:
                return True, "API Token verified successfully"
            return False, f"Token verification failed: {result}"
        else:
            success, result = self._request('GET', '/user')
            if success:
                email = result.get('email', 'unknown')
                return True, f"Connected as {email}"
            return False, f"Connection failed: {result}"
    
    @classmethod
    def get_credential_schema(cls):
        return [
            {'name': 'api_token', 'label': 'API Token', 'type': 'password', 'required': False,
             'help': 'Recommended. Create at dash.cloudflare.com/profile/api-tokens'},
            {'name': 'api_key', 'label': 'Global API Key (legacy)', 'type': 'password', 'required': False,
             'help': 'Use only if not using API Token'},
            {'name': 'email', 'label': 'Email (legacy)', 'type': 'text', 'required': False,
             'help': 'Required with Global API Key'},
        ]
