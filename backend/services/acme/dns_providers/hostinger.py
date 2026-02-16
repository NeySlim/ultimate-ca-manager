"""
Hostinger DNS Provider
Uses Hostinger API for DNS record management
https://developers.hostinger.com/
"""
import requests
from typing import Tuple, Dict, Any, Optional
import logging

from .base import BaseDnsProvider

logger = logging.getLogger(__name__)


class HostingerDnsProvider(BaseDnsProvider):
    PROVIDER_TYPE = "hostinger"
    PROVIDER_NAME = "Hostinger"
    PROVIDER_DESCRIPTION = "Hostinger DNS API"
    REQUIRED_CREDENTIALS = ["api_token"]
    
    BASE_URL = "https://api.hostinger.com/v1"
    
    def _get_headers(self) -> Dict[str, str]:
        return {
            'Authorization': f'Bearer {self.credentials["api_token"]}',
            'Content-Type': 'application/json',
        }
    
    def _request(self, method: str, path: str, data: Optional[Dict] = None) -> Tuple[bool, Any]:
        url = f"{self.BASE_URL}{path}"
        try:
            resp = requests.request(method=method, url=url, headers=self._get_headers(), json=data, timeout=30)
            if resp.status_code >= 400:
                try:
                    error_msg = resp.json().get('message', resp.reason)
                except Exception:
                    error_msg = resp.reason
                return False, error_msg
            return True, resp.json() if resp.text else None
        except requests.RequestException as e:
            return False, str(e)
    
    def create_txt_record(self, domain: str, record_name: str, record_value: str, ttl: int = 300) -> Tuple[bool, str]:
        relative = self.get_relative_record_name(record_name, domain)
        data = {'type': 'TXT', 'name': relative, 'content': record_value, 'ttl': ttl}
        success, result = self._request('POST', f'/dns/{domain}/records', data)
        if not success:
            return False, f"Failed to create record: {result}"
        return True, "Record created successfully"
    
    def delete_txt_record(self, domain: str, record_name: str) -> Tuple[bool, str]:
        success, records = self._request('GET', f'/dns/{domain}/records')
        if not success:
            return False, f"Failed to list records: {records}"
        relative = self.get_relative_record_name(record_name, domain)
        for rec in (records or []):
            if rec.get('type') == 'TXT' and rec.get('name') == relative:
                self._request('DELETE', f'/dns/{domain}/records/{rec["id"]}')
        return True, "Record deleted successfully"
    
    def test_connection(self) -> Tuple[bool, str]:
        success, result = self._request('GET', '/dns')
        if success:
            return True, f"Connected successfully"
        return False, f"Connection failed: {result}"
    
    @classmethod
    def get_credential_schema(cls):
        return [
            {'name': 'api_token', 'label': 'API Token', 'type': 'password', 'required': True,
             'help': 'hPanel > Account > API Token'},
        ]
