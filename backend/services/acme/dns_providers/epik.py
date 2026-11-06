"""
Epik DNS Provider
Uses Epik Domains API v2 for DNS host records
https://usersapiv2.epik.com/v2 (API reference)
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
        # The key goes in the Authorization header; the SIGNATURE query parameter is deprecated.
        headers = {'Authorization': f'Bearer {self.credentials["api_key"]}'}
        try:
            resp = requests.request(method=method, url=url, params=params, json=data,
                                    headers=headers, timeout=30)
            if resp.status_code >= 400:
                return False, self._error(resp)
            return True, resp.json() if resp.text else {}
        except (requests.RequestException, ValueError) as e:
            return False, self._failure(e)

    def _zone(self, domain: str) -> str:
        # No zone lookup: the zone is the registrable domain under the name.
        return self.get_zone_for_domain(domain) or domain

    def create_txt_record(self, domain: str, record_name: str, record_value: str, ttl: int = 300) -> Tuple[bool, str]:
        zone = self._zone(domain)
        host = self.get_relative_record_name(record_name, zone)
        data = {'create_host_records_payload': {
            'HOST': host, 'TYPE': 'TXT', 'DATA': record_value, 'TTL': ttl, 'AUX': 0}}
        success, result = self._request('POST', f'/domains/{zone}/records', data=data)
        if not success:
            return False, f"Failed to create record: {result}"
        return True, "Record created successfully"

    def delete_txt_record(self, domain: str, record_name: str, record_value: str) -> Tuple[bool, str]:
        zone = self._zone(domain)
        success, result = self._request('GET', f'/domains/{zone}/records')
        if not success:
            return False, f"Failed to list records: {result}"
        listing = (result or {}).get('data') or {}
        if 'records' not in listing:
            # A registry error comes back inside the 200 answer, without records.
            return False, f"Failed to list records: {listing.get('description') or listing.get('code')}"
        host = self.get_relative_record_name(record_name, zone)
        for rec in listing['records'] or []:
            if (rec.get('type') == 'TXT' and rec.get('name') == host
                    and self.txt_matches(rec.get('data'), record_value)):
                success, result = self._request('DELETE', f'/domains/{zone}/records', params={'ID': rec['id']})
                if not success:
                    logger.warning(f"Epik: failed to delete TXT value of {record_name}: {result}")
                    return False, f"Failed to delete record: {result}"
        return True, "Record deleted successfully"

    def test_connection(self) -> Tuple[bool, str]:
        success, result = self._request('GET', '/domains')
        if success:
            return True, "Connected successfully"
        return False, f"Connection failed: {result}"

    @classmethod
    def get_credential_schema(cls):
        return [
            {'name': 'api_key', 'label': 'API Key', 'type': 'password', 'required': True,
             'help': 'Epik > Account > API key'},
        ]
