"""
Dynu DNS Provider - Free Dynamic DNS
Uses Dynu REST API v2
https://www.dynu.com/Support/API
"""
import requests
from typing import Tuple, Dict, Any, Optional, List
import logging

from .base import BaseDnsProvider

logger = logging.getLogger(__name__)


class DynuDnsProvider(BaseDnsProvider):
    PROVIDER_TYPE = "dynu"
    PROVIDER_NAME = "Dynu"
    PROVIDER_DESCRIPTION = "Dynu Dynamic DNS API"
    REQUIRED_CREDENTIALS = ["api_key"]
    
    BASE_URL = "https://api.dynu.com/v2"
    
    def _get_headers(self):
        return {
            'API-Key': self.credentials['api_key'],
            'Content-Type': 'application/json',
        }
    
    def _request(self, method, path, data=None):
        try:
            resp = requests.request(method, f"{self.BASE_URL}{path}",
                headers=self._get_headers(), json=data, timeout=30)
            if resp.status_code >= 400:
                return False, resp.text
            return True, resp.json() if resp.text else None
        except requests.RequestException as e:
            logger.error(f"Dynu API error: {e}")
            return False, str(e)
    
    def _get_domain_id(self, domain):
        success, result = self._request('GET', '/dns')
        if not success:
            return None
        for d in result.get('domains', []):
            if domain.endswith(d['name']):
                return d['id'], d['name']
        return None
    
    def create_txt_record(self, domain, record_name, record_value, ttl=300):
        info = self._get_domain_id(domain)
        if not info:
            return False, f"Zone not found for {domain}"
        domain_id, zone = info
        
        node = self.get_relative_record_name(record_name, zone)
        data = {
            'nodeName': node,
            'recordType': 'TXT',
            'textData': record_value,
            'state': True,
            'ttl': ttl
        }
        success, result = self._request('POST', f'/dns/{domain_id}/record', data)
        if not success:
            return False, f"Failed: {result}"
        return True, "Record created"
    
    def delete_txt_record(self, domain, record_name):
        info = self._get_domain_id(domain)
        if not info:
            return False, f"Zone not found for {domain}"
        domain_id, zone = info
        node = self.get_relative_record_name(record_name, zone)
        
        success, result = self._request('GET', f'/dns/{domain_id}/record')
        if not success:
            return False, f"Failed to list records: {result}"
        
        for rec in result.get('dnsRecords', []):
            if rec.get('recordType') == 'TXT' and rec.get('nodeName') == node:
                self._request('DELETE', f'/dns/{domain_id}/record/{rec["id"]}')
                return True, "Record deleted"
        return True, "Record not found (already deleted?)"
    
    def test_connection(self):
        success, result = self._request('GET', '/dns')
        if success:
            domains = result.get('domains', [])
            return True, f"Connected. {len(domains)} domain(s) found"
        return False, f"Connection failed: {result}"
    
    @classmethod
    def get_credential_schema(cls):
        return [
            {'name': 'api_key', 'label': 'API Key', 'type': 'password', 'required': True,
             'help': 'Dynu Control Panel > API Credentials'},
        ]
