"""
ClouDNS Provider
https://www.cloudns.net/wiki/article/56/
"""
import requests
from typing import Tuple, Dict, Any
import logging

from .base import BaseDnsProvider

logger = logging.getLogger(__name__)


class ClouDnsDnsProvider(BaseDnsProvider):
    PROVIDER_TYPE = "cloudns"
    PROVIDER_NAME = "ClouDNS"
    PROVIDER_DESCRIPTION = "ClouDNS API"
    REQUIRED_CREDENTIALS = ["auth_id", "auth_password"]
    OPTIONAL_CREDENTIALS = ["sub_auth_id"]
    
    BASE_URL = "https://api.cloudns.net"
    
    def _auth_params(self):
        p = {'auth-password': self.credentials['auth_password']}
        if self.credentials.get('sub_auth_id'):
            p['sub-auth-id'] = self.credentials['sub_auth_id']
        else:
            p['auth-id'] = self.credentials['auth_id']
        return p
    
    def _request(self, path, params=None):
        p = self._auth_params()
        if params:
            p.update(params)
        try:
            resp = requests.get(f"{self.BASE_URL}{path}", params=p, timeout=30)
            if resp.status_code >= 400:
                return False, resp.text
            data = resp.json()
            if isinstance(data, dict) and data.get('status') == 'Failed':
                return False, data.get('statusDescription', 'Unknown error')
            return True, data
        except requests.RequestException as e:
            logger.error(f"ClouDNS API error: {e}")
            return False, str(e)
    
    def _post(self, path, params=None):
        p = self._auth_params()
        if params:
            p.update(params)
        try:
            resp = requests.post(f"{self.BASE_URL}{path}", data=p, timeout=30)
            data = resp.json()
            if isinstance(data, dict) and data.get('status') == 'Failed':
                return False, data.get('statusDescription', 'Unknown error')
            return True, data
        except requests.RequestException as e:
            return False, str(e)
    
    def _find_zone(self, domain):
        success, result = self._request('/dns/list-zones.json', {'page': 1, 'rows-per-page': 100})
        if not success:
            return None
        # result is a list of zones
        if isinstance(result, list):
            for z in result:
                if domain.endswith(z.get('name', '')):
                    return z['name']
        return None
    
    def create_txt_record(self, domain, record_name, record_value, ttl=300):
        zone = self._find_zone(domain) or self.get_zone_for_domain(domain)
        relative = self.get_relative_record_name(record_name, zone)
        success, result = self._post('/dns/add-record.json', {
            'domain-name': zone, 'host': relative, 'record-type': 'TXT',
            'record': record_value, 'ttl': str(ttl)
        })
        if not success:
            return False, f"Failed: {result}"
        return True, "Record created"
    
    def delete_txt_record(self, domain, record_name):
        zone = self._find_zone(domain) or self.get_zone_for_domain(domain)
        relative = self.get_relative_record_name(record_name, zone)
        
        success, result = self._request('/dns/records.json', {
            'domain-name': zone, 'host': relative, 'type': 'TXT'
        })
        if not success:
            return False, f"Failed: {result}"
        if isinstance(result, dict):
            for rec_id in result:
                self._post('/dns/delete-record.json', {'domain-name': zone, 'record-id': rec_id})
        return True, "Record deleted"
    
    def test_connection(self):
        success, result = self._request('/dns/login.json')
        if success:
            return True, "Connected successfully"
        return False, f"Connection failed: {result}"
    
    @classmethod
    def get_credential_schema(cls):
        return [
            {'name': 'auth_id', 'label': 'Auth ID', 'type': 'text', 'required': True,
             'help': 'ClouDNS API user auth-id'},
            {'name': 'auth_password', 'label': 'Auth Password', 'type': 'password', 'required': True,
             'help': 'ClouDNS API auth-password'},
            {'name': 'sub_auth_id', 'label': 'Sub Auth ID', 'type': 'text', 'required': False,
             'help': 'Optional: sub-auth-id instead of auth-id'},
        ]
