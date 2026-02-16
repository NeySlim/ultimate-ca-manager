"""
Porkbun DNS Provider
https://porkbun.com/api/json/v3/documentation
"""
import requests
from typing import Tuple, Dict, Any
import logging

from .base import BaseDnsProvider

logger = logging.getLogger(__name__)


class PorkbunDnsProvider(BaseDnsProvider):
    PROVIDER_TYPE = "porkbun"
    PROVIDER_NAME = "Porkbun"
    PROVIDER_DESCRIPTION = "Porkbun DNS API"
    REQUIRED_CREDENTIALS = ["api_key", "secret_api_key"]
    
    BASE_URL = "https://api.porkbun.com/api/json/v3"
    
    def _auth_body(self, extra=None):
        body = {
            'apikey': self.credentials['api_key'],
            'secretapikey': self.credentials['secret_api_key'],
        }
        if extra:
            body.update(extra)
        return body
    
    def _request(self, path, data=None):
        body = self._auth_body(data)
        try:
            resp = requests.post(f"{self.BASE_URL}{path}", json=body, timeout=30)
            result = resp.json()
            if result.get('status') == 'SUCCESS':
                return True, result
            return False, result.get('message', 'Unknown error')
        except requests.RequestException as e:
            logger.error(f"Porkbun API error: {e}")
            return False, str(e)
    
    def create_txt_record(self, domain, record_name, record_value, ttl=300):
        zone = self.get_zone_for_domain(domain)
        relative = self.get_relative_record_name(record_name, zone)
        success, result = self._request(f'/dns/create/{zone}', {
            'name': relative, 'type': 'TXT', 'content': record_value, 'ttl': str(ttl)
        })
        if not success:
            return False, f"Failed: {result}"
        return True, "Record created"
    
    def delete_txt_record(self, domain, record_name):
        zone = self.get_zone_for_domain(domain)
        relative = self.get_relative_record_name(record_name, zone)
        
        success, result = self._request(f'/dns/retrieveByNameType/{zone}/TXT/{relative}')
        if success:
            for rec in result.get('records', []):
                self._request(f'/dns/delete/{zone}/{rec["id"]}')
        return True, "Record deleted"
    
    def test_connection(self):
        success, result = self._request('/ping')
        if success:
            return True, "Connected successfully"
        return False, f"Connection failed: {result}"
    
    @classmethod
    def get_credential_schema(cls):
        return [
            {'name': 'api_key', 'label': 'API Key', 'type': 'password', 'required': True,
             'help': 'porkbun.com > Account > API Access'},
            {'name': 'secret_api_key', 'label': 'Secret API Key', 'type': 'password', 'required': True,
             'help': 'Porkbun Secret API Key'},
        ]
