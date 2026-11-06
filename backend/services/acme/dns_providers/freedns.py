"""
FreeDNS (afraid.org) DNS Provider
Free dynamic DNS service
https://freedns.afraid.org/

Based on: https://gist.github.com/AnthonyWharton/a0e8faae7195a5c1dea210466eda1c92
"""
import re
from typing import Tuple, Dict, Any, Optional
import logging
import requests

from .base import BaseDnsProvider
from utils.safe_requests import create_session

logger = logging.getLogger(__name__)


class FreeDnsDnsProvider(BaseDnsProvider):
    """
    FreeDNS (afraid.org) DNS Provider.
    
    Required credentials:
    - username: FreeDNS username (email, URL-encoded: @ = %40)
    - password: FreeDNS password
    
    Uses web scraping approach as FreeDNS lacks a proper API.
    """
    
    PROVIDER_TYPE = "freedns"
    PROVIDER_NAME = "FreeDNS"
    PROVIDER_DESCRIPTION = "FreeDNS afraid.org (Free DNS)"
    REQUIRED_CREDENTIALS = ["username", "password"]
    SINGLE_TXT_VALUE = True
    
    BASE_URL = "https://freedns.afraid.org"
    
    def __init__(self, credentials: Dict[str, Any]):
        super().__init__(credentials)
        self._session: Optional[requests.Session] = None
        self._domain_cache: Dict[str, str] = {}  # domain -> domain_id
        self._txt_record_cache: Dict[str, str] = {}  # record_name -> data_id
    
    def _get_session(self):
        """Get or create authenticated session"""
        if self._session is None:
            self._session = create_session()
            self._login()
        return self._session
    
    def _login(self) -> Tuple[bool, str]:
        """Login to FreeDNS"""
        if self._session is None:
            self._session = create_session()
        
        try:
            response = self._session.post(
                f"{self.BASE_URL}/zc.php?step=2",
                data={
                    'action': 'auth',
                    'submit': 'Login',
                    'username': self.credentials['username'],
                    'password': self.credentials['password']
                },
                timeout=30
            )
            
            # Check if login succeeded by looking for logout link or error
            if 'Invalid' in response.text or 'error' in response.text.lower():
                return False, "Login failed: Invalid credentials"
            
            if 'Logout' in response.text or 'logout' in response.url:
                return True, "Logged in successfully"
            
            # Check subdomain page to verify login
            check = self._session.get(f"{self.BASE_URL}/subdomain/", timeout=30)
            if 'domain_id=' in check.text:
                return True, "Logged in successfully"
            
            return False, "Login verification failed"
            
        except requests.RequestException as e:
            logger.error(f"FreeDNS login failed: {self._failure(e)}")
            return False, self._failure(e)
    
    def _get_domain_id(self, domain: str) -> Optional[str]:
        """Get domain_id for a domain from FreeDNS"""
        if domain in self._domain_cache:
            return self._domain_cache[domain]
        
        session = self._get_session()
        
        try:
            response = session.get(f"{self.BASE_URL}/subdomain/", timeout=30)
            
            # Parse domain_id from HTML
            # Format: <a href="...domain_id=12345...">domain.com</a>
            pattern = rf'{re.escape(domain)}.*?domain_id=(\d+)'
            match = re.search(pattern, response.text, re.IGNORECASE)
            
            if match:
                domain_id = match.group(1)
                self._domain_cache[domain] = domain_id
                return domain_id
            
            # Try alternative pattern
            pattern2 = rf'domain_id=(\d+).*?{re.escape(domain)}'
            match2 = re.search(pattern2, response.text, re.IGNORECASE)
            if match2:
                domain_id = match2.group(1)
                self._domain_cache[domain] = domain_id
                return domain_id
            
            return None
            
        except requests.RequestException as e:
            logger.error(f"FreeDNS get domain ID failed: {self._failure(e)}")
            return None
    
    def _get_txt_record_id(self, record_name: str) -> Tuple[bool, Optional[str]]:
        """(ok, data_id or None): a page that could not be read is not an absent record."""
        session = self._get_session()
        
        try:
            response = session.get(f"{self.BASE_URL}/subdomain/", timeout=30)
            
            # Rows link the full name (data_id=12345>_acme-challenge.example.com): match all of it,
            # its first label alone is the _acme-challenge of any domain of the account
            pattern = rf'data_id=(\d+)[^>]*>\s*{re.escape(record_name.rstrip("."))}\s*<'
            match = re.search(pattern, response.text, re.IGNORECASE)
            
            if response.status_code >= 400:
                logger.warning(f"FreeDNS: record listing answered HTTP {response.status_code}")
                return False, None
            return True, (match.group(1) if match else None)
            
        except requests.RequestException as e:
            logger.error(f"FreeDNS get TXT record ID failed: {self._failure(e)}")
            return False, None
    
    def create_txt_record(
        self, 
        domain: str, 
        record_name: str, 
        record_value: str, 
        ttl: int = 300
    ) -> Tuple[bool, str]:
        """Create TXT record via FreeDNS web interface"""
        session = self._get_session()
        
        # Get domain ID
        domain_id = self._get_domain_id(domain)
        if not domain_id:
            return False, f"Could not find domain ID for {domain}. Make sure domain is registered in FreeDNS."
        
        # Get subdomain part (e.g., _acme-challenge from _acme-challenge.example.com)
        if record_name.endswith('.' + domain):
            subdomain = record_name[:-len(domain) - 1]
        else:
            subdomain = record_name.split('.')[0]
        
        # Check if record already exists
        listed, existing_id = self._get_txt_record_id(record_name)
        if not listed:
            return False, "Could not read the FreeDNS record list"
        
        try:
            # Create or update TXT record
            response = session.post(
                f"{self.BASE_URL}/subdomain/save.php?step=2",
                data={
                    'type': 'TXT',
                    'subdomain': subdomain,
                    'domain_id': domain_id,
                    'address': f'"{record_value}"',
                    'data_id': existing_id or '',
                    'send': 'Save!'
                },
                timeout=30
            )
            
            # Verify record was created
            listed, new_id = self._get_txt_record_id(record_name)
            if new_id:
                self._txt_record_cache[record_name] = new_id
                logger.info(f"FreeDNS: Created TXT record {record_name} (ID: {new_id})")
                return True, "Record created successfully"
            
            logger.warning(f"FreeDNS: TXT record {record_name} is not listed after saving "
                           f"(HTTP {response.status_code})")
            return False, f"FreeDNS did not list the record after saving (HTTP {response.status_code})"
            
        except requests.RequestException as e:
            logger.error(f"FreeDNS create record failed: {self._failure(e)}")
            return False, self._failure(e)
    
    def delete_txt_record(self, domain: str, record_name: str, record_value: str) -> Tuple[bool, str]:
        """Delete TXT record via FreeDNS web interface"""
        session = self._get_session()
        # The listing page truncates TXT values, so the record cannot be matched on its value
        logger.warning(f"FreeDNS: cleanup of {record_name} removes its TXT record, whichever value it holds")
        
        # Get record ID
        data_id = self._txt_record_cache.get(record_name)
        if not data_id:
            listed, data_id = self._get_txt_record_id(record_name)
            if not listed:
                return False, "Could not read the FreeDNS record list"
        
        if not data_id:
            return True, "Record not found (already deleted?)"
        
        try:
            # Delete the record
            response = session.get(
                f"{self.BASE_URL}/subdomain/delete2.php",
                params={
                    'data_id[]': data_id,
                    'submit': 'delete selected'
                },
                timeout=30
            )
            
            # Remove from cache
            self._txt_record_cache.pop(record_name, None)
            
            # The web form reports no status of its own: the listing says whether the record went.
            listed, still = self._get_txt_record_id(record_name)
            if not listed or still == data_id:
                logger.warning(f"FreeDNS: TXT record {record_name} (ID: {data_id}) may still be listed after deletion")
                return False, f"FreeDNS kept the record (HTTP {response.status_code})"
            logger.info(f"FreeDNS: Deleted TXT record {record_name} (ID: {data_id})")
            return True, "Record deleted successfully"
            
        except requests.RequestException as e:
            logger.error(f"FreeDNS delete record failed: {self._failure(e)}")
            return False, self._failure(e)
    
    def test_connection(self) -> Tuple[bool, str]:
        """Test FreeDNS connection"""
        success, msg = self._login()
        if success:
            # Try to list domains
            try:
                session = self._get_session()
                response = session.get(f"{self.BASE_URL}/subdomain/", timeout=30)
                
                # Count domains
                domain_ids = re.findall(r'domain_id=(\d+)', response.text)
                unique_domains = len(set(domain_ids))
                
                return True, f"Connected successfully. Found {unique_domains} domain(s)"
            except Exception:
                return True, "Connected successfully"
        return False, f"Connection failed: {msg}"
    
    @classmethod
    def get_credential_schema(cls):
        return [
            {'name': 'username', 'label': 'Username/Email', 'type': 'text', 'required': True,
             'help': 'FreeDNS afraid.org username or email'},
            {'name': 'password', 'label': 'Password', 'type': 'password', 'required': True,
             'help': 'FreeDNS afraid.org password'},
        ]
