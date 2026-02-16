"""
DNSimple DNS Provider
https://developer.dnsimple.com/v2/
"""
import requests
from typing import Tuple, Dict, Any, Optional
import logging

from .base import BaseDnsProvider

logger = logging.getLogger(__name__)


class DnsimpleDnsProvider(BaseDnsProvider):
    PROVIDER_TYPE = "dnsimple"
    PROVIDER_NAME = "DNSimple"
    PROVIDER_DESCRIPTION = "DNSimple DNS API"
    REQUIRED_CREDENTIALS = ["api_token", "account_id"]
    
    BASE_URL = "https://api.dnsimple.com/v2"
    
    def _get_headers(self):
        return {
            'Authorization': f'Bearer {self.credentials["api_token"]}',
            'Content-Type': 'application/json',
            'Accept': 'application/json',
        }
    
    def _request(self, method, path, data=None):
        acct = self.credentials['account_id']
        try:
            resp = requests.request(method, f"{self.BASE_URL}/{acct}{path}",
                headers=self._get_headers(), json=data, timeout=30)
            if resp.status_code >= 400:
                return False, resp.text
            return True, resp.json() if resp.text else None
        except requests.RequestException as e:
            logger.error(f"DNSimple API error: {e}")
            return False, str(e)
    
    def _find_zone(self, domain):
        success, result = self._request('GET', '/zones')
        if not success:
            return None
        for z in result.get('data', []):
            if domain.endswith(z['name']):
                return z['name']
        return None
    
    def create_txt_record(self, domain, record_name, record_value, ttl=300):
        zone = self._find_zone(domain)
        if not zone:
            return False, f"Zone not found for {domain}"
        relative = self.get_relative_record_name(record_name, zone)
        data = {'name': relative, 'type': 'TXT', 'content': record_value, 'ttl': ttl}
        success, result = self._request('POST', f'/zones/{zone}/records', data)
        if not success:
            return False, f"Failed: {result}"
        return True, "Record created"
    
    def delete_txt_record(self, domain, record_name):
        zone = self._find_zone(domain)
        if not zone:
            return False, f"Zone not found for {domain}"
        relative = self.get_relative_record_name(record_name, zone)
        
        success, result = self._request('GET', f'/zones/{zone}/records?type=TXT&name={relative}')
        if not success:
            return False, f"Failed: {result}"
        for rec in result.get('data', []):
            self._request('DELETE', f'/zones/{zone}/records/{rec["id"]}')
        return True, "Record deleted"
    
    def test_connection(self):
        success, result = self._request('GET', '/zones')
        if success:
            zones = [z['name'] for z in result.get('data', [])]
            return True, f"Connected. Zones: {', '.join(zones)}"
        return False, f"Connection failed: {result}"
    
    @classmethod
    def get_credential_schema(cls):
        return [
            {'name': 'api_token', 'label': 'API Token', 'type': 'password', 'required': True,
             'help': 'dnsimple.com > Account > Access Tokens'},
            {'name': 'account_id', 'label': 'Account ID', 'type': 'text', 'required': True,
             'help': 'Numeric account ID from URL or API'},
        ]
