"""
Core-Networks DNS Provider (Germany)
https://beta.api.core-networks.de/doc/
"""
import requests
from typing import Tuple, Dict, Any
import logging

from .base import BaseDnsProvider

logger = logging.getLogger(__name__)


class CoreNetworksDnsProvider(BaseDnsProvider):
    PROVIDER_TYPE = "corenetworks"
    PROVIDER_NAME = "Core-Networks"
    PROVIDER_DESCRIPTION = "Core-Networks DNS API (Germany)"
    REQUIRED_CREDENTIALS = ["username", "password"]
    
    BASE_URL = "https://beta.api.core-networks.de"
    
    def __init__(self, credentials):
        super().__init__(credentials)
        self._token = None
    
    def _login(self):
        if self._token:
            return True
        try:
            resp = requests.post(f"{self.BASE_URL}/auth/token",
                data={'login': self.credentials['username'], 'password': self.credentials['password']},
                timeout=30)
            if resp.status_code == 200:
                self._token = resp.json().get('token')
                return True
            return False
        except:
            return False
    
    def _request(self, method, path, data=None):
        if not self._login():
            return False, "Authentication failed"
        try:
            resp = requests.request(method, f"{self.BASE_URL}{path}",
                headers={'Authorization': f'Bearer {self._token}', 'Content-Type': 'application/json'},
                json=data, timeout=30)
            if resp.status_code >= 400:
                return False, resp.text
            return True, resp.json() if resp.text and resp.status_code != 204 else None
        except requests.RequestException as e:
            logger.error(f"Core-Networks API error: {e}")
            return False, str(e)
    
    def _find_zone(self, domain):
        success, result = self._request('GET', '/dns/zones/')
        if not success:
            return None
        for z in result or []:
            name = z.get('name', '')
            if domain.endswith(name):
                return name
        return None
    
    def create_txt_record(self, domain, record_name, record_value, ttl=300):
        zone = self._find_zone(domain)
        if not zone:
            return False, f"Zone not found for {domain}"
        relative = self.get_relative_record_name(record_name, zone)
        data = {'name': relative, 'type': 'TXT', 'data': f'"{record_value}"', 'ttl': ttl}
        success, result = self._request('POST', f'/dns/zones/{zone}/records/', data)
        if not success:
            return False, f"Failed: {result}"
        # Commit changes
        self._request('POST', f'/dns/zones/{zone}/records/commit')
        return True, "Record created"
    
    def delete_txt_record(self, domain, record_name):
        zone = self._find_zone(domain)
        if not zone:
            return False, f"Zone not found for {domain}"
        relative = self.get_relative_record_name(record_name, zone)
        
        success, result = self._request('GET', f'/dns/zones/{zone}/records/')
        if not success:
            return False, f"Failed: {result}"
        for rec in result or []:
            if rec.get('type') == 'TXT' and rec.get('name') == relative:
                self._request('DELETE', f'/dns/zones/{zone}/records/', rec)
        self._request('POST', f'/dns/zones/{zone}/records/commit')
        return True, "Record deleted"
    
    def test_connection(self):
        success, result = self._request('GET', '/dns/zones/')
        if success:
            zones = [z['name'] for z in result or []]
            return True, f"Connected. Zones: {', '.join(zones)}"
        return False, f"Connection failed: {result}"
    
    @classmethod
    def get_credential_schema(cls):
        return [
            {'name': 'username', 'label': 'Username', 'type': 'text', 'required': True,
             'help': 'Core-Networks account username'},
            {'name': 'password', 'label': 'Password', 'type': 'password', 'required': True,
             'help': 'Core-Networks account password'},
        ]
