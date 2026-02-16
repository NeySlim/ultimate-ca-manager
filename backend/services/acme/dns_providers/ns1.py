"""
NS1 DNS Provider
Uses NS1 v2 REST API for DNS record management
https://ns1.com/api
"""
import requests
from typing import Tuple, Dict, Any, Optional
import logging

from .base import BaseDnsProvider

logger = logging.getLogger(__name__)


class Ns1DnsProvider(BaseDnsProvider):
    PROVIDER_TYPE = "ns1"
    PROVIDER_NAME = "NS1"
    PROVIDER_DESCRIPTION = "NS1 Managed DNS API"
    REQUIRED_CREDENTIALS = ["api_key"]
    
    BASE_URL = "https://api.nsone.net/v1"
    
    def _get_headers(self) -> Dict[str, str]:
        return {'X-NSONE-Key': self.credentials['api_key'], 'Content-Type': 'application/json'}
    
    def _request(self, method: str, path: str, data: Optional[Dict] = None) -> Tuple[bool, Any]:
        url = f"{self.BASE_URL}{path}"
        try:
            resp = requests.request(method=method, url=url, headers=self._get_headers(), json=data, timeout=30)
            if resp.status_code >= 400:
                try:
                    error_msg = resp.json().get('message', resp.reason)
                except Exception:
                    error_msg = resp.reason
                return False, error_msg
            return True, resp.json() if resp.text else None
        except requests.RequestException as e:
            return False, str(e)
    
    def _find_zone(self, domain: str) -> Optional[str]:
        success, zones = self._request('GET', '/zones')
        if not success:
            return None
        domain_parts = domain.split('.')
        for i in range(len(domain_parts) - 1):
            zone_name = '.'.join(domain_parts[i:])
            for z in zones:
                if z['zone'] == zone_name:
                    return zone_name
        return None
    
    def create_txt_record(self, domain: str, record_name: str, record_value: str, ttl: int = 300) -> Tuple[bool, str]:
        zone = self._find_zone(domain)
        if not zone:
            return False, f"Could not find zone for {domain}"
        data = {'zone': zone, 'domain': record_name, 'type': 'TXT', 'ttl': ttl,
                'answers': [{'answer': [record_value]}]}
        success, result = self._request('PUT', f'/zones/{zone}/{record_name}/TXT', data)
        if not success:
            return False, f"Failed to create record: {result}"
        return True, "Record created successfully"
    
    def delete_txt_record(self, domain: str, record_name: str) -> Tuple[bool, str]:
        zone = self._find_zone(domain)
        if not zone:
            return False, f"Could not find zone for {domain}"
        success, result = self._request('DELETE', f'/zones/{zone}/{record_name}/TXT')
        if not success:
            if 'not found' in str(result).lower():
                return True, "Record not found (already deleted?)"
            return False, f"Failed to delete record: {result}"
        return True, "Record deleted successfully"
    
    def test_connection(self) -> Tuple[bool, str]:
        success, zones = self._request('GET', '/zones')
        if success:
            names = [z['zone'] for z in zones]
            return True, f"Connected. Found {len(zones)} zone(s): {', '.join(names)}"
        return False, f"Connection failed: {zones}"
    
    @classmethod
    def get_credential_schema(cls):
        return [
            {'name': 'api_key', 'label': 'API Key', 'type': 'password', 'required': True,
             'help': 'my.nsone.net > Account Settings > API Keys'},
        ]
