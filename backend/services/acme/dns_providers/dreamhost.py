"""
DreamHost DNS Provider
https://help.dreamhost.com/hc/en-us/articles/217560167-API-overview
"""
import requests
from typing import Tuple, Dict, Any
import logging

from .base import BaseDnsProvider

logger = logging.getLogger(__name__)


class DreamhostDnsProvider(BaseDnsProvider):
    PROVIDER_TYPE = "dreamhost"
    PROVIDER_NAME = "DreamHost"
    PROVIDER_DESCRIPTION = "DreamHost DNS API"
    REQUIRED_CREDENTIALS = ["api_key"]
    
    BASE_URL = "https://api.dreamhost.com"
    
    def _request(self, cmd, params=None):
        p = {'key': self.credentials['api_key'], 'cmd': cmd, 'format': 'json'}
        if params:
            p.update(params)
        try:
            resp = requests.get(self.BASE_URL, params=p, timeout=30)
            if resp.status_code >= 400:
                return False, resp.text
            data = resp.json()
            if data.get('result') == 'success':
                return True, data
            return False, data.get('data', 'Unknown error')
        except requests.RequestException as e:
            logger.error(f"DreamHost API error: {e}")
            return False, str(e)
    
    def create_txt_record(self, domain, record_name, record_value, ttl=300):
        success, result = self._request('dns-add_record', {
            'record': record_name, 'type': 'TXT', 'value': record_value
        })
        if not success:
            return False, f"Failed: {result}"
        return True, "Record created"
    
    def delete_txt_record(self, domain, record_name):
        # First list to find the value
        success, result = self._request('dns-list_records')
        if not success:
            return False, f"Failed: {result}"
        
        for rec in result.get('data', []):
            if rec.get('record') == record_name and rec.get('type') == 'TXT':
                self._request('dns-remove_record', {
                    'record': record_name, 'type': 'TXT', 'value': rec['value']
                })
                return True, "Record deleted"
        return True, "Record not found (already deleted?)"
    
    def test_connection(self):
        success, result = self._request('dns-list_records')
        if success:
            count = len(result.get('data', []))
            return True, f"Connected. {count} DNS record(s) found"
        return False, f"Connection failed: {result}"
    
    @classmethod
    def get_credential_schema(cls):
        return [
            {'name': 'api_key', 'label': 'API Key', 'type': 'password', 'required': True,
             'help': 'panel.dreamhost.com > Web Panel API'},
        ]
