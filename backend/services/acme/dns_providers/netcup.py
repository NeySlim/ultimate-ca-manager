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
            logger.error(f"Netcup API request failed: {e}")
            return False, str(e)
    
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
    
    def create_txt_record(
        self, 
        domain: str, 
        record_name: str, 
        record_value: str, 
        ttl: int = 300
    ) -> Tuple[bool, str]:
        """Create TXT record via Netcup API"""
        success, msg = self._login()
        if not success:
            return False, f"Login failed: {msg}"
        
        try:
            # Get relative hostname
            if record_name.endswith('.' + domain):
                hostname = record_name[:-len(domain) - 1]
            elif record_name == domain:
                hostname = '@'
            else:
                hostname = record_name
            
            params = self._get_base_params()
            params['domainname'] = domain
            params['dnsrecordset'] = {
                'dnsrecords': [{
                    'hostname': hostname,
                    'type': 'TXT',
                    'destination': record_value,
                    'priority': '',
                    'state': 'yes'
                }]
            }
            
            success, result = self._rpc_call('updateDnsRecords', params)
            
            if not success:
                return False, f"Failed to create record: {result}"
            
            logger.info(f"Netcup: Created TXT record {record_name}")
            return True, "Record created successfully"
            
        finally:
            self._logout()
    
    def delete_txt_record(self, domain: str, record_name: str) -> Tuple[bool, str]:
        """Delete TXT record via Netcup API"""
        success, msg = self._login()
        if not success:
            return False, f"Login failed: {msg}"
        
        try:
            # Get relative hostname
            if record_name.endswith('.' + domain):
                hostname = record_name[:-len(domain) - 1]
            elif record_name == domain:
                hostname = '@'
            else:
                hostname = record_name
            
            params = self._get_base_params()
            params['domainname'] = domain
            params['dnsrecordset'] = {
                'dnsrecords': [{
                    'hostname': hostname,
                    'type': 'TXT',
                    'destination': '',
                    'state': 'no',
                    'deleterecord': True
                }]
            }
            
            success, result = self._rpc_call('updateDnsRecords', params)
            
            if not success:
                if 'not found' in str(result).lower():
                    return True, "Record not found (already deleted?)"
                return False, f"Failed to delete record: {result}"
            
            logger.info(f"Netcup: Deleted TXT record {record_name}")
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
