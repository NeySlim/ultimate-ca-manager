"""
Domeneshop DNS Provider (Norway)
https://api.domeneshop.no/docs/
"""
import requests
from typing import Tuple, Dict, Any
import logging

from .base import BaseDnsProvider

logger = logging.getLogger(__name__)


class DomeneshopDnsProvider(BaseDnsProvider):
    PROVIDER_TYPE = "domeneshop"
    PROVIDER_NAME = "Domeneshop"
    PROVIDER_DESCRIPTION = "Domeneshop DNS API (Norway)"
    REQUIRED_CREDENTIALS = ["api_token", "api_secret"]
    
    BASE_URL = "https://api.domeneshop.no/v0"
    
    def _request(self, method, path, data=None):
        try:
            resp = requests.request(method, f"{self.BASE_URL}{path}",
                auth=(self.credentials['api_token'], self.credentials['api_secret']),
                json=data, timeout=30, headers={'Content-Type': 'application/json'})
            if resp.status_code >= 400:
                return False, resp.text
            return True, resp.json() if resp.text and resp.status_code != 204 else None
        except requests.RequestException as e:
            logger.error(f"Domeneshop API error: {e}")
            return False, str(e)
    
    def _find_domain(self, domain):
        success, result = self._request('GET', '/domains')
        if not success:
            return None
        for d in result or []:
            if domain.endswith(d['domain']):
                return d['id'], d['domain']
        return None
    
    def create_txt_record(self, domain, record_name, record_value, ttl=300):
        info = self._find_domain(domain)
        if not info:
            return False, f"Domain not found for {domain}"
        domain_id, zone = info
        relative = self.get_relative_record_name(record_name, zone)
        data = {'host': relative, 'type': 'TXT', 'data': f'"{record_value}"', 'ttl': ttl}
        success, result = self._request('POST', f'/domains/{domain_id}/dns', data)
        if not success:
            return False, f"Failed: {result}"
        return True, "Record created"
    
    def delete_txt_record(self, domain, record_name):
        info = self._find_domain(domain)
        if not info:
            return False, f"Domain not found for {domain}"
        domain_id, zone = info
        relative = self.get_relative_record_name(record_name, zone)
        
        success, result = self._request('GET', f'/domains/{domain_id}/dns')
        if not success:
            return False, f"Failed: {result}"
        for rec in result or []:
            if rec.get('type') == 'TXT' and rec.get('host') == relative:
                self._request('DELETE', f'/domains/{domain_id}/dns/{rec["id"]}')
        return True, "Record deleted"
    
    def test_connection(self):
        success, result = self._request('GET', '/domains')
        if success:
            domains = [d['domain'] for d in result or []]
            return True, f"Connected. Domains: {', '.join(domains)}"
        return False, f"Connection failed: {result}"
    
    @classmethod
    def get_credential_schema(cls):
        return [
            {'name': 'api_token', 'label': 'API Token', 'type': 'text', 'required': True,
             'help': 'domeneshop.no > My Pages > API'},
            {'name': 'api_secret', 'label': 'API Secret', 'type': 'password', 'required': True,
             'help': 'API Secret from Domeneshop'},
        ]
