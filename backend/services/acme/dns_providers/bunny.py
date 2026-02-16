"""
Bunny DNS Provider
https://docs.bunny.net/reference/dnszonepublic_index
"""
import requests
from typing import Tuple, Dict, Any
import logging

from .base import BaseDnsProvider

logger = logging.getLogger(__name__)


class BunnyDnsProvider(BaseDnsProvider):
    PROVIDER_TYPE = "bunny"
    PROVIDER_NAME = "Bunny"
    PROVIDER_DESCRIPTION = "Bunny.net DNS API"
    REQUIRED_CREDENTIALS = ["api_key"]
    
    BASE_URL = "https://api.bunny.net"
    
    def _get_headers(self):
        return {
            'AccessKey': self.credentials['api_key'],
            'Content-Type': 'application/json',
            'Accept': 'application/json',
        }
    
    def _request(self, method, path, data=None):
        try:
            resp = requests.request(method, f"{self.BASE_URL}{path}",
                headers=self._get_headers(), json=data, timeout=30)
            if resp.status_code >= 400:
                return False, resp.text
            return True, resp.json() if resp.text and resp.status_code != 204 else None
        except requests.RequestException as e:
            logger.error(f"Bunny API error: {e}")
            return False, str(e)
    
    def _find_zone(self, domain):
        success, result = self._request('GET', '/dnszone')
        if not success:
            return None
        for z in result.get('Items', []):
            if domain.endswith(z['Domain']):
                return z['Id'], z['Domain']
        return None
    
    def create_txt_record(self, domain, record_name, record_value, ttl=300):
        info = self._find_zone(domain)
        if not info:
            return False, f"Zone not found for {domain}"
        zone_id, zone = info
        relative = self.get_relative_record_name(record_name, zone)
        data = {'Type': 5, 'Name': relative, 'Value': record_value, 'Ttl': ttl}  # Type 5 = TXT
        success, result = self._request('PUT', f'/dnszone/{zone_id}/records', data)
        if not success:
            return False, f"Failed: {result}"
        return True, "Record created"
    
    def delete_txt_record(self, domain, record_name):
        info = self._find_zone(domain)
        if not info:
            return False, f"Zone not found for {domain}"
        zone_id, zone = info
        relative = self.get_relative_record_name(record_name, zone)
        
        success, result = self._request('GET', f'/dnszone/{zone_id}')
        if not success:
            return False, f"Failed: {result}"
        for rec in result.get('Records', []):
            if rec.get('Type') == 5 and rec.get('Name') == relative:
                self._request('DELETE', f'/dnszone/{zone_id}/records/{rec["Id"]}')
        return True, "Record deleted"
    
    def test_connection(self):
        success, result = self._request('GET', '/dnszone')
        if success:
            zones = [z['Domain'] for z in result.get('Items', [])]
            return True, f"Connected. Zones: {', '.join(zones)}"
        return False, f"Connection failed: {result}"
    
    @classmethod
    def get_credential_schema(cls):
        return [
            {'name': 'api_key', 'label': 'API Key', 'type': 'password', 'required': True,
             'help': 'bunny.net > Account Settings > API Key'},
        ]
