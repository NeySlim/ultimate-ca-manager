"""
INWX DNS Provider
German domain registrar with XML-RPC API
https://www.inwx.de/en/help/apidoc
"""
import requests
from typing import Tuple, Dict, Any, Optional
import logging
import hashlib
import time
import hmac
import base64

from .base import BaseDnsProvider

logger = logging.getLogger(__name__)


class InwxDnsProvider(BaseDnsProvider):
    """
    INWX DNS Provider (Germany).
    
    Required credentials:
    - username: INWX Username
    - password: INWX Password
    - shared_secret: (Optional) TOTP shared secret for 2FA
    
    API documentation: inwx.de/en/help/apidoc
    """
    
    PROVIDER_TYPE = "inwx"
    PROVIDER_NAME = "INWX"
    PROVIDER_DESCRIPTION = "INWX DNS API (Germany)"
    REQUIRED_CREDENTIALS = ["username", "password"]
    
    API_URL = "https://api.domrobot.com/jsonrpc/"
    SANDBOX_URL = "https://api.ote.domrobot.com/jsonrpc/"
    
    def __init__(self, credentials: Dict[str, Any]):
        super().__init__(credentials)
        self._use_sandbox = credentials.get('sandbox', False)
        self._cookies = None
    
    def _get_api_url(self) -> str:
        return self.SANDBOX_URL if self._use_sandbox else self.API_URL
    
    def _rpc_call(self, method: str, params: Optional[Dict] = None) -> Tuple[bool, Any]:
        """Make INWX JSON-RPC API call"""
        payload = {
            'method': method,
            'params': params or {}
        }
        
        try:
            response = requests.post(
                self._get_api_url(),
                json=payload,
                timeout=30,
                headers={'Content-Type': 'application/json'},
                cookies=self._cookies
            )
            
            # Store cookies for session
            if response.cookies:
                self._cookies = response.cookies
            
            if response.status_code >= 400:
                return False, f"HTTP {response.status_code}: {response.reason}"
            
            result = response.json()
            
            code = result.get('code', 0)
            if code >= 2000:  # Error codes start at 2000
                return False, result.get('msg', 'Unknown error')
            
            return True, result.get('resData', result)
            
        except requests.RequestException as e:
            logger.error(f"INWX API request failed: {e}")
            return False, str(e)
    
    def _login(self) -> Tuple[bool, str]:
        """Login to INWX API"""
        params = {
            'user': self.credentials['username'],
            'pass': self.credentials['password']
        }
        
        success, result = self._rpc_call('account.login', params)
        if not success:
            return False, result
        
        # Handle 2FA if shared secret provided
        if result.get('tfa') and self.credentials.get('shared_secret'):
            tan = self._generate_totp(self.credentials['shared_secret'])
            success, result = self._rpc_call('account.unlock', {'tan': tan})
            if not success:
                return False, f"2FA unlock failed: {result}"
        
        return True, "Logged in"
    
    def _generate_totp(self, secret: str) -> str:
        """Generate TOTP code from shared secret"""
        # Base32 decode the secret
        import base64
        try:
            key = base64.b32decode(secret.upper() + '=' * (8 - len(secret) % 8))
        except:
            key = secret.encode()
        
        # Time-based counter
        counter = int(time.time() // 30)
        counter_bytes = counter.to_bytes(8, 'big')
        
        # HMAC-SHA1
        hmac_result = hmac.new(key, counter_bytes, hashlib.sha1).digest()
        
        # Dynamic truncation
        offset = hmac_result[-1] & 0x0F
        code = ((hmac_result[offset] & 0x7F) << 24 |
                (hmac_result[offset + 1] & 0xFF) << 16 |
                (hmac_result[offset + 2] & 0xFF) << 8 |
                (hmac_result[offset + 3] & 0xFF))
        
        return str(code % 1000000).zfill(6)
    
    def _logout(self):
        """Logout from INWX API"""
        self._rpc_call('account.logout')
        self._cookies = None
    
    def create_txt_record(
        self, 
        domain: str, 
        record_name: str, 
        record_value: str, 
        ttl: int = 300
    ) -> Tuple[bool, str]:
        """Create TXT record via INWX API"""
        success, msg = self._login()
        if not success:
            return False, f"Login failed: {msg}"
        
        try:
            params = {
                'domain': domain,
                'name': record_name,
                'type': 'TXT',
                'content': record_value,
                'ttl': ttl
            }
            
            success, result = self._rpc_call('nameserver.createRecord', params)
            
            if not success:
                return False, f"Failed to create record: {result}"
            
            logger.info(f"INWX: Created TXT record {record_name}")
            return True, "Record created successfully"
            
        finally:
            self._logout()
    
    def delete_txt_record(self, domain: str, record_name: str) -> Tuple[bool, str]:
        """Delete TXT record via INWX API"""
        success, msg = self._login()
        if not success:
            return False, f"Login failed: {msg}"
        
        try:
            # First find the record ID
            params = {
                'domain': domain,
                'name': record_name,
                'type': 'TXT'
            }
            
            success, result = self._rpc_call('nameserver.info', params)
            if not success:
                if 'not found' in str(result).lower():
                    return True, "Record not found (already deleted?)"
                return False, f"Failed to find record: {result}"
            
            records = result.get('record', [])
            if not records:
                return True, "Record not found (already deleted?)"
            
            # Delete each matching record
            for record in records:
                record_id = record.get('id')
                if record_id:
                    success, _ = self._rpc_call('nameserver.deleteRecord', {'id': record_id})
            
            logger.info(f"INWX: Deleted TXT record {record_name}")
            return True, "Record deleted successfully"
            
        finally:
            self._logout()
    
    def test_connection(self) -> Tuple[bool, str]:
        """Test INWX API connection"""
        success, msg = self._login()
        if success:
            self._logout()
            return True, "Connected successfully"
        return False, f"Connection failed: {msg}"
    
    @classmethod
    def get_credential_schema(cls):
        return [
            {'name': 'username', 'label': 'Username', 'type': 'text', 'required': True,
             'help': 'INWX username'},
            {'name': 'password', 'label': 'Password', 'type': 'password', 'required': True,
             'help': 'INWX password'},
            {'name': 'shared_secret', 'label': '2FA Shared Secret', 'type': 'password', 'required': False,
             'help': 'TOTP shared secret for 2FA (optional)'},
            {'name': 'sandbox', 'label': 'Use Sandbox', 'type': 'checkbox', 'required': False,
             'help': 'Use sandbox environment for testing'},
        ]
