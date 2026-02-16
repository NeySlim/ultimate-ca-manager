"""
Rackspace Cloud DNS Provider
Uses Rackspace Cloud DNS API v1.0
https://docs.rackspace.com/docs/cloud-dns/v1
"""
import requests
from typing import Tuple, Dict, Any, Optional
import logging

from .base import BaseDnsProvider

logger = logging.getLogger(__name__)


class RackspaceDnsProvider(BaseDnsProvider):
    PROVIDER_TYPE = "rackspace"
    PROVIDER_NAME = "Rackspace"
    PROVIDER_DESCRIPTION = "Rackspace Cloud DNS API"
    REQUIRED_CREDENTIALS = ["username", "api_key"]
    
    AUTH_URL = "https://identity.api.rackspacecloud.com/v2.0/tokens"
    
    def __init__(self, credentials: Dict[str, Any]):
        super().__init__(credentials)
        self._token = None
        self._dns_endpoint = None
    
    def _authenticate(self) -> Tuple[bool, str]:
        if self._token:
            return True, "Already authenticated"
        data = {'auth': {'RAX-KSKEY:apiKeyCredentials': {
            'username': self.credentials['username'],
            'apiKey': self.credentials['api_key']
        }}}
        try:
            resp = requests.post(self.AUTH_URL, json=data, timeout=30)
            if resp.status_code != 200:
                return False, f"Auth failed: {resp.reason}"
            body = resp.json()
            self._token = body['access']['token']['id']
            for sc in body['access']['serviceCatalog']:
                if sc['name'] == 'cloudDNS':
                    self._dns_endpoint = sc['endpoints'][0]['publicURL']
                    break
            if not self._dns_endpoint:
                return False, "Could not find Cloud DNS endpoint"
            return True, "Authenticated"
        except requests.RequestException as e:
            return False, str(e)
    
    def _request(self, method: str, path: str, data: Optional[Dict] = None) -> Tuple[bool, Any]:
        ok, err = self._authenticate()
        if not ok:
            return False, err
        url = f"{self._dns_endpoint}{path}"
        headers = {'X-Auth-Token': self._token, 'Content-Type': 'application/json'}
        try:
            resp = requests.request(method=method, url=url, headers=headers, json=data, timeout=30)
            if resp.status_code >= 400:
                return False, resp.reason
            return True, resp.json() if resp.text else None
        except requests.RequestException as e:
            return False, str(e)
    
    def _find_domain(self, domain: str) -> Optional[Dict]:
        success, result = self._request('GET', f'/domains?name={domain}')
        if not success:
            return None
        domains = result.get('domains', [])
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
        data = {'records': [{'name': record_name, 'type': 'TXT', 'data': record_value, 'ttl': ttl}]}
        success, result = self._request('POST', f'/domains/{dom["id"]}/records', data)
        if not success:
            return False, f"Failed to create record: {result}"
        return True, "Record created successfully"
    
    def delete_txt_record(self, domain: str, record_name: str) -> Tuple[bool, str]:
        dom = self._find_domain(domain)
        if not dom:
            return False, f"Could not find domain {domain}"
        success, result = self._request('GET', f'/domains/{dom["id"]}/records?type=TXT&name={record_name}')
        if not success:
            return False, f"Failed to list records: {result}"
        for rec in result.get('records', []):
            self._request('DELETE', f'/domains/{dom["id"]}/records/{rec["id"]}')
        return True, "Record deleted successfully"
    
    def test_connection(self) -> Tuple[bool, str]:
        success, result = self._request('GET', '/domains?limit=10')
        if success:
            domains = result.get('domains', [])
            return True, f"Connected. Found {len(domains)} domain(s)"
        return False, f"Connection failed: {result}"
    
    @classmethod
    def get_credential_schema(cls):
        return [
            {'name': 'username', 'label': 'Username', 'type': 'text', 'required': True},
            {'name': 'api_key', 'label': 'API Key', 'type': 'password', 'required': True,
             'help': 'Account Settings > Rackspace API Key'},
        ]
