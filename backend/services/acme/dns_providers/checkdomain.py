"""
Checkdomain DNS Provider (Germany)
https://developer.checkdomain.de/reference (v1: domains, nameservers, records)
"""
import requests
from typing import Tuple, Dict, Any, List
import logging

from .base import BaseDnsProvider

logger = logging.getLogger(__name__)


class CheckdomainDnsProvider(BaseDnsProvider):
    PROVIDER_TYPE = "checkdomain"
    PROVIDER_NAME = "Checkdomain"
    PROVIDER_DESCRIPTION = "Checkdomain DNS API (Germany)"
    REQUIRED_CREDENTIALS = ["api_token"]

    BASE_URL = "https://api.checkdomain.de/v1"
    PAGE_LIMIT = 100
    MAX_PAGES = 50

    def _get_headers(self):
        return {
            'Authorization': f'Bearer {self.credentials["api_token"]}',
            'Content-Type': 'application/json',
        }

    def _request(self, method, path, data=None, params=None):
        try:
            resp = requests.request(method, f"{self.BASE_URL}{path}",
                headers=self._get_headers(), json=data, params=params, timeout=30)
            if resp.status_code >= 400:
                return False, self._error(resp)
            return True, resp.json() if resp.text and resp.status_code not in (201, 204) else None
        except (requests.RequestException, ValueError) as e:
            logger.error(f"Checkdomain API error: {self._failure(e)}")
            return False, self._failure(e)

    def _list(self, path, key, params=None) -> Tuple[bool, Any]:
        """Every `_embedded[key]` item of a listing paginated by page/limit/pages."""
        items: List[Dict] = []
        for page in range(1, self.MAX_PAGES + 1):
            success, result = self._request('GET', path, params={**(params or {}), 'page': page,
                                                                 'limit': self.PAGE_LIMIT})
            if not success:
                return False, result
            items.extend(((result or {}).get('_embedded') or {}).get(key) or [])
            if page >= int((result or {}).get('pages') or 1):
                return True, items
        return False, f"More than {self.MAX_PAGES} pages at {path}"

    def _find_domain(self, domain):
        success, domains = self._list('/domains', 'domains')
        if not success:
            return None
        d = self.find_zone(domain, domains, key=lambda z: z.get('name', ''))
        return (d['id'], d['name']) if d else None

    def create_txt_record(self, domain, record_name, record_value, ttl=300):
        info = self._find_domain(domain)
        if not info:
            return False, f"Domain not found for {domain}"
        domain_id, zone = info
        relative = self.get_relative_record_name(record_name, zone)
        data = {'name': relative, 'type': 'TXT', 'value': record_value, 'ttl': ttl, 'priority': 0}
        success, result = self._request('POST', f'/domains/{domain_id}/nameservers/records', data)
        if not success:
            return False, f"Failed: {result}"
        return True, "Record created"

    @staticmethod
    def _kept(rec, include_www) -> bool:
        """Whether a listed record goes back in the replacing PUT (as lego does).

        SOA, NS, `@` and, with include_www, `www` are generated from the nameserver
        settings: sending them back makes the update fail.
        """
        if not rec.get('value'):
            return False
        if rec.get('type') in ('SOA', 'NS') or rec.get('name') == '@':
            return False
        return not (include_www and rec.get('name') == 'www')

    def delete_txt_record(self, domain, record_name, record_value):
        info = self._find_domain(domain)
        if not info:
            return False, f"Domain not found for {domain}"
        domain_id, zone = info
        relative = self.get_relative_record_name(record_name, zone)
        base = f'/domains/{domain_id}/nameservers'

        success, records = self._list(f'{base}/records', 'records')
        if not success:
            logger.warning(f"Checkdomain: failed to list records of {zone}: {records}")
            return False, f"Failed to list records: {records}"
        target = [r for r in records if r.get('type') == 'TXT' and r.get('name') == relative
                  and self.txt_matches(r.get('value'), record_value)]
        if not target:
            return True, "Record already absent"

        # No per-record DELETE: the only removal is a PUT replacing every record.
        success, ns = self._request('GET', base)
        if not success:
            logger.warning(f"Checkdomain: failed to read nameserver settings of {zone}: {ns}")
            return False, f"Failed to read nameserver settings: {ns}"
        include_www = bool(((ns or {}).get('general') or {}).get('include_www'))
        soa_ttl = ((ns or {}).get('soa') or {}).get('ttl')
        keep = []
        for rec in records:
            if any(rec is t for t in target) or not self._kept(rec, include_www):
                continue
            ttl = rec.get('ttl') or soa_ttl  # a ttl of 0 is refused on the way back
            keep.append({'name': rec.get('name'), 'value': rec.get('value'), 'ttl': ttl,
                         'priority': rec.get('priority', 0), 'type': rec.get('type')})
        success, result = self._request('PUT', f'{base}/records', keep)
        if not success:
            logger.warning(f"Checkdomain: failed to delete TXT value of {record_name}: {result}")
            return False, f"Failed to delete record: {result}"
        return True, "Record deleted"

    def test_connection(self):
        success, result = self._request('GET', '/domains', params={'limit': 1})
        if success:
            return True, "Connected successfully"
        return False, f"Connection failed: {result}"

    @classmethod
    def get_credential_schema(cls):
        return [
            {'name': 'api_token', 'label': 'API Token', 'type': 'password', 'required': True,
             'help': 'checkdomain.de > API Access'},
        ]
