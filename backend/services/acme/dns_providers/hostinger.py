"""
Hostinger DNS Provider
Uses the Hostinger API DNS zone endpoints
https://developers.hostinger.com/ (DNS > Zone)
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

    BASE_URL = "https://developers.hostinger.com"

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
                return False, self._error(resp)
            return True, resp.json() if resp.text else None
        except (requests.RequestException, ValueError) as e:
            return False, self._failure(e)

    def _zone(self, domain: str) -> str:
        # No zone lookup in the DNS API: the zone is the registrable domain.
        return self.get_zone_for_domain(domain) or domain

    @staticmethod
    def _kept(record: Dict) -> Dict:
        # PUT documents only `content`; a disabled value says so rather than come back enabled.
        kept = {'content': record.get('content')}
        if record.get('is_disabled'):
            kept['is_disabled'] = True
        return kept

    def create_txt_record(self, domain: str, record_name: str, record_value: str, ttl: int = 300) -> Tuple[bool, str]:
        zone = self._zone(domain)
        relative = self.get_relative_record_name(record_name, zone)
        # overwrite=false appends the value to the name's TXT records instead of replacing them.
        data = {'overwrite': False, 'zone': [
            {'name': relative, 'type': 'TXT', 'ttl': ttl, 'records': [{'content': record_value}]}]}
        success, result = self._request('PUT', f'/api/dns/v1/zones/{zone}', data)
        if not success:
            return False, f"Failed to create record: {result}"
        return True, "Record created successfully"

    def delete_txt_record(self, domain: str, record_name: str, record_value: str) -> Tuple[bool, str]:
        zone = self._zone(domain)
        path = f'/api/dns/v1/zones/{zone}'
        success, rrsets = self._request('GET', path)
        if not success:
            msg = f"Failed to list records: {rrsets}"
            logger.warning(f"Hostinger: {msg}")
            return False, msg
        relative = self.get_relative_record_name(record_name, zone)
        for rrset in rrsets or []:
            if rrset.get('type') != 'TXT' or rrset.get('name') != relative:
                continue
            records = rrset.get('records') or []
            remaining = [r for r in records if not self.txt_matches(r.get('content'), record_value)]
            if len(remaining) == len(records):
                continue
            if remaining:
                # The delete endpoint takes only name and type: keep the others by rewriting the set.
                data = {'overwrite': True, 'zone': [
                    {'name': relative, 'type': 'TXT', 'ttl': rrset.get('ttl', 300),
                     'records': [self._kept(r) for r in remaining]}]}
                success, result = self._request('PUT', path, data)
            else:
                success, result = self._request(
                    'DELETE', path, {'filters': [{'name': relative, 'type': 'TXT'}]})
            if not success:
                logger.warning(f"Hostinger: failed to delete TXT value of {record_name}: {result}")
                return False, f"Failed to delete record: {result}"
        return True, "Record deleted successfully"

    def test_connection(self) -> Tuple[bool, str]:
        success, result = self._request('GET', '/api/domains/v1/portfolio')
        if success:
            return True, "Connected successfully"
        return False, f"Connection failed: {result}"

    @classmethod
    def get_credential_schema(cls):
        return [
            {'name': 'api_token', 'label': 'API Token', 'type': 'password', 'required': True,
             'help': 'hPanel > Account > API Token'},
        ]
