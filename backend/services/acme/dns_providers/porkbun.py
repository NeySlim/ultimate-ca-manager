"""
Porkbun DNS Provider
https://porkbun.com/api/json/v3/documentation
"""
import requests
from typing import Tuple, Dict, Any
import logging

from .base import BaseDnsProvider

logger = logging.getLogger(__name__)


class PorkbunDnsProvider(BaseDnsProvider):
    PROVIDER_TYPE = "porkbun"
    PROVIDER_NAME = "Porkbun"
    PROVIDER_DESCRIPTION = "Porkbun DNS API"
    REQUIRED_CREDENTIALS = ["api_key", "secret_api_key"]
    
    BASE_URL = "https://api.porkbun.com/api/json/v3"
    
    def _auth_body(self, extra=None):
        body = {
            'apikey': self.credentials['api_key'],
            'secretapikey': self.credentials['secret_api_key'],
        }
        if extra:
            body.update(extra)
        return body
    
    def _request(self, path, data=None):
        body = self._auth_body(data)
        try:
            # A 307/308 to another host would resend the API keys in the body
            resp = requests.post(f"{self.BASE_URL}{path}", json=body, timeout=30,
                                 allow_redirects=False)
            result = resp.json()
            if result.get('status') == 'SUCCESS':
                # A write to a domain not delegated to Porkbun succeeds and says so here.
                for warning in result.get('warnings') or []:
                    logger.warning(f"Porkbun: {warning}")
                return True, result
            message = result.get('message') or f"HTTP {resp.status_code}"
            return False, self.redact_secrets(f"{result.get('code')}: {message}" if result.get('code') else message)
        except (requests.RequestException, ValueError) as e:
            logger.error(f"Porkbun API error: {self._failure(e)}")
            return False, self._failure(e)
    
    def create_txt_record(self, domain, record_name, record_value, ttl=300):
        zone = self.get_zone_for_domain(domain)
        relative = self.get_relative_record_name(record_name, zone)
        success, result = self._request(f'/dns/create/{zone}', {
            'name': relative, 'type': 'TXT', 'content': record_value, 'ttl': int(ttl)
        })
        if not success:
            msg = f"Failed: {result}"
            logger.warning(f"Porkbun: {msg}")
            return False, msg
        return True, "Record created"
    
    def delete_txt_record(self, domain, record_name, record_value):
        zone = self.get_zone_for_domain(domain)
        relative = self.get_relative_record_name(record_name, zone)
        
        success, result = self._request(f'/dns/retrieveByNameType/{zone}/TXT/{relative}')
        if not success:
            msg = f"Failed to list records: {result}"
            logger.warning(f"Porkbun: {msg}")
            return False, msg
        for rec in result.get('records') or []:
            if self.txt_matches(rec.get('content'), record_value):
                ok, err = self._request(f'/dns/delete/{zone}/{rec["id"]}')
                if not ok:
                    logger.warning(f"Porkbun: failed to delete TXT value of {record_name}: {err}")
                    return False, f"Failed to delete record: {err}"
        return True, "Record deleted"
    
    def test_connection(self):
        success, result = self._request('/ping')
        if success:
            return True, "Connected successfully"
        return False, f"Connection failed: {result}"
    
    @classmethod
    def get_credential_schema(cls):
        return [
            {'name': 'api_key', 'label': 'API Key', 'type': 'password', 'required': True,
             'help': 'porkbun.com > Account > API Access'},
            {'name': 'secret_api_key', 'label': 'Secret API Key', 'type': 'password', 'required': True,
             'help': 'Porkbun Secret API Key'},
        ]
