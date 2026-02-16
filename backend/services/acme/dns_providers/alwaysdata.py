"""
Alwaysdata DNS Provider (France)
https://help.alwaysdata.com/en/api/
"""
import requests
from typing import Tuple, Dict, Any
import logging

from .base import BaseDnsProvider

logger = logging.getLogger(__name__)


class AlwaysdataDnsProvider(BaseDnsProvider):
    PROVIDER_TYPE = "alwaysdata"
    PROVIDER_NAME = "Alwaysdata"
    PROVIDER_DESCRIPTION = "Alwaysdata DNS API (France)"
    REQUIRED_CREDENTIALS = ["api_key", "account"]
    
    BASE_URL = "https://api.alwaysdata.com/v1"
    
    def _request(self, method, path, data=None):
        try:
            resp = requests.request(method, f"{self.BASE_URL}{path}",
                auth=(self.credentials['api_key'], ''),
                json=data, timeout=30, headers={'Content-Type': 'application/json'})
            if resp.status_code >= 400:
                return False, resp.text
            return True, resp.json() if resp.text and resp.status_code not in (201, 204) else None
        except requests.RequestException as e:
            logger.error(f"Alwaysdata API error: {e}")
            return False, str(e)
    
    def _find_domain(self, domain):
        success, result = self._request('GET', '/domain/')
        if not success:
            return None
        for d in result or []:
            if domain.endswith(d.get('name', '')):
                return d['id'], d['name']
        return None
    
    def create_txt_record(self, domain, record_name, record_value, ttl=300):
        info = self._find_domain(domain)
        if not info:
            return False, f"Domain not found for {domain}"
        domain_id, zone = info
        data = {
            'domain': domain_id, 'type': 'TXT', 'name': record_name + '.',
            'value': f'"{record_value}"', 'ttl': ttl
        }
        success, result = self._request('POST', '/record/', data)
        if not success:
            return False, f"Failed: {result}"
        return True, "Record created"
    
    def delete_txt_record(self, domain, record_name):
        success, result = self._request('GET', f'/record/?name={record_name}.&type=TXT')
        if not success:
            return False, f"Failed: {result}"
        for rec in result or []:
            self._request('DELETE', f'/record/{rec["id"]}/')
        return True, "Record deleted"
    
    def test_connection(self):
        success, result = self._request('GET', '/domain/')
        if success:
            return True, "Connected successfully"
        return False, f"Connection failed: {result}"
    
    @classmethod
    def get_credential_schema(cls):
        return [
            {'name': 'api_key', 'label': 'API Key', 'type': 'password', 'required': True,
             'help': 'admin.alwaysdata.com > Profile > API Keys'},
            {'name': 'account', 'label': 'Account Name', 'type': 'text', 'required': True,
             'help': 'Your Alwaysdata account name'},
        ]
