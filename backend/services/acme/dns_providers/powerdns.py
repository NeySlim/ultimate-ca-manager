"""
PowerDNS Authoritative Server Provider
Uses PowerDNS HTTP API for DNS record management
https://doc.powerdns.com/authoritative/http-api/
"""
import requests
from urllib.parse import quote
from typing import Tuple, Dict, Any, Optional
import logging

from utils.ssrf_protection import safe_request

from .base import BaseDnsProvider

logger = logging.getLogger(__name__)


class PowerDnsDnsProvider(BaseDnsProvider):
    PROVIDER_TYPE = "powerdns"
    PROVIDER_NAME = "PowerDNS"
    PROVIDER_DESCRIPTION = "PowerDNS Authoritative Server API (self-hosted)"
    REQUIRED_CREDENTIALS = ["server_url", "api_key"]
    
    def __init__(self, credentials: Dict[str, Any]):
        super().__init__(credentials)
        self.server_url = self.credentials['server_url'].rstrip('/')
    
    def _get_headers(self) -> Dict[str, str]:
        return {'X-API-Key': self.credentials['api_key'], 'Content-Type': 'application/json'}
    
    def _request(self, method: str, path: str, data: Optional[Dict] = None) -> Tuple[bool, Any]:
        url = f"{self.server_url}/api/v1/servers/localhost{path}"
        try:
            verify_ssl = self.credentials.get('verify_ssl', True)
            # Pinned, and the API key never follows a redirect to another origin.
            # A PowerDNS on the same host stays reachable.
            resp = safe_request(method, url, allow_loopback=True, headers=self._get_headers(),
                                json=data, timeout=30, verify=verify_ssl)
            if resp.status_code >= 400:
                try:
                    error_msg = resp.json().get('error', resp.reason)
                except Exception:
                    error_msg = resp.reason
                return False, error_msg
            return True, resp.json() if resp.text and resp.status_code != 204 else None
        except (requests.RequestException, ValueError) as e:
            return False, self._failure(e)
    
    def _find_zone(self, domain: str) -> Optional[str]:
        success, zones = self._request('GET', '/zones')
        if not success:
            return None
        domain_parts = domain.split('.')
        for i in range(len(domain_parts) - 1):
            zone_name = '.'.join(domain_parts[i:]) + '.'
            for z in zones:
                if z['name'] == zone_name:
                    return zone_name
        return None
    
    def create_txt_record(self, domain: str, record_name: str, record_value: str, ttl: int = 300) -> Tuple[bool, str]:
        zone = self._find_zone(domain)
        if not zone:
            return False, f"Could not find zone for {domain}"
        fqdn = record_name if record_name.endswith('.') else record_name + '.'
        # REPLACE rewrites the whole rrset, so send the existing values plus the new one.
        success, result = self._request('GET', f'/zones/{zone}?rrset_name={quote(fqdn)}&rrset_type=TXT')
        if not success:
            return False, f"Failed to read existing records: {result}"
        rrsets = [r for r in (result or {}).get('rrsets', [])
                  if r.get('type') == 'TXT' and r.get('name', '').lower() == fqdn.lower()]
        records = [{'content': r['content'], 'disabled': r.get('disabled', False)}
                   for rr in rrsets for r in rr.get('records', [])]
        content = f'"{record_value}"'
        same = [r for r in records if r['content'] == content]
        if any(not r['disabled'] for r in same):
            return True, "Record already present"
        # A disabled copy is re-enabled: PowerDNS refuses a duplicate record in an rrset
        if same:
            same[0]['disabled'] = False
        else:
            records.append({'content': content, 'disabled': False})
        data = {'rrsets': [{'name': fqdn, 'type': 'TXT', 'ttl': rrsets[0].get('ttl', ttl) if rrsets else ttl,
                            'changetype': 'REPLACE', 'records': records}]}
        success, result = self._request('PATCH', f'/zones/{zone}', data)
        if not success:
            return False, f"Failed to create record: {result}"
        return True, "Record created successfully"
    
    def delete_txt_record(self, domain: str, record_name: str) -> Tuple[bool, str]:
        zone = self._find_zone(domain)
        if not zone:
            return False, f"Could not find zone for {domain}"
        fqdn = record_name if record_name.endswith('.') else record_name + '.'
        data = {'rrsets': [{'name': fqdn, 'type': 'TXT', 'changetype': 'DELETE'}]}
        success, result = self._request('PATCH', f'/zones/{zone}', data)
        if not success:
            return False, f"Failed to delete record: {result}"
        return True, "Record deleted successfully"
    
    def test_connection(self) -> Tuple[bool, str]:
        success, zones = self._request('GET', '/zones')
        if success:
            names = [z['name'] for z in zones]
            return True, f"Connected. Found {len(zones)} zone(s): {', '.join(names[:5])}"
        return False, f"Connection failed: {zones}"
    
    @classmethod
    def get_credential_schema(cls):
        return [
            {'name': 'server_url', 'label': 'Server URL', 'type': 'text', 'required': True,
             'help': 'e.g. http://pdns.example.com:8081'},
            {'name': 'api_key', 'label': 'API Key', 'type': 'password', 'required': True,
             'help': 'Set in pdns.conf: api-key=your-key'},
        ]
