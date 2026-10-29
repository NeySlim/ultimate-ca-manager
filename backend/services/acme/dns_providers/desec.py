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
        self._last_status: Optional[int] = None
    
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
            
            self._last_status = response.status_code
            if response.status_code >= 400:
                try:
                    error = response.json()
                    if isinstance(error, dict):
                        error_msg = error.get('detail', str(error))
                    else:
                        error_msg = str(error)
                except Exception:
                    error_msg = response.reason
                return False, error_msg
            
            if response.text:
                return True, response.json()
            return True, None
            
        except requests.RequestException as e:
            logger.error(f"deSEC API request failed: {self._failure(e)}")
            return False, self._failure(e)
    
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
        
        # An RRset holds all values of a name: merge into the existing one so a
        # wildcard and its apex (same name) coexist. A failed read must not overwrite.
        quoted = f'"{record_value}"'
        rrset_path = f'/domains/{domain_name}/rrsets/{subname or "@"}/TXT/'
        success, current = self._request('GET', rrset_path)
        if success and isinstance(current, dict):
            records = list(current.get('records') or [])
            if quoted in records:
                logger.info(f"deSEC: TXT value already present on {record_name}")
                return True, "Record created successfully"
            success, result = self._request(
                'PATCH', rrset_path,
                {'records': records + [quoted], 'ttl': current.get('ttl') or max(ttl, 60)}
            )
            if not success:
                return False, f"Failed to update record: {result}"
        elif self._last_status == 404:
            data = {
                'subname': subname,
                'type': 'TXT',
                'ttl': max(ttl, 60),  # deSEC minimum TTL is 60
                'records': [quoted]
            }
            success, result = self._request('POST', f'/domains/{domain_name}/rrsets/', data)
            if not success:
                return False, f"Failed to create record: {result}"
        else:
            return False, f"Failed to read existing record: {current}"
        
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
