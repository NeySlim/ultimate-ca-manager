"""
RcodeZero DNS Provider
Uses RcodeZero Anycast DNS API v2
https://my.rcodezero.at/openapi (spec: /openapi/rcode0api-v2.json)
"""
import requests
from typing import Tuple, Dict, Any, List, Optional
import logging

from .base import BaseDnsProvider

logger = logging.getLogger(__name__)


class RcodeZeroDnsProvider(BaseDnsProvider):
    PROVIDER_TYPE = "rcodezero"
    PROVIDER_NAME = "RcodeZero"
    PROVIDER_DESCRIPTION = "RcodeZero Anycast DNS API (Austria)"
    REQUIRED_CREDENTIALS = ["api_token"]

    # Version 1 is deprecated except for its ACME calls.
    BASE_URL = "https://my.rcodezero.at/api/v2"
    MAX_PAGES = 50

    def _get_headers(self) -> Dict[str, str]:
        return {
            'Authorization': f'Bearer {self.credentials["api_token"]}',
            'Content-Type': 'application/json',
        }

    def _request(self, method: str, path: str, data: Optional[Any] = None,
                 params: Optional[Dict] = None) -> Tuple[bool, Any]:
        url = f"{self.BASE_URL}{path}"
        try:
            resp = requests.request(method=method, url=url, headers=self._get_headers(), json=data,
                                    params=params, timeout=30)
            if resp.status_code >= 400:
                return False, self._error(resp)
            body = resp.json() if resp.text else None
            # A refused rrset change answers 200 with status "failed".
            if isinstance(body, dict) and body.get('status') == 'failed':
                return False, self.redact_secrets(body.get('message') or 'failed')
            return True, body
        except (requests.RequestException, ValueError) as e:
            return False, self._failure(e)

    def _pages(self, path: str, params: Dict) -> Tuple[bool, Any]:
        """Every `data` item of a paginated listing (current_page / last_page)."""
        items: List[Dict] = []
        for page in range(1, self.MAX_PAGES + 1):
            success, result = self._request('GET', path, params={**params, 'page': page, 'page_size': 100})
            if not success:
                return False, result
            items.extend((result or {}).get('data') or [])
            if page >= int((result or {}).get('last_page') or 1):
                return True, items
        return False, f"More than {self.MAX_PAGES} pages at {path}"

    def _find_zone(self, domain: str) -> Optional[str]:
        success, zones = self._pages('/zones', {})
        if not success:
            return None
        z = self.find_zone(domain, zones, key=lambda zone: zone.get('domain', ''))
        return z['domain'].rstrip('.') if z else None

    def _get_txt_rrset(self, zone: str, fqdn: str) -> Tuple[bool, Any]:
        """The TXT rrset of `fqdn` (None if absent)."""
        success, rrsets = self._pages(f'/zones/{zone}/rrsets', {'names': fqdn, 'types': 'TXT'})
        if not success:
            return False, rrsets
        for rr in rrsets:
            if rr.get('type') == 'TXT' and rr.get('name', '').rstrip('.').lower() == fqdn.rstrip('.').lower():
                return True, rr
        return True, None

    @staticmethod
    def _records(rrset) -> List[Dict]:
        return [{'content': r.get('content'), 'disabled': bool(r.get('disabled'))}
                for r in (rrset or {}).get('records') or []]

    def create_txt_record(self, domain: str, record_name: str, record_value: str, ttl: int = 300) -> Tuple[bool, str]:
        zone = self._find_zone(domain)
        if not zone:
            return False, f"Could not find zone for {domain}"
        fqdn = record_name if record_name.endswith('.') else record_name + '.'
        success, rrset = self._get_txt_rrset(zone, fqdn)
        if not success:
            return False, f"Failed to read existing records: {rrset}"
        records = self._records(rrset)
        if any(self.txt_matches(r['content'], record_value) for r in records):
            return True, "Record already present"
        # Only whole rrsets are written: a second value is an update carrying the first.
        new = {'content': f'"{record_value}"', 'disabled': False}
        if rrset:
            data = [{'name': fqdn, 'type': 'TXT', 'ttl': rrset.get('ttl', ttl),
                     'changetype': 'update', 'records': records + [new]}]
        else:
            data = [{'name': fqdn, 'type': 'TXT', 'ttl': ttl, 'changetype': 'add', 'records': [new]}]
        success, result = self._request('PATCH', f'/zones/{zone}/rrsets', data)
        if not success:
            return False, f"Failed to create record: {result}"
        return True, "Record created successfully"

    def delete_txt_record(self, domain: str, record_name: str, record_value: str) -> Tuple[bool, str]:
        zone = self._find_zone(domain)
        if not zone:
            return False, f"Could not find zone for {domain}"
        fqdn = record_name if record_name.endswith('.') else record_name + '.'
        success, rrset = self._get_txt_rrset(zone, fqdn)
        if not success:
            return False, f"Failed to read existing records: {rrset}"
        records = self._records(rrset)
        remaining = [r for r in records if not self.txt_matches(r['content'], record_value)]
        if len(remaining) == len(records):
            return True, "Record not found (already deleted?)"
        ttl = rrset.get('ttl', 300)
        if remaining:
            data = [{'name': fqdn, 'type': 'TXT', 'ttl': ttl, 'changetype': 'update', 'records': remaining}]
        else:
            data = [{'name': fqdn, 'type': 'TXT', 'ttl': ttl, 'changetype': 'delete'}]
        success, result = self._request('PATCH', f'/zones/{zone}/rrsets', data)
        if not success:
            logger.warning(f"RcodeZero: failed to delete TXT value of {record_name}: {result}")
            return False, f"Failed to delete record: {result}"
        return True, "Record deleted successfully"

    def test_connection(self) -> Tuple[bool, str]:
        success, zones = self._pages('/zones', {})
        if success:
            return True, f"Connected. Found {len(zones)} zone(s)"
        return False, f"Connection failed: {zones}"

    @classmethod
    def get_credential_schema(cls):
        return [
            {'name': 'api_token', 'label': 'API Token', 'type': 'password', 'required': True,
             'help': 'my.rcodezero.at > API Tokens'},
        ]
