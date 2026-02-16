"""
DNS Made Easy Provider
https://api-docs.dnsmadeeasy.com/
"""
import requests, hashlib, hmac, time
from typing import Tuple, Dict, Any, Optional
import logging
from datetime import datetime, timezone

from .base import BaseDnsProvider

logger = logging.getLogger(__name__)


class DnsMadeEasyDnsProvider(BaseDnsProvider):
    PROVIDER_TYPE = "dnsmadeeasy"
    PROVIDER_NAME = "DNS Made Easy"
    PROVIDER_DESCRIPTION = "DNS Made Easy API"
    REQUIRED_CREDENTIALS = ["api_key", "secret_key"]
    
    BASE_URL = "https://api.dnsmadeeasy.com/V2.0"
    
    def _get_headers(self):
        now = datetime.now(timezone.utc).strftime('%a, %d %b %Y %H:%M:%S GMT')
        hmac_hash = hmac.new(
            self.credentials['secret_key'].encode(),
            now.encode(), hashlib.sha1
        ).hexdigest()
        return {
            'x-dnsme-apiKey': self.credentials['api_key'],
            'x-dnsme-requestDate': now,
            'x-dnsme-hmac': hmac_hash,
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
            logger.error(f"DNS Made Easy API error: {e}")
            return False, str(e)
    
    def _find_domain(self, domain):
        success, result = self._request('GET', '/dns/managed/')
        if not success:
            return None
        for d in result.get('data', []):
            if domain.endswith(d['name']):
                return d['id'], d['name']
        return None
    
    def create_txt_record(self, domain, record_name, record_value, ttl=300):
        info = self._find_domain(domain)
        if not info:
            return False, f"Domain not found for {domain}"
        domain_id, zone = info
        relative = self.get_relative_record_name(record_name, zone)
        data = {'name': relative, 'type': 'TXT', 'value': f'"{record_value}"', 'ttl': ttl}
        success, result = self._request('POST', f'/dns/managed/{domain_id}/records/', data)
        if not success:
            return False, f"Failed: {result}"
        return True, "Record created"
    
    def delete_txt_record(self, domain, record_name):
        info = self._find_domain(domain)
        if not info:
            return False, f"Domain not found for {domain}"
        domain_id, zone = info
        relative = self.get_relative_record_name(record_name, zone)
        
        success, result = self._request('GET', f'/dns/managed/{domain_id}/records?type=TXT&recordName={relative}')
        if not success:
            return False, f"Failed: {result}"
        for rec in result.get('data', []):
            self._request('DELETE', f'/dns/managed/{domain_id}/records/{rec["id"]}')
        return True, "Record deleted"
    
    def test_connection(self):
        success, result = self._request('GET', '/dns/managed/')
        if success:
            domains = [d['name'] for d in result.get('data', [])]
            return True, f"Connected. Domains: {', '.join(domains)}"
        return False, f"Connection failed: {result}"
    
    @classmethod
    def get_credential_schema(cls):
        return [
            {'name': 'api_key', 'label': 'API Key', 'type': 'password', 'required': True,
             'help': 'dnsmadeeasy.com > Config > Account Info'},
            {'name': 'secret_key', 'label': 'Secret Key', 'type': 'password', 'required': True,
             'help': 'HMAC secret key'},
        ]
