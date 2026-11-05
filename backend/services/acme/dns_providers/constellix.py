"""
Constellix DNS Provider
Uses Constellix DNS v4 API with HMAC-SHA1 authentication
https://api.dns.constellix.com/v4/docs
"""
import requests
import hmac
import hashlib
import base64
import time
from typing import Tuple, Dict, Any, Optional
import logging

from .base import BaseDnsProvider

logger = logging.getLogger(__name__)


class ConstellixDnsProvider(BaseDnsProvider):
    PROVIDER_TYPE = "constellix"
    PROVIDER_NAME = "Constellix"
    PROVIDER_DESCRIPTION = "Constellix Managed DNS API"
    REQUIRED_CREDENTIALS = ["api_key", "secret_key"]
    
    BASE_URL = "https://api.dns.constellix.com/v4"
    
    def _get_headers(self) -> Dict[str, str]:
        timestamp = str(int(time.time() * 1000))
        hmac_hash = hmac.new(
            self.credentials['secret_key'].encode(),
            timestamp.encode(),
            hashlib.sha1
        ).digest()
        token = base64.b64encode(hmac_hash).decode()
        return {
            'x-cns-security-token': f'{self.credentials["api_key"]}:{token}:{timestamp}',
            'Content-Type': 'application/json',
        }
    
    def _request(self, method: str, path: str, data: Optional[Dict] = None) -> Tuple[bool, Any]:
        url = f"{self.BASE_URL}{path}"
        try:
            resp = requests.request(method=method, url=url, headers=self._get_headers(), json=data, timeout=30)
            if resp.status_code >= 400:
                return False, resp.reason
            return True, resp.json() if resp.text else None
        except requests.RequestException as e:
            return False, self._failure(e)
    
    def _find_domain(self, domain: str) -> Optional[Dict]:
        success, result = self._request('GET', '/domains')
        if not success:
            return None
        domains = result.get('data', [])
        domain_parts = domain.split('.')
        for i in range(len(domain_parts) - 1):
            name = '.'.join(domain_parts[i:])
            for d in domains:
                if d['name'] == name:
                    return d
        return None
    
    def create_txt_record(self, domain: str, record_name: str, record_value: str, ttl: int = 300) -> Tuple[bool, str]:
        dom = self._find_domain(domain)
        if not dom:
            return False, f"Could not find domain {domain}"
        relative = self.get_relative_record_name(record_name, dom['name'])
        data = {'name': relative, 'ttl': ttl, 'roundRobin': [{'value': f'"{record_value}"'}]}
        success, result = self._request('POST', f'/domains/{dom["id"]}/records/txt', data)
        if not success:
            return False, f"Failed to create record: {result}"
        return True, "Record created successfully"
    
    def delete_txt_record(self, domain: str, record_name: str, record_value: str) -> Tuple[bool, str]:
        dom = self._find_domain(domain)
        if not dom:
            return False, f"Could not find domain {domain}"
        success, result = self._request('GET', f'/domains/{dom["id"]}/records/txt')
        if not success:
            return False, f"Failed to list records: {result}"
        relative = self.get_relative_record_name(record_name, dom['name'])
        # A record's roundRobin holds every value of the name: keep the others, delete it only when empty.
        for rec in result.get('data', []):
            if rec.get('name') != relative:
                continue
            values = list(rec.get('roundRobin') or [])
            remaining = [v for v in values if not self.txt_matches(v.get('value'), record_value)]
            if len(remaining) == len(values):
                continue
            path = f'/domains/{dom["id"]}/records/txt/{rec["id"]}'
            if remaining:
                success, result = self._request(
                    'PUT', path, {'name': relative, 'ttl': rec.get('ttl', 300), 'roundRobin': remaining})
            else:
                success, result = self._request('DELETE', path)
            if not success:
                return False, f"Failed to delete record: {result}"
        return True, "Record deleted successfully"
    
    def test_connection(self) -> Tuple[bool, str]:
        success, result = self._request('GET', '/domains')
        if success:
            domains = result.get('data', [])
            return True, f"Connected. Found {len(domains)} domain(s)"
        return False, f"Connection failed: {result}"
    
    @classmethod
    def get_credential_schema(cls):
        return [
            {'name': 'api_key', 'label': 'API Key', 'type': 'password', 'required': True},
            {'name': 'secret_key', 'label': 'Secret Key', 'type': 'password', 'required': True,
             'help': 'Constellix portal > User Administration > API'},
        ]
