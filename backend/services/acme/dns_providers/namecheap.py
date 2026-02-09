"""
Namecheap DNS Provider
https://www.namecheap.com/support/api/methods.aspx
"""
import requests
import xml.etree.ElementTree as ET
from typing import Tuple, Dict, Any, Optional, List
import logging

from .base import BaseDnsProvider

logger = logging.getLogger(__name__)


class NamecheapDnsProvider(BaseDnsProvider):
    """
    Namecheap DNS Provider.
    
    Required credentials:
    - api_user: Namecheap API User
    - api_key: Namecheap API Key
    - client_ip: Your whitelisted IP address
    
    Get credentials at: namecheap.com > Profile > Tools > API Access
    
    Note: Requires $50+ balance, 20+ domains, or $50+ purchases in last 2 years.
    """
    
    PROVIDER_TYPE = "namecheap"
    PROVIDER_NAME = "Namecheap"
    PROVIDER_DESCRIPTION = "Namecheap DNS API"
    REQUIRED_CREDENTIALS = ["api_user", "api_key", "client_ip"]
    
    BASE_URL = "https://api.namecheap.com/xml.response"
    SANDBOX_URL = "https://api.sandbox.namecheap.com/xml.response"
    
    def __init__(self, credentials: Dict[str, Any]):
        super().__init__(credentials)
        self._use_sandbox = credentials.get('sandbox', False)
    
    def _get_api_url(self) -> str:
        return self.SANDBOX_URL if self._use_sandbox else self.BASE_URL
    
    def _make_request(self, command: str, extra_params: Optional[Dict] = None) -> Tuple[bool, Any]:
        """Make Namecheap API request"""
        params = {
            'ApiUser': self.credentials['api_user'],
            'ApiKey': self.credentials['api_key'],
            'UserName': self.credentials['api_user'],
            'ClientIp': self.credentials['client_ip'],
            'Command': command,
        }
        
        if extra_params:
            params.update(extra_params)
        
        try:
            response = requests.get(
                self._get_api_url(),
                params=params,
                timeout=60
            )
            
            if response.status_code >= 400:
                return False, f"HTTP {response.status_code}: {response.reason}"
            
            # Parse XML response
            root = ET.fromstring(response.text)
            
            # Check for errors
            status = root.attrib.get('Status', '')
            if status.lower() == 'error':
                errors = root.findall('.//Error')
                if errors:
                    error_msg = errors[0].text or 'Unknown error'
                    return False, error_msg
                return False, 'Unknown API error'
            
            return True, root
            
        except ET.ParseError as e:
            logger.error(f"Namecheap XML parse failed: {e}")
            return False, f"XML parse error: {e}"
        except requests.RequestException as e:
            logger.error(f"Namecheap API request failed: {e}")
            return False, str(e)
    
    def _parse_domain(self, domain: str) -> Tuple[str, str]:
        """Parse domain into SLD and TLD"""
        parts = domain.split('.')
        if len(parts) >= 2:
            tld = parts[-1]
            sld = '.'.join(parts[:-1])
            return sld, tld
        return domain, ''
    
    def _get_existing_records(self, sld: str, tld: str) -> List[Dict]:
        """Get existing DNS records for a domain"""
        success, result = self._make_request(
            'namecheap.domains.dns.getHosts',
            {'SLD': sld, 'TLD': tld}
        )
        
        if not success:
            return []
        
        records = []
        for host in result.findall('.//host'):
            records.append({
                'HostName': host.attrib.get('Name', ''),
                'RecordType': host.attrib.get('Type', ''),
                'Address': host.attrib.get('Address', ''),
                'TTL': host.attrib.get('TTL', '1800'),
                'MXPref': host.attrib.get('MXPref', '10'),
            })
        
        return records
    
    def create_txt_record(
        self, 
        domain: str, 
        record_name: str, 
        record_value: str, 
        ttl: int = 1800
    ) -> Tuple[bool, str]:
        """Create TXT record via Namecheap API"""
        # Parse domain
        sld, tld = self._parse_domain(domain)
        
        # Get relative name
        if record_name.endswith('.' + domain):
            host_name = record_name[:-len(domain) - 1]
        elif record_name == domain:
            host_name = '@'
        else:
            host_name = record_name
        
        # Get existing records
        existing_records = self._get_existing_records(sld, tld)
        
        # Add new record
        existing_records.append({
            'HostName': host_name,
            'RecordType': 'TXT',
            'Address': record_value,
            'TTL': str(max(ttl, 60)),
        })
        
        # Build params for all records
        params = {'SLD': sld, 'TLD': tld}
        for i, record in enumerate(existing_records, 1):
            params[f'HostName{i}'] = record['HostName']
            params[f'RecordType{i}'] = record['RecordType']
            params[f'Address{i}'] = record['Address']
            params[f'TTL{i}'] = record.get('TTL', '1800')
            if record['RecordType'] == 'MX':
                params[f'MXPref{i}'] = record.get('MXPref', '10')
        
        success, result = self._make_request('namecheap.domains.dns.setHosts', params)
        
        if not success:
            return False, f"Failed to create record: {result}"
        
        logger.info(f"Namecheap: Created TXT record {record_name}")
        return True, "Record created successfully"
    
    def delete_txt_record(self, domain: str, record_name: str) -> Tuple[bool, str]:
        """Delete TXT record via Namecheap API"""
        # Parse domain
        sld, tld = self._parse_domain(domain)
        
        # Get relative name
        if record_name.endswith('.' + domain):
            host_name = record_name[:-len(domain) - 1]
        elif record_name == domain:
            host_name = '@'
        else:
            host_name = record_name
        
        # Get existing records
        existing_records = self._get_existing_records(sld, tld)
        
        # Filter out the TXT record to delete
        filtered_records = [
            r for r in existing_records
            if not (r['RecordType'] == 'TXT' and r['HostName'] == host_name)
        ]
        
        if len(filtered_records) == len(existing_records):
            return True, "Record not found (already deleted?)"
        
        # Build params for remaining records
        params = {'SLD': sld, 'TLD': tld}
        for i, record in enumerate(filtered_records, 1):
            params[f'HostName{i}'] = record['HostName']
            params[f'RecordType{i}'] = record['RecordType']
            params[f'Address{i}'] = record['Address']
            params[f'TTL{i}'] = record.get('TTL', '1800')
            if record['RecordType'] == 'MX':
                params[f'MXPref{i}'] = record.get('MXPref', '10')
        
        success, result = self._make_request('namecheap.domains.dns.setHosts', params)
        
        if not success:
            return False, f"Failed to delete record: {result}"
        
        logger.info(f"Namecheap: Deleted TXT record {record_name}")
        return True, "Record deleted successfully"
    
    def test_connection(self) -> Tuple[bool, str]:
        """Test Namecheap API connection"""
        success, result = self._make_request('namecheap.domains.getList')
        if success:
            domains = result.findall('.//Domain')
            domain_names = [d.attrib.get('Name', '') for d in domains]
            return True, f"Connected successfully. Found {len(domains)} domain(s): {', '.join(domain_names[:5])}"
        return False, f"Connection failed: {result}"
    
    @classmethod
    def get_credential_schema(cls):
        return [
            {'name': 'api_user', 'label': 'API User', 'type': 'text', 'required': True,
             'help': 'Namecheap username'},
            {'name': 'api_key', 'label': 'API Key', 'type': 'password', 'required': True,
             'help': 'namecheap.com > Profile > Tools > API Access'},
            {'name': 'client_ip', 'label': 'Client IP', 'type': 'text', 'required': True,
             'help': 'Your whitelisted IP address'},
            {'name': 'sandbox', 'label': 'Use Sandbox', 'type': 'checkbox', 'required': False,
             'help': 'Use sandbox environment for testing'},
        ]
