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
        """(ok, error): POST /auth/token takes a JSON body and answers {token, expires}."""
        if self._token:
            return True, None
        try:
            resp = requests.post(f"{self.BASE_URL}/auth/token",
                json={'login': self.credentials['username'], 'password': self.credentials['password']},
                timeout=30)
            if resp.status_code >= 300:
                return False, self._error(resp, 'Authentication failed: ')
            self._token = self.remember_secret(resp.json().get('token'))
            if not self._token:
                return False, "Authentication failed: no token in the answer"
            return True, None
        except (requests.RequestException, ValueError) as e:
            return False, self._failure(e, 'Authentication failed: ')
    
    def _request(self, method, path, data=None, params=None):
        ok, err = self._login()
        if not ok:
            return False, err
        try:
            resp = requests.request(method, f"{self.BASE_URL}{path}",
                headers={'Authorization': f'Bearer {self._token}', 'Content-Type': 'application/json'},
                json=data, params=params, timeout=30)
            if resp.status_code >= 400:
                return False, self._error(resp)
            return True, resp.json() if resp.text and resp.status_code != 204 else None
        except (requests.RequestException, ValueError) as e:
            logger.error(f"Core-Networks API error: {self._failure(e)}")
            return False, self._failure(e)
    
    def _find_zone(self, domain):
        success, result = self._request('GET', '/dnszones/')
        if not success:
            return None
        z = self.find_zone(domain, result or [], key=lambda zone: zone.get('name', ''))
        return z['name'] if z else None
    
    def create_txt_record(self, domain, record_name, record_value, ttl=300):
        zone = self._find_zone(domain)
        if not zone:
            return False, f"Zone not found for {domain}"
        relative = self.get_relative_record_name(record_name, zone)
        data = {'name': relative, 'type': 'TXT', 'data': f'"{record_value}"', 'ttl': ttl}
        success, result = self._request('POST', f'/dnszones/{zone}/records/', data)
        if not success:
            return False, f"Failed: {result}"
        return self._commit(zone, "Record created")

    def _commit(self, zone, message):
        """Changes reach the nameservers only once the zone is committed."""
        success, result = self._request('POST', f'/dnszones/{zone}/records/commit')
        if not success:
            logger.warning(f"Core-Networks: commit of {zone} failed: {result}")
            return False, f"Commit failed: {result}"
        return True, message
    
    def delete_txt_record(self, domain, record_name, record_value):
        zone = self._find_zone(domain)
        if not zone:
            return False, f"Zone not found for {domain}"
        relative = self.get_relative_record_name(record_name, zone)
        
        success, result = self._request('GET', f'/dnszones/{zone}/records/', params={'type': 'TXT'})
        if not success:
            return False, f"Failed: {result}"
        deleted = False
        for rec in result or []:
            if (rec.get('type') == 'TXT' and rec.get('name') == relative
                    and self.txt_matches(rec.get('data'), record_value)):
                # The body is a filter and an empty one deletes the whole zone: always name all three.
                body = {'name': rec['name'], 'type': 'TXT', 'data': rec['data']}
                success, err = self._request('POST', f'/dnszones/{zone}/records/delete', body)
                if not success:
                    logger.warning(f"Core-Networks: failed to delete TXT value of {record_name}: {err}")
                    return False, f"Failed to delete record: {err}"
                deleted = True
        if not deleted:
            return True, "Record already absent"
        return self._commit(zone, "Record deleted")
    
    def test_connection(self):
        success, result = self._request('GET', '/dnszones/')
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
