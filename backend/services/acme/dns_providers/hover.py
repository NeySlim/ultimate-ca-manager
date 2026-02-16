"""
Hover DNS Provider
Uses Hover's unofficial API for DNS record management
Note: Hover does not have an official public API
"""
import requests
from typing import Tuple, Dict, Any, Optional
import logging

from .base import BaseDnsProvider

logger = logging.getLogger(__name__)


class HoverDnsProvider(BaseDnsProvider):
    PROVIDER_TYPE = "hover"
    PROVIDER_NAME = "Hover"
    PROVIDER_DESCRIPTION = "Hover DNS (session-based auth)"
    REQUIRED_CREDENTIALS = ["username", "password"]
    
    BASE_URL = "https://www.hover.com/api"
    
    def __init__(self, credentials: Dict[str, Any]):
        super().__init__(credentials)
        self._session = None
    
    def _authenticate(self) -> Tuple[bool, str]:
        if self._session:
            return True, "Already authenticated"
        self._session = requests.Session()
        try:
            resp = self._session.post(f'{self.BASE_URL}/login',
                data={'username': self.credentials['username'], 'password': self.credentials['password']}, timeout=30)
            if resp.status_code != 200 or not resp.json().get('succeeded'):
                self._session = None
                return False, "Authentication failed"
            return True, "Authenticated"
        except requests.RequestException as e:
            self._session = None
            return False, str(e)
    
    def _request(self, method: str, path: str, data: Optional[Dict] = None) -> Tuple[bool, Any]:
        ok, err = self._authenticate()
        if not ok:
            return False, err
        try:
            resp = self._session.request(method=method, url=f'{self.BASE_URL}{path}', json=data, timeout=30)
            if resp.status_code >= 400:
                return False, resp.reason
            return True, resp.json() if resp.text else None
        except requests.RequestException as e:
            return False, str(e)
    
    def create_txt_record(self, domain: str, record_name: str, record_value: str, ttl: int = 300) -> Tuple[bool, str]:
        relative = self.get_relative_record_name(record_name, domain)
        data = {'name': relative, 'type': 'TXT', 'content': record_value}
        success, result = self._request('POST', f'/domains/{domain}/dns', data)
        if not success:
            return False, f"Failed to create record: {result}"
        return True, "Record created successfully"
    
    def delete_txt_record(self, domain: str, record_name: str) -> Tuple[bool, str]:
        success, result = self._request('GET', f'/domains/{domain}/dns')
        if not success:
            return False, f"Failed to list records: {result}"
        for rec in result.get('domains', [{}])[0].get('entries', []):
            if rec.get('type') == 'TXT' and rec.get('name') == self.get_relative_record_name(record_name, domain):
                self._request('DELETE', f'/dns/{rec["id"]}')
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
            {'name': 'username', 'label': 'Username/Email', 'type': 'text', 'required': True},
            {'name': 'password', 'label': 'Password', 'type': 'password', 'required': True},
        ]
