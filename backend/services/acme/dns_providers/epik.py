"""
Epik DNS Provider
Uses Epik Marketplace API for DNS record management
https://docs.userapi.epik.com/v2/
"""
import requests
from typing import Tuple, Dict, Any, Optional
import logging

from .base import BaseDnsProvider

logger = logging.getLogger(__name__)


class EpikDnsProvider(BaseDnsProvider):
    PROVIDER_TYPE = "epik"
    PROVIDER_NAME = "Epik"
    PROVIDER_DESCRIPTION = "Epik Domains DNS API"
    REQUIRED_CREDENTIALS = ["api_key"]
    
    BASE_URL = "https://usersapiv2.epik.com/v2"
    
    def _request(self, method: str, path: str, params: Optional[Dict] = None, data: Optional[Dict] = None) -> Tuple[bool, Any]:
        url = f"{self.BASE_URL}{path}"
        if params is None:
            params = {}
        params['SIGNATURE'] = self.credentials['api_key']
        try:
            resp = requests.request(method=method, url=url, params=params, json=data, timeout=30)
            if resp.status_code >= 400:
                return False, resp.reason
            body = resp.json()
            if body.get('code') != 200 and body.get('status') != 'SUCCESS':
                return False, body.get('message', 'Unknown error')
            return True, body
        except requests.RequestException as e:
            return False, str(e)
    
    def create_txt_record(self, domain: str, record_name: str, record_value: str, ttl: int = 300) -> Tuple[bool, str]:
        host = self.get_relative_record_name(record_name, domain)
        data = {'HOST': host, 'TYPE': 'TXT', 'DATA': record_value, 'TTL': ttl, 'AUX': 0}
        success, result = self._request('POST', f'/domains/{domain}/records', data=data)
        if not success:
            return False, f"Failed to create record: {result}"
        return True, "Record created successfully"
    
    def delete_txt_record(self, domain: str, record_name: str) -> Tuple[bool, str]:
        success, result = self._request('GET', f'/domains/{domain}/records')
        if not success:
            return False, f"Failed to list records: {result}"
        host = self.get_relative_record_name(record_name, domain)
        records = result.get('data', {}).get('records', [])
        for rec in records:
            if rec.get('TYPE') == 'TXT' and rec.get('HOST') == host:
                self._request('DELETE', f'/domains/{domain}/records/{rec["ID"]}')
        return True, "Record deleted successfully"
    
    def test_connection(self) -> Tuple[bool, str]:
        success, result = self._request('GET', '/domains')
        if success:
            return True, "Connected successfully"
        return False, f"Connection failed: {result}"
    
    @classmethod
    def get_credential_schema(cls):
        return [
            {'name': 'api_key', 'label': 'API Key (Signature)', 'type': 'password', 'required': True,
             'help': 'Epik > Account > API Signature'},
        ]
