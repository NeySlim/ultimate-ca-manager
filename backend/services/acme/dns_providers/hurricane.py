"""
Hurricane Electric (he.net) DNS Provider
Uses HE's TXT record update API
https://dns.he.net/
"""
import requests
from typing import Tuple, Dict, Any, Optional
import logging

from .base import BaseDnsProvider

logger = logging.getLogger(__name__)


class HurricaneDnsProvider(BaseDnsProvider):
    PROVIDER_TYPE = "hurricane"
    PROVIDER_NAME = "Hurricane Electric"
    PROVIDER_DESCRIPTION = "Hurricane Electric Free DNS (he.net)"
    REQUIRED_CREDENTIALS = ["password"]
    
    BASE_URL = "https://dyn.dns.he.net"
    
    def create_txt_record(self, domain: str, record_name: str, record_value: str, ttl: int = 300) -> Tuple[bool, str]:
        """HE uses a dynamic TXT update endpoint per record."""
        try:
            resp = requests.post(f'{self.BASE_URL}/nic/update', data={
                'hostname': record_name,
                'password': self.credentials['password'],
                'txt': record_value,
            }, timeout=30)
            body = resp.text.strip()
            if body.startswith('good') or body.startswith('nochg'):
                return True, "Record created successfully"
            return False, f"HE update failed: {body}"
        except requests.RequestException as e:
            return False, str(e)
    
    def delete_txt_record(self, domain: str, record_name: str) -> Tuple[bool, str]:
        # HE doesn't have a delete API — set TXT to empty value
        try:
            resp = requests.post(f'{self.BASE_URL}/nic/update', data={
                'hostname': record_name,
                'password': self.credentials['password'],
                'txt': '',
            }, timeout=30)
            return True, "Record cleared (HE does not support delete)"
        except requests.RequestException as e:
            return False, str(e)
    
    def test_connection(self) -> Tuple[bool, str]:
        # HE has no list/status endpoint — just verify credentials format
        if self.credentials.get('password'):
            return True, "Credentials configured (HE uses per-record DDNS keys)"
        return False, "Password not configured"
    
    @classmethod
    def get_credential_schema(cls):
        return [
            {'name': 'password', 'label': 'DDNS Key', 'type': 'password', 'required': True,
             'help': 'dns.he.net > Edit Zone > Enable DDNS on the TXT record > copy the generated key'},
        ]
