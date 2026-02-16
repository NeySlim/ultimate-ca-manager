"""
Mythic Beasts DNS Provider
Uses Mythic Beasts DNS API v2
https://www.mythic-beasts.com/support/api/dnsv2
"""
import requests
from typing import Tuple, Dict, Any, Optional
import logging

from .base import BaseDnsProvider

logger = logging.getLogger(__name__)


class MythicBeastsDnsProvider(BaseDnsProvider):
    PROVIDER_TYPE = "mythicbeasts"
    PROVIDER_NAME = "Mythic Beasts"
    PROVIDER_DESCRIPTION = "Mythic Beasts DNS API v2 (UK)"
    REQUIRED_CREDENTIALS = ["api_key", "api_secret"]
    
    BASE_URL = "https://api.mythic-beasts.com/dns/v2"
    TOKEN_URL = "https://auth.mythic-beasts.com/login"
    
    def __init__(self, credentials: Dict[str, Any]):
        super().__init__(credentials)
        self._token = None
    
    def _authenticate(self) -> Tuple[bool, str]:
        if self._token:
            return True, "OK"
        try:
            resp = requests.post(self.TOKEN_URL,
                data={'grant_type': 'client_credentials'},
                auth=(self.credentials['api_key'], self.credentials['api_secret']),
                timeout=30)
            if resp.status_code != 200:
                return False, f"Auth failed: {resp.reason}"
            self._token = resp.json()['access_token']
            return True, "OK"
        except requests.RequestException as e:
            return False, str(e)
    
    def _request(self, method: str, path: str, data: Optional[str] = None) -> Tuple[bool, Any]:
        ok, err = self._authenticate()
        if not ok:
            return False, err
        url = f"{self.BASE_URL}{path}"
        headers = {'Authorization': f'Bearer {self._token}'}
        if data:
            headers['Content-Type'] = 'text/dns'
        try:
            resp = requests.request(method=method, url=url, headers=headers, data=data, timeout=30)
            if resp.status_code >= 400:
                return False, resp.text or resp.reason
            return True, resp.json() if resp.text and resp.headers.get('content-type', '').startswith('application/json') else resp.text
        except requests.RequestException as e:
            return False, str(e)
    
    def create_txt_record(self, domain: str, record_name: str, record_value: str, ttl: int = 300) -> Tuple[bool, str]:
        relative = self.get_relative_record_name(record_name, domain)
        record_line = f"{relative} {ttl} TXT {record_value}"
        success, result = self._request('POST', f'/zones/{domain}/records', data=record_line)
        if not success:
            return False, f"Failed to create record: {result}"
        return True, "Record created successfully"
    
    def delete_txt_record(self, domain: str, record_name: str) -> Tuple[bool, str]:
        relative = self.get_relative_record_name(record_name, domain)
        record_line = f"{relative} TXT"
        success, result = self._request('DELETE', f'/zones/{domain}/records', data=record_line)
        if not success:
            return False, f"Failed to delete record: {result}"
        return True, "Record deleted successfully"
    
    def test_connection(self) -> Tuple[bool, str]:
        success, result = self._request('GET', '/zones')
        if success:
            return True, "Connected successfully"
        return False, f"Connection failed: {result}"
    
    @classmethod
    def get_credential_schema(cls):
        return [
            {'name': 'api_key', 'label': 'API Key', 'type': 'password', 'required': True},
            {'name': 'api_secret', 'label': 'API Secret', 'type': 'password', 'required': True,
             'help': 'mythic-beasts.com > API Keys'},
        ]
