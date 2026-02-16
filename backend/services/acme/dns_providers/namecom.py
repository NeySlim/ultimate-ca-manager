"""
Name.com DNS Provider
Uses Name.com v4 API for DNS record management
https://www.name.com/api-docs
"""
import requests
from typing import Tuple, Dict, Any, Optional
import logging

from .base import BaseDnsProvider

logger = logging.getLogger(__name__)


class NamecomDnsProvider(BaseDnsProvider):
    PROVIDER_TYPE = "namecom"
    PROVIDER_NAME = "Name.com"
    PROVIDER_DESCRIPTION = "Name.com DNS API v4"
    REQUIRED_CREDENTIALS = ["username", "api_token"]
    
    BASE_URL = "https://api.name.com/v4"
    
    def _get_auth(self):
        return (self.credentials['username'], self.credentials['api_token'])
    
    def _request(self, method: str, path: str, data: Optional[Dict] = None) -> Tuple[bool, Any]:
        url = f"{self.BASE_URL}{path}"
        try:
            resp = requests.request(method=method, url=url, auth=self._get_auth(),
                                    json=data, timeout=30, headers={'Content-Type': 'application/json'})
            if resp.status_code >= 400:
                try:
                    error_msg = resp.json().get('message', resp.reason)
                except Exception:
                    error_msg = resp.reason
                return False, error_msg
            return True, resp.json() if resp.text else None
        except requests.RequestException as e:
            return False, str(e)
    
    def _find_domain(self, domain: str) -> Optional[str]:
        domain_parts = domain.split('.')
        for i in range(len(domain_parts) - 1):
            name = '.'.join(domain_parts[i:])
            success, result = self._request('GET', f'/domains/{name}')
            if success:
                return name
        return None
    
    def create_txt_record(self, domain: str, record_name: str, record_value: str, ttl: int = 300) -> Tuple[bool, str]:
        dom = self._find_domain(domain)
        if not dom:
            return False, f"Could not find domain {domain}"
        fqdn = record_name if record_name.endswith('.') else record_name + '.'
        data = {'host': self.get_relative_record_name(record_name, dom), 'type': 'TXT',
                'answer': record_value, 'ttl': ttl, 'fqdn': fqdn}
        success, result = self._request('POST', f'/domains/{dom}/records', data)
        if not success:
            return False, f"Failed to create record: {result}"
        return True, "Record created successfully"
    
    def delete_txt_record(self, domain: str, record_name: str) -> Tuple[bool, str]:
        dom = self._find_domain(domain)
        if not dom:
            return False, f"Could not find domain {domain}"
        success, result = self._request('GET', f'/domains/{dom}/records')
        if not success:
            return False, f"Failed to list records: {result}"
        host = self.get_relative_record_name(record_name, dom)
        for rec in result.get('records', []):
            if rec.get('type') == 'TXT' and rec.get('host') == host:
                self._request('DELETE', f'/domains/{dom}/records/{rec["id"]}')
        return True, "Record deleted successfully"
    
    def test_connection(self) -> Tuple[bool, str]:
        success, result = self._request('GET', '/domains')
        if success:
            domains = result.get('domains', [])
            return True, f"Connected. Found {len(domains)} domain(s)"
        return False, f"Connection failed: {result}"
    
    @classmethod
    def get_credential_schema(cls):
        return [
            {'name': 'username', 'label': 'Username', 'type': 'text', 'required': True},
            {'name': 'api_token', 'label': 'API Token', 'type': 'password', 'required': True,
             'help': 'name.com > Account > API Token'},
        ]
