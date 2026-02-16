"""
Checkdomain DNS Provider (Germany)
https://developer.checkdomain.de/reference
"""
import requests
from typing import Tuple, Dict, Any
import logging

from .base import BaseDnsProvider

logger = logging.getLogger(__name__)


class CheckdomainDnsProvider(BaseDnsProvider):
    PROVIDER_TYPE = "checkdomain"
    PROVIDER_NAME = "Checkdomain"
    PROVIDER_DESCRIPTION = "Checkdomain DNS API (Germany)"
    REQUIRED_CREDENTIALS = ["api_token"]
    
    BASE_URL = "https://api.checkdomain.de/v1"
    
    def _get_headers(self):
        return {
            'Authorization': f'Bearer {self.credentials["api_token"]}',
            'Content-Type': 'application/json',
        }
    
    def _request(self, method, path, data=None):
        try:
            resp = requests.request(method, f"{self.BASE_URL}{path}",
                headers=self._get_headers(), json=data, timeout=30)
            if resp.status_code >= 400:
                return False, resp.text
            return True, resp.json() if resp.text and resp.status_code not in (201, 204) else None
        except requests.RequestException as e:
            logger.error(f"Checkdomain API error: {e}")
            return False, str(e)
    
    def _find_domain(self, domain):
        success, result = self._request('GET', '/domains')
        if not success:
            return None
        for d in result.get('_embedded', {}).get('domains', []):
            if domain.endswith(d.get('name', '')):
                return d['id'], d['name']
        return None
    
    def create_txt_record(self, domain, record_name, record_value, ttl=300):
        info = self._find_domain(domain)
        if not info:
            return False, f"Domain not found for {domain}"
        domain_id, zone = info
        relative = self.get_relative_record_name(record_name, zone)
        data = {'name': relative, 'type': 'TXT', 'value': record_value, 'ttl': ttl}
        success, result = self._request('POST', f'/domains/{domain_id}/nameservers/records', data)
        if not success:
            return False, f"Failed: {result}"
        return True, "Record created"
    
    def delete_txt_record(self, domain, record_name):
        info = self._find_domain(domain)
        if not info:
            return False, f"Domain not found for {domain}"
        domain_id, zone = info
        relative = self.get_relative_record_name(record_name, zone)
        
        success, result = self._request('GET', f'/domains/{domain_id}/nameservers/records')
        if not success:
            return False, f"Failed: {result}"
        for rec in result.get('_embedded', {}).get('records', []):
            if rec.get('type') == 'TXT' and rec.get('name') == relative:
                self._request('DELETE', f'/domains/{domain_id}/nameservers/records/{rec["id"]}')
        return True, "Record deleted"
    
    def test_connection(self):
        success, result = self._request('GET', '/domains')
        if success:
            return True, "Connected successfully"
        return False, f"Connection failed: {result}"
    
    @classmethod
    def get_credential_schema(cls):
        return [
            {'name': 'api_token', 'label': 'API Token', 'type': 'password', 'required': True,
             'help': 'checkdomain.de > API Access'},
        ]
