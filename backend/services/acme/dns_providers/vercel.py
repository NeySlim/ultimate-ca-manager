"""
Vercel DNS Provider
https://vercel.com/docs/rest-api/endpoints/dns
"""
import requests
from typing import Tuple, Dict, Any
import logging

from .base import BaseDnsProvider

logger = logging.getLogger(__name__)


class VercelDnsProvider(BaseDnsProvider):
    PROVIDER_TYPE = "vercel"
    PROVIDER_NAME = "Vercel"
    PROVIDER_DESCRIPTION = "Vercel DNS API"
    REQUIRED_CREDENTIALS = ["api_token"]
    
    BASE_URL = "https://api.vercel.com"
    
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
            return True, resp.json() if resp.text else None
        except requests.RequestException as e:
            logger.error(f"Vercel API error: {e}")
            return False, str(e)
    
    def create_txt_record(self, domain, record_name, record_value, ttl=300):
        zone = self.get_zone_for_domain(domain)
        relative = self.get_relative_record_name(record_name, zone)
        data = {'name': relative, 'type': 'TXT', 'value': record_value, 'ttl': ttl}
        success, result = self._request('POST', f'/v2/domains/{zone}/records', data)
        if not success:
            return False, f"Failed: {result}"
        return True, "Record created"
    
    def delete_txt_record(self, domain, record_name):
        zone = self.get_zone_for_domain(domain)
        relative = self.get_relative_record_name(record_name, zone)
        
        success, result = self._request('GET', f'/v4/domains/{zone}/records')
        if not success:
            return False, f"Failed: {result}"
        for rec in result.get('records', []):
            if rec.get('type') == 'TXT' and rec.get('name') == relative:
                self._request('DELETE', f'/v2/domains/{zone}/records/{rec["id"]}')
        return True, "Record deleted"
    
    def test_connection(self):
        success, result = self._request('GET', '/v5/domains')
        if success:
            domains = [d['name'] for d in result.get('domains', [])]
            return True, f"Connected. Domains: {', '.join(domains)}"
        return False, f"Connection failed: {result}"
    
    @classmethod
    def get_credential_schema(cls):
        return [
            {'name': 'api_token', 'label': 'API Token', 'type': 'password', 'required': True,
             'help': 'vercel.com > Settings > Tokens'},
        ]
