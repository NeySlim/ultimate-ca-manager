"""
RcodeZero DNS Provider
Uses RcodeZero Anycast DNS API
https://my.rcodezero.at/api-doc
"""
import requests
from typing import Tuple, Dict, Any, Optional
import logging

from .base import BaseDnsProvider

logger = logging.getLogger(__name__)


class RcodeZeroDnsProvider(BaseDnsProvider):
    PROVIDER_TYPE = "rcodezero"
    PROVIDER_NAME = "RcodeZero"
    PROVIDER_DESCRIPTION = "RcodeZero Anycast DNS API (Austria)"
    REQUIRED_CREDENTIALS = ["api_token"]
    
    BASE_URL = "https://my.rcodezero.at/api/v1"
    
    def _get_headers(self) -> Dict[str, str]:
        return {
            'Authorization': f'Bearer {self.credentials["api_token"]}',
            'Content-Type': 'application/json',
        }
    
    def _request(self, method: str, path: str, data: Optional[Any] = None) -> Tuple[bool, Any]:
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
        success, result = self._request('GET', '/zones')
        if not success:
            return None
        zones = result.get('data', []) if isinstance(result, dict) else result
        domain_parts = domain.split('.')
        for i in range(len(domain_parts) - 1):
            name = '.'.join(domain_parts[i:])
            for z in zones:
                zone_name = z.get('domain', z.get('name', ''))
                if zone_name.rstrip('.') == name:
                    return zone_name
        return None
    
    def create_txt_record(self, domain: str, record_name: str, record_value: str, ttl: int = 300) -> Tuple[bool, str]:
        zone = self._find_zone(domain)
        if not zone:
            return False, f"Could not find zone for {domain}"
        fqdn = record_name if record_name.endswith('.') else record_name + '.'
        data = [{'name': fqdn, 'type': 'TXT', 'ttl': ttl, 'records': [f'"{record_value}"'], 'changetype': 'ADD'}]
        success, result = self._request('PATCH', f'/zones/{zone}/rrsets', data)
        if not success:
            return False, f"Failed to create record: {result}"
        return True, "Record created successfully"
    
    def delete_txt_record(self, domain: str, record_name: str) -> Tuple[bool, str]:
        zone = self._find_zone(domain)
        if not zone:
            return False, f"Could not find zone for {domain}"
        fqdn = record_name if record_name.endswith('.') else record_name + '.'
        data = [{'name': fqdn, 'type': 'TXT', 'changetype': 'DELETE'}]
        success, result = self._request('PATCH', f'/zones/{zone}/rrsets', data)
        if not success:
            return False, f"Failed to delete record: {result}"
        return True, "Record deleted successfully"
    
    def test_connection(self) -> Tuple[bool, str]:
        success, result = self._request('GET', '/zones')
        if success:
            zones = result.get('data', []) if isinstance(result, dict) else result
            return True, f"Connected. Found {len(zones)} zone(s)"
        return False, f"Connection failed: {result}"
    
    @classmethod
    def get_credential_schema(cls):
        return [
            {'name': 'api_token', 'label': 'API Token', 'type': 'password', 'required': True,
             'help': 'my.rcodezero.at > API Tokens'},
        ]
