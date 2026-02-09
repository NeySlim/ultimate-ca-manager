"""
FreeDNS (afraid.org) DNS Provider
Free dynamic DNS service
https://freedns.afraid.org/
"""
import requests
import hashlib
from typing import Tuple, Dict, Any, Optional, List
import logging

from .base import BaseDnsProvider

logger = logging.getLogger(__name__)


class FreeDnsDnsProvider(BaseDnsProvider):
    """
    FreeDNS (afraid.org) DNS Provider.
    
    Required credentials:
    - username: FreeDNS username
    - password: FreeDNS password
    
    Note: FreeDNS uses a token-based update system.
    This provider uses the API v2 interface for TXT record management.
    
    API documentation: freedns.afraid.org/api/
    """
    
    PROVIDER_TYPE = "freedns"
    PROVIDER_NAME = "FreeDNS"
    PROVIDER_DESCRIPTION = "FreeDNS afraid.org (Free DNS)"
    REQUIRED_CREDENTIALS = ["username", "password"]
    
    BASE_URL = "https://freedns.afraid.org"
    API_URL = "https://freedns.afraid.org/api/"
    
    def __init__(self, credentials: Dict[str, Any]):
        super().__init__(credentials)
        self._cookie = None
        self._records_cache: Dict[str, List[Dict]] = {}
    
    def _get_auth_hash(self) -> str:
        """Generate SHA1 hash of username|password for API auth"""
        auth_string = f"{self.credentials['username']}|{self.credentials['password']}"
        return hashlib.sha1(auth_string.encode()).hexdigest()
    
    def _api_request(self, action: str, params: Optional[Dict] = None) -> Tuple[bool, Any]:
        """Make FreeDNS API request"""
        url = f"{self.API_URL}"
        
        request_params = {
            'action': action,
            'sha': self._get_auth_hash()
        }
        if params:
            request_params.update(params)
        
        try:
            response = requests.get(
                url,
                params=request_params,
                timeout=30
            )
            
            if response.status_code >= 400:
                return False, f"HTTP {response.status_code}: {response.reason}"
            
            text = response.text.strip()
            
            # Check for error responses
            if text.startswith('ERROR'):
                return False, text
            
            return True, text
            
        except requests.RequestException as e:
            logger.error(f"FreeDNS API request failed: {e}")
            return False, str(e)
    
    def _get_records(self) -> Tuple[bool, List[Dict]]:
        """Get list of DNS records"""
        success, result = self._api_request('getdyndns')
        if not success:
            return False, []
        
        # Parse the response (pipe-delimited format)
        # Format: hostname|currentIP|updateURL
        records = []
        for line in result.split('\n'):
            if '|' in line:
                parts = line.split('|')
                if len(parts) >= 3:
                    records.append({
                        'hostname': parts[0],
                        'ip': parts[1],
                        'update_url': parts[2]
                    })
        
        return True, records
    
    def create_txt_record(
        self, 
        domain: str, 
        record_name: str, 
        record_value: str, 
        ttl: int = 300
    ) -> Tuple[bool, str]:
        """
        Create TXT record via FreeDNS.
        
        Note: FreeDNS has limited API for TXT records.
        This uses the web interface approach with authentication.
        """
        # FreeDNS doesn't have a direct API for creating TXT records
        # We need to use the web interface or the v2 dynamic update
        
        # Try using the subdomain API endpoint
        url = f"{self.BASE_URL}/subdomain/save.php"
        
        try:
            # First, we need to get a session by logging in
            session = requests.Session()
            
            # Login
            login_url = f"{self.BASE_URL}/zc.php"
            login_data = {
                'username': self.credentials['username'],
                'password': self.credentials['password'],
                'submit': 'Login',
                'action': 'auth'
            }
            
            login_response = session.post(login_url, data=login_data, timeout=30)
            
            if 'Invalid' in login_response.text or login_response.status_code >= 400:
                return False, "Login failed: Invalid credentials"
            
            # Now try to create the TXT record
            # FreeDNS uses numeric type IDs: TXT = 16
            record_data = {
                'type': '16',  # TXT record
                'subdomain': record_name.split('.')[0] if '.' in record_name else record_name,
                'domain_id': '',  # Would need to look this up
                'address': record_value,
                'ttl': str(ttl),
                'submit': 'Save!'
            }
            
            # This approach requires knowing the domain_id
            # For a proper implementation, we'd need to:
            # 1. List domains to get domain_id
            # 2. Submit the record creation form
            
            # Since FreeDNS doesn't have a proper API, return guidance
            return False, (
                "FreeDNS requires manual TXT record creation via web interface. "
                f"Please add TXT record: {record_name} = {record_value}"
            )
            
        except requests.RequestException as e:
            logger.error(f"FreeDNS create record failed: {e}")
            return False, str(e)
    
    def delete_txt_record(self, domain: str, record_name: str) -> Tuple[bool, str]:
        """Delete TXT record via FreeDNS"""
        # FreeDNS doesn't have a direct API for deleting TXT records
        return False, (
            "FreeDNS requires manual TXT record deletion via web interface. "
            f"Please delete TXT record: {record_name}"
        )
    
    def test_connection(self) -> Tuple[bool, str]:
        """Test FreeDNS API connection"""
        success, result = self._api_request('getdyndns')
        if success:
            # Count records from response
            lines = [l for l in result.split('\n') if '|' in l]
            return True, f"Connected successfully. Found {len(lines)} dynamic DNS record(s)"
        return False, f"Connection failed: {result}"
    
    @classmethod
    def get_credential_schema(cls):
        return [
            {'name': 'username', 'label': 'Username', 'type': 'text', 'required': True,
             'help': 'FreeDNS afraid.org username'},
            {'name': 'password', 'label': 'Password', 'type': 'password', 'required': True,
             'help': 'FreeDNS afraid.org password'},
        ]
