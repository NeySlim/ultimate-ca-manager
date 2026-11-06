"""
Constellix DNS Provider
Uses Constellix DNS v4 API with HMAC-SHA1 authentication
https://api.dns.constellix.com/v4/docs
"""
import requests
import hmac
import hashlib
import base64
import time
from typing import Tuple, Dict, Any, List, Optional
import logging

from .base import BaseDnsProvider

logger = logging.getLogger(__name__)


class ConstellixDnsProvider(BaseDnsProvider):
    PROVIDER_TYPE = "constellix"
    PROVIDER_NAME = "Constellix"
    PROVIDER_DESCRIPTION = "Constellix Managed DNS API"
    REQUIRED_CREDENTIALS = ["api_key", "secret_key"]

    BASE_URL = "https://api.dns.constellix.com/v4"
    MAX_PAGES = 50

    def _get_headers(self) -> Dict[str, str]:
        timestamp = str(int(time.time() * 1000))
        hmac_hash = hmac.new(
            self.credentials['secret_key'].encode(),
            timestamp.encode(),
            hashlib.sha1
        ).digest()
        token = base64.b64encode(hmac_hash).decode()
        return {
            'Authorization': f'Bearer {self.credentials["api_key"]}:{token}:{timestamp}',
            'Content-Type': 'application/json',
        }

    def _request(self, method: str, path: str, data: Optional[Dict] = None,
                 params: Optional[Dict] = None) -> Tuple[bool, Any]:
        url = f"{self.BASE_URL}{path}"
        try:
            resp = requests.request(method=method, url=url, headers=self._get_headers(),
                                    json=data, params=params, timeout=30)
            if resp.status_code >= 400:
                return False, self._error(resp)
            return True, resp.json() if resp.text else None
        except (requests.RequestException, ValueError) as e:
            return False, self._failure(e)

    def _list(self, path: str) -> Tuple[bool, Any]:
        """Every item of a paginated listing; `meta.links.next` is null on the last page."""
        items: List[Dict] = []
        for page in range(1, self.MAX_PAGES + 1):
            success, result = self._request('GET', path, params={'page': page})
            if not success:
                return False, result
            items.extend((result or {}).get('data') or [])
            links = ((result or {}).get('meta') or {}).get('links') or {}
            if not links.get('next'):
                return True, items
        return False, f"More than {self.MAX_PAGES} pages at {path}"

    def _find_domain(self, domain: str) -> Optional[Dict]:
        success, domains = self._list('/domains')
        if not success:
            return None
        return self.find_zone(domain, domains, key=lambda d: d.get('name'))

    def _txt_record(self, dom: Dict, relative: str) -> Tuple[bool, Any]:
        """The domain's TXT record named `relative` (one record holds every value), or None."""
        success, records = self._list(f'/domains/{dom["id"]}/records')
        if not success:
            return False, records
        for rec in records:
            if rec.get('type') == 'TXT' and (rec.get('name') or '') == relative:
                return True, rec
        return True, None

    def _write_values(self, dom: Dict, rec: Dict, relative: str, values: List[Dict]) -> Tuple[bool, Any]:
        body = {'name': relative, 'type': 'TXT', 'ttl': rec.get('ttl', 300),
                'mode': rec.get('mode') or 'standard', 'value': values}
        return self._request('PUT', f'/domains/{dom["id"]}/records/{rec["id"]}', body)

    def create_txt_record(self, domain: str, record_name: str, record_value: str, ttl: int = 300) -> Tuple[bool, str]:
        dom = self._find_domain(domain)
        if not dom:
            return False, f"Could not find domain {domain}"
        relative = self.get_relative_record_name(record_name, dom['name'])
        success, rec = self._txt_record(dom, relative)
        if not success:
            return False, f"Failed to list records: {rec}"
        entry = {'value': record_value, 'enabled': True}
        if rec is None:
            body = {'name': relative, 'type': 'TXT', 'ttl': ttl, 'mode': 'standard', 'value': [entry]}
            success, result = self._request('POST', f'/domains/{dom["id"]}/records', body)
        else:
            # A second value under the name joins the existing record's value list.
            values = list(rec.get('value') or [])
            if any(self.txt_matches(v.get('value'), record_value) for v in values):
                return True, "Record already present"
            success, result = self._write_values(dom, rec, relative, values + [entry])
        if not success:
            return False, f"Failed to create record: {result}"
        return True, "Record created successfully"

    def delete_txt_record(self, domain: str, record_name: str, record_value: str) -> Tuple[bool, str]:
        dom = self._find_domain(domain)
        if not dom:
            return False, f"Could not find domain {domain}"
        relative = self.get_relative_record_name(record_name, dom['name'])
        success, rec = self._txt_record(dom, relative)
        if not success:
            return False, f"Failed to list records: {rec}"
        if rec is None:
            return True, "Record already absent"
        values = list(rec.get('value') or [])
        remaining = [v for v in values if not self.txt_matches(v.get('value'), record_value)]
        if len(remaining) == len(values):
            return True, "Record already absent"
        if remaining:
            success, result = self._write_values(dom, rec, relative, remaining)
        else:
            success, result = self._request('DELETE', f'/domains/{dom["id"]}/records/{rec["id"]}')
        if not success:
            logger.warning(f"Constellix: failed to delete TXT value of {record_name}: {result}")
            return False, f"Failed to delete record: {result}"
        return True, "Record deleted successfully"

    def test_connection(self) -> Tuple[bool, str]:
        success, result = self._list('/domains')
        if success:
            return True, f"Connected. Found {len(result)} domain(s)"
        return False, f"Connection failed: {result}"

    @classmethod
    def get_credential_schema(cls):
        return [
            {'name': 'api_key', 'label': 'API Key', 'type': 'password', 'required': True},
            {'name': 'secret_key', 'label': 'Secret Key', 'type': 'password', 'required': True,
             'help': 'Constellix portal > User Administration > API'},
        ]
