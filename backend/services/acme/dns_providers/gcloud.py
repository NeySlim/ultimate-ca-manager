"""
Google Cloud DNS Provider
Uses Google Cloud DNS REST API with Service Account authentication
https://cloud.google.com/dns/docs/reference/v1
"""
import json
import time
import base64
import requests
import logging
from urllib.parse import quote
from typing import Tuple, Dict, Any, Optional, List

from .base import BaseDnsProvider

logger = logging.getLogger(__name__)


class GoogleCloudDnsProvider(BaseDnsProvider):
    """
    Google Cloud DNS Provider using REST API.
    
    Required credentials:
    - project_id: Google Cloud project ID
    - service_account_json: Full service account JSON key content
    
    Create credentials at: Google Cloud Console > IAM > Service Accounts > Keys
    Required role: DNS Administrator (roles/dns.admin)
    """
    
    PROVIDER_TYPE = "gcloud"
    PROVIDER_NAME = "Google Cloud DNS"
    PROVIDER_DESCRIPTION = "Google Cloud DNS API"
    REQUIRED_CREDENTIALS = ["project_id", "service_account_json"]
    
    BASE_URL = "https://dns.googleapis.com/dns/v1"
    MAX_PAGES = 50
    TOKEN_URL = "https://oauth2.googleapis.com/token"
    SCOPE = "https://www.googleapis.com/auth/ndev.clouddns.readwrite"
    
    def __init__(self, credentials: Dict[str, Any]):
        super().__init__(credentials)
        self._zone_cache: Dict[str, Dict] = {}
        self._access_token: Optional[str] = None
        self._token_expiry: float = 0
    
    def _get_access_token(self) -> str:
        """Get OAuth2 access token using service account JWT"""
        # Return cached token if still valid
        if self._access_token and time.time() < self._token_expiry - 60:
            return self._access_token
        
        try:
            from cryptography.hazmat.primitives import serialization, hashes
            from cryptography.hazmat.primitives.asymmetric import padding
        except ImportError:
            raise ImportError(
                "cryptography is required for Google Cloud DNS. "
                "Install with: pip install cryptography"
            )
        
        sa = json.loads(self.credentials['service_account_json'])
        now = int(time.time())
        
        # Build JWT header and payload
        header = base64.urlsafe_b64encode(
            json.dumps({"alg": "RS256", "typ": "JWT"}).encode()
        ).rstrip(b'=')
        
        claim_set = base64.urlsafe_b64encode(json.dumps({
            "iss": sa['client_email'],
            "scope": self.SCOPE,
            "aud": self.TOKEN_URL,
            "iat": now,
            "exp": now + 3600,
        }).encode()).rstrip(b'=')
        
        signing_input = header + b'.' + claim_set
        
        # Sign with RSA private key
        private_key = serialization.load_pem_private_key(
            sa['private_key'].encode(), password=None
        )
        signature = private_key.sign(
            signing_input, padding.PKCS1v15(), hashes.SHA256()
        )
        jwt_token = (
            signing_input + b'.' +
            base64.urlsafe_b64encode(signature).rstrip(b'=')
        )
        
        # Exchange JWT for access token
        resp = requests.post(self.TOKEN_URL, data={
            'grant_type': 'urn:ietf:params:oauth:grant-type:jwt-bearer',
            'assertion': jwt_token.decode(),
        }, timeout=30)
        
        if resp.status_code != 200:
            raise RuntimeError(self._error(resp, "Failed to obtain access token: "))
        
        data = resp.json()
        self._access_token = self.remember_secret(data['access_token'])
        self._token_expiry = now + data.get('expires_in', 3600)
        return self._access_token
    
    def _get_headers(self) -> Dict[str, str]:
        return {
            'Authorization': f'Bearer {self._get_access_token()}',
            'Content-Type': 'application/json',
        }
    
    def _request(
        self,
        method: str,
        path: str,
        data: Optional[Dict] = None,
    ) -> Tuple[bool, Any]:
        """Make Google Cloud DNS API request"""
        url = f"{self.BASE_URL}{path}"
        
        try:
            response = requests.request(
                method=method,
                url=url,
                headers=self._get_headers(),
                json=data,
                timeout=30,
            )
            
            if response.status_code >= 400:
                try:
                    error = response.json()
                    error_msg = (
                        error.get('error', {}).get('message', response.reason)
                    )
                except Exception:
                    error_msg = response.reason
                return False, error_msg
            
            if response.text:
                return True, response.json()
            return True, None
            
        except requests.RequestException as e:
            logger.error(f"Google Cloud DNS API request failed: {self._failure(e)}")
            return False, self._failure(e)
    
    def _get_zone(self, domain: str) -> Optional[Dict]:
        """Get managed zone info for domain"""
        # Check cache
        if domain in self._zone_cache:
            return self._zone_cache[domain]
        
        project = self.credentials['project_id']
        zones: List[Dict] = []
        token = None
        for _ in range(self.MAX_PAGES):
            path = f'/projects/{project}/managedZones'
            if token:
                path += f'?pageToken={quote(token)}'
            success, result = self._request('GET', path)
            if not success:
                return None
            zones.extend((result or {}).get('managedZones') or [])
            token = (result or {}).get('nextPageToken')
            if not token:
                break
        else:
            return None

        zone = self.find_zone(domain, zones, key=lambda z: z.get('dnsName'))
        if zone:
            self._zone_cache[domain] = zone
        return zone
    
    def _get_existing_rrset(
        self, project: str, zone_name: str, record_name: str
    ) -> Tuple[bool, Any]:
        """(ok, the TXT RRSet or None); a failed read is not an absent record."""
        # Ensure record_name ends with dot for API
        if not record_name.endswith('.'):
            record_name = record_name + '.'
        
        success, result = self._request(
            'GET',
            f'/projects/{project}/managedZones/{zone_name}'
            f'/rrsets?type=TXT&name={quote(record_name)}',
        )
        if not success:
            return False, result
        
        rrsets = (result or {}).get('rrsets', [])
        for rrset in rrsets:
            if rrset.get('name') == record_name and rrset.get('type') == 'TXT':
                return True, rrset
        return True, None
    
    def create_txt_record(
        self,
        domain: str,
        record_name: str,
        record_value: str,
        ttl: int = 300,
    ) -> Tuple[bool, str]:
        """Create TXT record via Google Cloud DNS API"""
        zone = self._get_zone(domain)
        if not zone:
            return False, f"Could not find managed zone for domain {domain}"
        
        project = self.credentials['project_id']
        zone_name = zone['name']  # managedZone name (not dnsName)
        
        # Google Cloud DNS requires FQDN with trailing dot
        fqdn = record_name if record_name.endswith('.') else record_name + '.'
        quoted_value = f'"{record_value}"'
        
        # Check for existing RRSet
        success, existing = self._get_existing_rrset(project, zone_name, fqdn)
        if not success:
            msg = f"Failed to read existing records: {existing}"
            logger.warning(f"Google Cloud DNS: {msg}")
            return False, msg
        
        change: Dict[str, List[Dict]] = {"additions": []}
        
        if existing:
            # Must delete old and add new combined RRSet
            new_rrdatas = list(existing.get('rrdatas', []))
            if quoted_value not in new_rrdatas:
                new_rrdatas.append(quoted_value)
            change["deletions"] = [existing]
            change["additions"] = [{
                "name": fqdn,
                "type": "TXT",
                "ttl": ttl,
                "rrdatas": new_rrdatas,
            }]
        else:
            change["additions"] = [{
                "name": fqdn,
                "type": "TXT",
                "ttl": ttl,
                "rrdatas": [quoted_value],
            }]
        
        success, result = self._request(
            'POST',
            f'/projects/{project}/managedZones/{zone_name}/changes',
            change,
        )
        
        if not success:
            return False, f"Failed to create record: {result}"
        
        logger.info(f"Google Cloud DNS: Created TXT record {record_name}")
        return True, "Record created successfully"
    
    def delete_txt_record(self, domain: str, record_name: str, record_value: str) -> Tuple[bool, str]:
        """Delete TXT record via Google Cloud DNS API"""
        zone = self._get_zone(domain)
        if not zone:
            return False, f"Could not find managed zone for domain {domain}"
        
        project = self.credentials['project_id']
        zone_name = zone['name']
        fqdn = record_name if record_name.endswith('.') else record_name + '.'
        
        success, existing = self._get_existing_rrset(project, zone_name, fqdn)
        if not success:
            msg = f"Failed to read existing records: {existing}"
            logger.warning(f"Google Cloud DNS: {msg}")
            return False, msg
        if not existing:
            return True, "Record not found (already deleted?)"
        rrdatas = list(existing.get('rrdatas', []))
        remaining = [v for v in rrdatas if not self.txt_matches(v, record_value)]
        if len(remaining) == len(rrdatas):
            return True, "Record not found (already deleted?)"
        
        # A change replaces the RRset atomically: re-add the other challenges' values with its TTL
        change = {"deletions": [existing]}
        if remaining:
            change["additions"] = [{
                "name": fqdn,
                "type": "TXT",
                "ttl": existing.get('ttl', 300),
                "rrdatas": remaining,
            }]
        
        success, result = self._request(
            'POST',
            f'/projects/{project}/managedZones/{zone_name}/changes',
            change,
        )
        
        if not success:
            if 'not found' in str(result).lower():
                return True, "Record not found (already deleted?)"
            logger.warning(f"Google Cloud DNS: failed to delete TXT value of {record_name}: {result}")
            return False, f"Failed to delete record: {result}"
        
        logger.info(f"Google Cloud DNS: Deleted TXT record {record_name}")
        return True, "Record deleted successfully"
    
    def test_connection(self) -> Tuple[bool, str]:
        """Test Google Cloud DNS API connection"""
        project = self.credentials['project_id']
        success, result = self._request(
            'GET', f'/projects/{project}/managedZones'
        )
        if success:
            zones = result.get('managedZones', [])
            zone_names = [z['dnsName'].rstrip('.') for z in zones]
            return True, (
                f"Connected successfully. Found {len(zones)} zone(s): "
                f"{', '.join(zone_names)}"
            )
        return False, f"Connection failed: {result}"
    
    @classmethod
    def get_credential_schema(cls):
        return [
            {
                'name': 'project_id',
                'label': 'Project ID',
                'type': 'text',
                'required': True,
                'help': 'Google Cloud project ID',
            },
            {
                'name': 'service_account_json',
                'label': 'Service Account JSON',
                'type': 'password',
                'required': True,
                'help': 'Paste the full service account JSON key file content',
            },
        ]
