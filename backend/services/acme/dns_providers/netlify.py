"""
Netlify DNS Provider
Uses Netlify API for DNS record management
https://docs.netlify.com/api/get-started/
"""
import requests
from typing import Tuple, Dict, Any, Optional
import logging

from .base import BaseDnsProvider

logger = logging.getLogger(__name__)


class NetlifyDnsProvider(BaseDnsProvider):
    PROVIDER_TYPE = "netlify"
    PROVIDER_NAME = "Netlify"
    PROVIDER_DESCRIPTION = "Netlify DNS API"
    REQUIRED_CREDENTIALS = ["api_token"]
    
    BASE_URL = "https://api.netlify.com/api/v1"
    
    def __init__(self, credentials: Dict[str, Any]):
        super().__init__(credentials)
        self._zone_cache: Dict[str, str] = {}
    
    def _get_headers(self) -> Dict[str, str]:
        return {
            'Authorization': f'Bearer {self.credentials["api_token"]}',
            'Content-Type': 'application/json',
        }
    
    def _request(self, method: str, path: str, data: Optional[Dict] = None) -> Tuple[bool, Any]:
        url = f"{self.BASE_URL}{path}"
        try:
            response = requests.request(method=method, url=url, headers=self._get_headers(), json=data, timeout=30)
            if response.status_code >= 400:
                try:
                    error_msg = response.json().get('message', response.reason)
                except Exception:
                    error_msg = response.reason
                return False, error_msg
            if response.text:
                return True, response.json()
            return True, None
        except requests.RequestException as e:
            logger.error("Netlify API request failed: %s", e)
            return False, str(e)
    
    def _get_zone_id(self, domain: str) -> Optional[str]:
        if domain in self._zone_cache:
            return self._zone_cache[domain]
        success, zones = self._request('GET', '/dns_zones')
        if not success:
            return None
        domain_parts = domain.split('.')
        for i in range(len(domain_parts) - 1):
            zone_name = '.'.join(domain_parts[i:])
            for zone in zones:
                if zone['name'] == zone_name:
                    self._zone_cache[domain] = zone['id']
                    return zone['id']
        return None
    
    def create_txt_record(self, domain: str, record_name: str, record_value: str, ttl: int = 300) -> Tuple[bool, str]:
        zone_id = self._get_zone_id(domain)
        if not zone_id:
            return False, f"Could not find zone for domain {domain}"
        data = {'type': 'TXT', 'hostname': record_name, 'value': record_value, 'ttl': ttl}
        success, result = self._request('POST', f'/dns_zones/{zone_id}/dns_records', data)
        if not success:
            return False, f"Failed to create record: {result}"
        logger.info("Netlify: Created TXT record %s", record_name)
        return True, "Record created successfully"
    
    def delete_txt_record(self, domain: str, record_name: str) -> Tuple[bool, str]:
        zone_id = self._get_zone_id(domain)
        if not zone_id:
            return False, f"Could not find zone for domain {domain}"
        success, records = self._request('GET', f'/dns_zones/{zone_id}/dns_records')
        if not success:
            return False, f"Failed to list records: {records}"
        for rec in records:
            if rec.get('type') == 'TXT' and rec.get('hostname') == record_name:
                ok, res = self._request('DELETE', f'/dns_zones/{zone_id}/dns_records/{rec["id"]}')
                if not ok:
                    return False, f"Failed to delete record: {res}"
        logger.info("Netlify: Deleted TXT record %s", record_name)
        return True, "Record deleted successfully"
    
    def test_connection(self) -> Tuple[bool, str]:
        success, zones = self._request('GET', '/dns_zones')
        if success:
            names = [z['name'] for z in zones]
            return True, f"Connected. Found {len(zones)} zone(s): {', '.join(names)}"
        return False, f"Connection failed: {zones}"
    
    @classmethod
    def get_credential_schema(cls):
        return [
            {'name': 'api_token', 'label': 'Personal Access Token', 'type': 'password', 'required': True,
             'help': 'app.netlify.com > User Settings > Applications > Personal access tokens'},
        ]
