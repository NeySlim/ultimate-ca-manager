"""
EasyDNS Provider
https://docs.sandbox.rest.easydns.net/
"""
import requests
from typing import Tuple, Dict, Any, Optional
import logging

from .base import BaseDnsProvider

logger = logging.getLogger(__name__)


class EasyDnsDnsProvider(BaseDnsProvider):
    PROVIDER_TYPE = "easydns"
    PROVIDER_NAME = "EasyDNS"
    PROVIDER_DESCRIPTION = "EasyDNS REST API"
    REQUIRED_CREDENTIALS = ["api_token", "api_key"]
    
    BASE_URL = "https://rest.easydns.net"
    
    def _get_headers(self):
        return {'Content-Type': 'application/json', 'Accept': 'application/json'}
    
    def _auth_params(self):
        return f"?_key={self.credentials['api_key']}&_token={self.credentials['api_token']}&_format=json"
    
    def _request(self, method, path, data=None):
        url = f"{self.BASE_URL}{path}{self._auth_params()}"
        try:
            resp = requests.request(method, url, json=data, timeout=30)
            if resp.status_code >= 400:
                return False, resp.text
            return True, resp.json() if resp.text else None
        except requests.RequestException as e:
            logger.error(f"EasyDNS API error: {e}")
            return False, str(e)
    
    def _find_zone(self, domain):
        parts = domain.split('.')
        for i in range(len(parts) - 1):
            zone = '.'.join(parts[i:])
            success, _ = self._request('GET', f'/zones/records/all/{zone}')
            if success:
                return zone
        return None
    
    def create_txt_record(self, domain, record_name, record_value, ttl=300):
        zone = self._find_zone(domain)
        if not zone:
            return False, f"Zone not found for {domain}"
        relative = self.get_relative_record_name(record_name, zone)
        data = {'host': relative, 'type': 'TXT', 'rdata': record_value, 'ttl': str(ttl)}
        success, result = self._request('PUT', f'/zones/records/add/{zone}/TXT', data)
        if not success:
            return False, f"Failed: {result}"
        return True, "Record created"
    
    def delete_txt_record(self, domain, record_name):
        zone = self._find_zone(domain)
        if not zone:
            return False, f"Zone not found for {domain}"
        relative = self.get_relative_record_name(record_name, zone)
        
        success, result = self._request('GET', f'/zones/records/all/{zone}')
        if not success:
            return False, f"Failed: {result}"
        for rec in result.get('data', []):
            if rec.get('type') == 'TXT' and rec.get('host') == relative:
                self._request('DELETE', f'/zones/records/{zone}/{rec["id"]}')
        return True, "Record deleted"
    
    def test_connection(self):
        success, result = self._request('GET', '/domain/list')
        if success:
            return True, "Connected successfully"
        return False, f"Connection failed: {result}"
    
    @classmethod
    def get_credential_schema(cls):
        return [
            {'name': 'api_token', 'label': 'API Token', 'type': 'password', 'required': True,
             'help': 'cp.easydns.com > User > API Keys'},
            {'name': 'api_key', 'label': 'API Key', 'type': 'text', 'required': True,
             'help': 'EasyDNS API Key'},
        ]
