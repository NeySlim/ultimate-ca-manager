"""
Vercel DNS Provider
https://vercel.com/docs/rest-api/endpoints/dns
"""
import requests
from typing import Tuple, Dict, Any
import logging

from .base import BaseDnsProvider

logger = logging.getLogger(__name__)


class VercelDnsProvider(BaseDnsProvider):
    PROVIDER_TYPE = "vercel"
    PROVIDER_NAME = "Vercel"
    PROVIDER_DESCRIPTION = "Vercel DNS API"
    REQUIRED_CREDENTIALS = ["api_token"]
    OPTIONAL_CREDENTIALS = ["team_id"]
    
    BASE_URL = "https://api.vercel.com"
    MAX_PAGES = 50
    
    def _get_headers(self):
        return {
            'Authorization': f'Bearer {self.credentials["api_token"]}',
            'Content-Type': 'application/json',
        }
    
    def _request(self, method, path, data=None, params=None):
        # Domains owned by a team are only reachable on its behalf (teamId on every call).
        team = (self.credentials.get('team_id') or '').strip()
        if team:
            params = {**(params or {}), 'teamId': team}
        try:
            resp = requests.request(method, f"{self.BASE_URL}{path}",
                headers=self._get_headers(), json=data, params=params, timeout=30)
            if resp.status_code >= 400:
                return False, self._error(resp)
            return True, resp.json() if resp.text else None
        except (requests.RequestException, ValueError) as e:
            logger.error(f"Vercel API error: {self._failure(e)}")
            return False, self._failure(e)
    
    def _records(self, zone):
        """Every record of the zone: `pagination.next` is the `until` timestamp of the next page."""
        records, params = [], {}
        for _ in range(self.MAX_PAGES):
            success, result = self._request('GET', f'/v5/domains/{zone}/records', params=params)
            if not success:
                return False, result
            if not isinstance(result, dict):
                return False, f"Unexpected answer: {str(result)[:200]}"
            records.extend(result.get('records') or [])
            nxt = (result.get('pagination') or {}).get('next')
            if not nxt or str(nxt) == params.get('until'):
                return True, records
            params = {'until': str(nxt)}
        return False, f"More than {self.MAX_PAGES} pages of records in {zone}"

    def create_txt_record(self, domain, record_name, record_value, ttl=300):
        zone = self.get_zone_for_domain(domain)
        relative = self.get_relative_record_name(record_name, zone)
        data = {'name': relative, 'type': 'TXT', 'value': record_value, 'ttl': ttl}
        success, result = self._request('POST', f'/v2/domains/{zone}/records', data)
        if not success:
            msg = f"Failed: {result}"
            logger.warning(f"Vercel: {msg}")
            return False, msg
        return True, "Record created"
    
    def delete_txt_record(self, domain, record_name, record_value):
        zone = self.get_zone_for_domain(domain)
        relative = self.get_relative_record_name(record_name, zone)
        
        success, records = self._records(zone)
        if not success:
            msg = f"Failed to list records: {records}"
            logger.warning(f"Vercel: {msg}")
            return False, msg
        for rec in records:
            if (rec.get('type') == 'TXT' and rec.get('name') == relative
                    and self.txt_matches(rec.get('value'), record_value)):
                ok, err = self._request('DELETE', f'/v2/domains/{zone}/records/{rec["id"]}')
                if not ok:
                    logger.warning(f"Vercel: failed to delete TXT value of {record_name}: {err}")
                    return False, f"Failed to delete record: {err}"
        return True, "Record deleted"
    
    def test_connection(self):
        success, result = self._request('GET', '/v5/domains')
        if success:
            domains = [d['name'] for d in result.get('domains', [])]
            return True, f"Connected. Domains: {', '.join(domains)}"
        return False, f"Connection failed: {result}"
    
    @classmethod
    def get_credential_schema(cls):
        return [
            {'name': 'api_token', 'label': 'API Token', 'type': 'password', 'required': True,
             'help': 'vercel.com > Settings > Tokens'},
            {'name': 'team_id', 'label': 'Team ID', 'type': 'text', 'required': False,
             'help': 'Only for domains owned by a team: the team ID from its settings (team_...)'},
        ]
