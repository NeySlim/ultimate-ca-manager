"""
deSEC DNS Provider
Free DNSSEC-enabled DNS hosting
https://desec.readthedocs.io/
"""
import requests
from typing import Tuple, Dict, Any, Optional
import logging

from .base import BaseDnsProvider

logger = logging.getLogger(__name__)


class DesecDnsProvider(BaseDnsProvider):
    """
    deSEC DNS Provider - Free DNSSEC-enabled DNS hosting.
    
    Required credentials:
    - api_token: deSEC API Token
    
    Get token at: desec.io > Account > Token Management
    """
    
    PROVIDER_TYPE = "desec"
    PROVIDER_NAME = "deSEC"
    PROVIDER_DESCRIPTION = "deSEC DNS (Free DNSSEC hosting)"
    REQUIRED_CREDENTIALS = ["api_token"]
    
    BASE_URL = "https://desec.io/api/v1"
    
    def __init__(self, credentials: Dict[str, Any]):
        super().__init__(credentials)
        self._domain_cache: Dict[str, str] = {}
    
    def _get_headers(self) -> Dict[str, str]:
        return {
            'Authorization': f"Token {self.credentials['api_token']}",
            'Content-Type': 'application/json',
        }
    
    def _request(
        self, 
        method: str, 
        path: str, 
        data: Optional[Any] = None
    ) -> Tuple[bool, Any]:
        """Make deSEC API request"""
        url = f"{self.BASE_URL}{path}"
        
        try:
            response = requests.request(
                method=method,
                url=url,
                headers=self._get_headers(),
                json=data,
                timeout=30
            )
            
            if response.status_code >= 400:
                try:
                    error = response.json()
                    if isinstance(error, dict):
                        error_msg = error.get('detail', str(error))
                    else:
                        error_msg = str(error)
                except:
                    error_msg = response.reason
                return False, error_msg
            
            if response.text:
                return True, response.json()
            return True, None
            
        except requests.RequestException as e:
            logger.error(f"deSEC API request failed: {e}")
            return False, str(e)
    
    def _get_domain_name(self, domain: str) -> Optional[str]:
        """Get domain name for a subdomain"""
        if domain in self._domain_cache:
            return self._domain_cache[domain]
        
        success, result = self._request('GET', '/domains/')
        if not success:
            return None
        
        domains = result if isinstance(result, list) else []
        
        # Find best matching domain
        domain_parts = domain.split('.')
        for i in range(len(domain_parts) - 1):
            domain_name = '.'.join(domain_parts[i:])
            for d in domains:
                if d.get('name') == domain_name:
                    self._domain_cache[domain] = domain_name
                    return domain_name
        
        return None
    
    def create_txt_record(
        self, 
        domain: str, 
        record_name: str, 
        record_value: str, 
        ttl: int = 300
    ) -> Tuple[bool, str]:
        """Create TXT record via deSEC API"""
        domain_name = self._get_domain_name(domain)
        if not domain_name:
            return False, f"Could not find domain for {domain}"
        
        # Get subname (relative to domain)
        if record_name.endswith('.' + domain_name):
            subname = record_name[:-len(domain_name) - 1]
        elif record_name.endswith(domain_name):
            subname = record_name[:-len(domain_name)]
        else:
            subname = record_name
        
        subname = subname.rstrip('.')
        
        # deSEC uses PATCH to create/update RRsets
        data = {
            'subname': subname,
            'type': 'TXT',
            'ttl': max(ttl, 60),  # deSEC minimum TTL is 60
            'records': [f'"{record_value}"']
        }
        
        # Try to create new RRset
        success, result = self._request(
            'POST', 
            f'/domains/{domain_name}/rrsets/',
            data
        )
        
        if not success:
            # If exists, try PATCH to update
            if 'already exists' in str(result).lower():
                success, result = self._request(
                    'PATCH',
                    f'/domains/{domain_name}/rrsets/{subname}/TXT/',
                    {'records': [f'"{record_value}"'], 'ttl': max(ttl, 60)}
                )
                if not success:
                    return False, f"Failed to update record: {result}"
            else:
                return False, f"Failed to create record: {result}"
        
        logger.info(f"deSEC: Created TXT record {record_name}")
        return True, "Record created successfully"
    
    def delete_txt_record(self, domain: str, record_name: str) -> Tuple[bool, str]:
        """Delete TXT record via deSEC API"""
        domain_name = self._get_domain_name(domain)
        if not domain_name:
            return False, f"Could not find domain for {domain}"
        
        # Get subname
        if record_name.endswith('.' + domain_name):
            subname = record_name[:-len(domain_name) - 1]
        elif record_name.endswith(domain_name):
            subname = record_name[:-len(domain_name)]
        else:
            subname = record_name
        
        subname = subname.rstrip('.')
        
        success, result = self._request(
            'DELETE',
            f'/domains/{domain_name}/rrsets/{subname}/TXT/'
        )
        
        if not success:
            if '404' in str(result) or 'not found' in str(result).lower():
                return True, "Record not found (already deleted?)"
            return False, f"Failed to delete record: {result}"
        
        logger.info(f"deSEC: Deleted TXT record {record_name}")
        return True, "Record deleted successfully"
    
    def test_connection(self) -> Tuple[bool, str]:
        """Test deSEC API connection"""
        success, result = self._request('GET', '/domains/')
        if success:
            domains = result if isinstance(result, list) else []
            domain_names = [d.get('name', '') for d in domains]
            return True, f"Connected successfully. Found {len(domains)} domain(s): {', '.join(domain_names[:5])}"
        return False, f"Connection failed: {result}"
    
    @classmethod
    def get_credential_schema(cls):
        return [
            {'name': 'api_token', 'label': 'API Token', 'type': 'password', 'required': True,
             'help': 'desec.io > Account > Token Management'},
        ]
