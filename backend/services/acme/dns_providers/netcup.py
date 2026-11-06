"""
Netcup DNS Provider
German hosting provider with JSON-RPC API
https://www.netcup-wiki.de/wiki/DNS_API
"""
import requests
from typing import Tuple, Dict, Any, Optional
import logging

from .base import BaseDnsProvider

logger = logging.getLogger(__name__)


class NetcupDnsProvider(BaseDnsProvider):
    """
    Netcup DNS Provider (Germany).
    
    Required credentials:
    - customer_number: Netcup Customer Number
    - api_key: Netcup API Key
    - api_password: Netcup API Password
    
    Get credentials at: customercontrolpanel.de > Stammdaten > API
    """
    
    PROVIDER_TYPE = "netcup"
    PROVIDER_NAME = "Netcup"
    PROVIDER_DESCRIPTION = "Netcup DNS API (Germany)"
    REQUIRED_CREDENTIALS = ["customer_number", "api_key", "api_password"]
    
    BASE_URL = "https://ccp.netcup.net/run/webservice/servers/endpoint.php?JSON"
    
    def __init__(self, credentials: Dict[str, Any]):
        super().__init__(credentials)
        self._session_id: Optional[str] = None
    
    def _rpc_call(self, action: str, params: Dict) -> Tuple[bool, Any]:
        """Make Netcup JSON-RPC API call"""
        payload = {
            'action': action,
            'param': params
        }
        
        try:
            response = requests.post(
                self.BASE_URL,
                json=payload,
                timeout=30,
                headers={'Content-Type': 'application/json'}
            )
            
            if response.status_code >= 400:
                return False, f"HTTP {response.status_code}: {response.reason}"
            
            result = response.json()
            
            if result.get('status') == 'error':
                return False, result.get('longmessage', result.get('shortmessage', 'Unknown error'))
            
            return True, result
            
        except requests.RequestException as e:
            logger.error(f"Netcup API request failed: {self._failure(e)}")
            return False, self._failure(e)
    
    def _login(self) -> Tuple[bool, str]:
        """Login to get session ID"""
        if self._session_id:
            return True, self._session_id
        
        success, result = self._rpc_call('login', {
            'customernumber': self.credentials['customer_number'],
            'apikey': self.credentials['api_key'],
            'apipassword': self.credentials['api_password']
        })
        
        if not success:
            return False, result
        
        self._session_id = result.get('responsedata', {}).get('apisessionid')
        if not self._session_id:
            return False, "No session ID in response"
        
        return True, self._session_id
    
    def _logout(self):
        """Logout and clear session"""
        if self._session_id:
            self._rpc_call('logout', {
                'customernumber': self.credentials['customer_number'],
                'apikey': self.credentials['api_key'],
                'apisessionid': self._session_id
            })
            self._session_id = None
    
    def _get_base_params(self) -> Dict:
        """Get base parameters for API calls"""
        return {
            'customernumber': self.credentials['customer_number'],
            'apikey': self.credentials['api_key'],
            'apisessionid': self._session_id
        }
    
    def _split_domain_and_host(
        self, record_name: str, domain_from_client: str
    ) -> Tuple[str, str]:
        """
        Splits the incoming data into the real registered Netcup base domain
        and the full relative hostname required by the Netcup API.
        Handles multi-part TLDs (e.g. .co.uk, .com.au) -- the table that knows
        about them is `BaseDnsProvider._MULTI_PART_TLDS`, shared with every
        other provider that has no zone API to ask.
        Example:
          record_name:      _acme-challenge.sub.example.co.uk
          domain_from_client: sub.example.co.uk
          Returns:          base_domain='example.co.uk', hostname='_acme-challenge.sub'
        """
        base_domain = self.get_zone_for_domain(domain_from_client) or domain_from_client

        if record_name.endswith('.' + base_domain):
            hostname = record_name[:-len(base_domain) - 1]
        elif record_name == base_domain:
            hostname = '@'
        else:
            hostname = record_name

        return base_domain, hostname
    
    def create_txt_record(
        self, 
        domain: str, 
        record_name: str, 
        record_value: str, 
        ttl: int = 300
    ) -> Tuple[bool, str]:
        """Create TXT record via Netcup API safely without overriding the zone"""
        success, msg = self._login()
        if not success:
            return False, f"Login failed: {msg}"
        
        try:
            # Dynamic splitting into main domain and relative hostname for Netcup
            real_base_domain, hostname = self._split_domain_and_host(record_name, domain)
            
            params = self._get_base_params()
            params['domainname'] = real_base_domain
            
            # 1. Query existing records of the actual main domain
            success, info_result = self._rpc_call('infoDnsRecords', params)
            if not success:
                return False, f"Failed to fetch existing records for {real_base_domain}: {info_result}"
            
            dns_records = info_result.get('responsedata', {}).get('dnsrecords', [])
            
            # 2. Remove any existing duplicate (same hostname + type + value)
            dns_records = [
                r for r in dns_records
                if not (r.get('hostname') == hostname
                        and r.get('type') == 'TXT'
                        and r.get('destination') == record_value)
            ]

            # 3. Append the new TXT record
            new_record = {
                'hostname': hostname,
                'type': 'TXT',
                'destination': record_value,
                'priority': '',
                'ttl': str(ttl),
                'state': 'yes'
            }
            dns_records.append(new_record)
            
            # 3. Write back the complete, modified set
            params['dnsrecordset'] = {'dnsrecords': dns_records}
            success, update_result = self._rpc_call('updateDnsRecords', params)
            
            if not success:
                return False, f"Failed to update records: {update_result}"
            
            logger.info(f"Netcup: Created TXT record {hostname} on {real_base_domain}")
            return True, "Record created successfully"
            
        finally:
            self._logout()
    
    def delete_txt_record(self, domain: str, record_name: str, record_value: str) -> Tuple[bool, str]:
        """Delete TXT record via Netcup API using individual internal IDs"""
        success, msg = self._login()
        if not success:
            return False, f"Login failed: {msg}"
        
        try:
            # Dynamic splitting into main domain and relative hostname for Netcup
            real_base_domain, hostname = self._split_domain_and_host(record_name, domain)
            
            params = self._get_base_params()
            params['domainname'] = real_base_domain
            
            # 1. Query existing records to find entries along with their Netcup ID
            success, info_result = self._rpc_call('infoDnsRecords', params)
            if not success:
                return False, f"Failed to fetch existing records: {info_result}"
            
            dns_records = info_result.get('responsedata', {}).get('dnsrecords', [])
            
            # 2. Flag only this value: other values of the name belong to other challenges
            record_found = False
            for record in dns_records:
                if (record.get('hostname') == hostname and 
                    record.get('type') == 'TXT' and
                    self.txt_matches(record.get('destination'), record_value)):
                    record['deleterecord'] = True
                    record_found = True
            
            if not record_found:
                return True, "Record not found (already deleted?)"
            
            # 3. Submit the modified set (including IDs and deletion flags)
            params['dnsrecordset'] = {'dnsrecords': dns_records}
            success, update_result = self._rpc_call('updateDnsRecords', params)
            
            if not success:
                if 'not found' in str(update_result).lower():
                    return True, "Record not found (already deleted?)"
                return False, f"Failed to delete record: {update_result}"
            
            logger.info(f"Netcup: Deleted TXT record {hostname} from {real_base_domain}")
            return True, "Record deleted successfully"
            
        finally:
            self._logout()
    
    def test_connection(self) -> Tuple[bool, str]:
        """Test Netcup API connection"""
        success, msg = self._login()
        if success:
            self._logout()
            return True, "Connected successfully"
        return False, f"Connection failed: {msg}"
    
    @classmethod
    def get_credential_schema(cls):
        return [
            {'name': 'customer_number', 'label': 'Customer Number', 'type': 'text', 'required': True,
             'help': 'Netcup customer number'},
            {'name': 'api_key', 'label': 'API Key', 'type': 'text', 'required': True,
             'help': 'customercontrolpanel.de > Stammdaten > API'},
            {'name': 'api_password', 'label': 'API Password', 'type': 'password', 'required': True,
             'help': 'API Password (not your login password)'},
        ]
