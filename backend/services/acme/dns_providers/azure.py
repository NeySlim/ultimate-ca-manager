"""
Azure DNS Provider - Microsoft Azure REST API
Uses Azure Service Principal (OAuth2) for DNS record management
https://learn.microsoft.com/en-us/rest/api/dns/
"""
import requests
from typing import Tuple, Dict, Any, Optional, List
import logging

from .base import BaseDnsProvider

logger = logging.getLogger(__name__)


class AzureDnsProvider(BaseDnsProvider):
    """
    Azure DNS Provider using Azure REST API.
    
    Required credentials:
    - tenant_id: Azure AD Tenant ID
    - client_id: Service Principal Application (Client) ID
    - client_secret: Service Principal Client Secret
    - subscription_id: Azure Subscription ID
    - resource_group: Resource Group containing DNS zones
    
    Setup: Azure Portal > App registrations > New registration > Certificates & secrets
    Assign "DNS Zone Contributor" role on the resource group.
    """
    
    PROVIDER_TYPE = "azure"
    PROVIDER_NAME = "Azure DNS"
    PROVIDER_DESCRIPTION = "Microsoft Azure DNS"
    REQUIRED_CREDENTIALS = ["tenant_id", "client_id", "client_secret", "subscription_id", "resource_group"]
    
    BASE_URL = "https://management.azure.com"
    API_VERSION = "2018-05-01"
    
    def __init__(self, credentials: Dict[str, Any]):
        super().__init__(credentials)
        self._zone_cache: Dict[str, Dict] = {}
        self._access_token: Optional[str] = None
    
    def _get_access_token(self) -> Tuple[bool, str]:
        """Get OAuth2 access token from Azure AD"""
        if self._access_token:
            return True, self._access_token
        
        tenant_id = self.credentials["tenant_id"]
        token_url = f"https://login.microsoftonline.com/{tenant_id}/oauth2/v2.0/token"
        
        try:
            response = requests.post(
                token_url,
                data={
                    "grant_type": "client_credentials",
                    "client_id": self.credentials["client_id"],
                    "client_secret": self.credentials["client_secret"],
                    "scope": "https://management.azure.com/.default",
                },
                timeout=30,
            )
            
            if response.status_code >= 400:
                try:
                    error = response.json()
                    error_msg = error.get("error_description", response.reason)
                except Exception:
                    error_msg = response.reason
                return False, f"Authentication failed: {error_msg}"
            
            data = response.json()
            self._access_token = data["access_token"]
            return True, self._access_token
            
        except requests.RequestException as e:
            logger.error(f"Azure OAuth2 token request failed: {e}")
            return False, str(e)
    
    def _get_headers(self) -> Optional[Dict[str, str]]:
        """Get request headers with Bearer token"""
        success, token = self._get_access_token()
        if not success:
            return None
        return {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }
    
    def _request(
        self,
        method: str,
        path: str,
        data: Optional[Dict] = None,
    ) -> Tuple[bool, Any]:
        """Make Azure REST API request"""
        headers = self._get_headers()
        if not headers:
            return False, "Failed to obtain access token"
        
        url = f"{self.BASE_URL}{path}"
        
        try:
            response = requests.request(
                method=method,
                url=url,
                headers=headers,
                json=data,
                timeout=30,
            )
            
            if response.status_code >= 400:
                try:
                    error = response.json()
                    error_msg = error.get("error", {}).get("message", response.reason)
                except Exception:
                    error_msg = response.reason
                return False, error_msg
            
            if response.status_code == 204:
                return True, None
            
            if response.text:
                return True, response.json()
            return True, None
            
        except requests.RequestException as e:
            logger.error(f"Azure DNS API request failed: {e}")
            return False, str(e)
    
    def _zones_path(self) -> str:
        """Build base path for DNS zones"""
        sub = self.credentials["subscription_id"]
        rg = self.credentials["resource_group"]
        return f"/subscriptions/{sub}/resourceGroups/{rg}/providers/Microsoft.Network/dnsZones"
    
    def _get_zone(self, domain: str) -> Optional[Dict]:
        """Get zone info for domain"""
        if domain in self._zone_cache:
            return self._zone_cache[domain]
        
        success, result = self._request("GET", f"{self._zones_path()}?api-version={self.API_VERSION}")
        if not success:
            return None
        
        zones = result.get("value", [])
        
        # Find best matching zone (longest suffix match)
        domain_parts = domain.split(".")
        for i in range(len(domain_parts) - 1):
            zone_name = ".".join(domain_parts[i:])
            for zone in zones:
                if zone["name"] == zone_name:
                    self._zone_cache[domain] = zone
                    return zone
        
        return None
    
    def create_txt_record(
        self,
        domain: str,
        record_name: str,
        record_value: str,
        ttl: int = 300,
    ) -> Tuple[bool, str]:
        """Create TXT record via Azure DNS API"""
        zone = self._get_zone(domain)
        if not zone:
            return False, f"Could not find zone for domain {domain}"
        
        zone_name = zone["name"]
        relative_name = self.get_relative_record_name(record_name, zone_name)
        
        path = (
            f"{self._zones_path()}/{zone_name}/TXT/{relative_name}"
            f"?api-version={self.API_VERSION}"
        )
        
        data = {
            "properties": {
                "TTL": ttl,
                "TXTRecords": [{"value": [record_value]}],
            }
        }
        
        success, result = self._request("PUT", path, data)
        
        if not success:
            return False, f"Failed to create record: {result}"
        
        logger.info(f"Azure: Created TXT record {record_name}")
        return True, "Record created successfully"
    
    def delete_txt_record(self, domain: str, record_name: str) -> Tuple[bool, str]:
        """Delete TXT record via Azure DNS API"""
        zone = self._get_zone(domain)
        if not zone:
            return False, f"Could not find zone for domain {domain}"
        
        zone_name = zone["name"]
        relative_name = self.get_relative_record_name(record_name, zone_name)
        
        path = (
            f"{self._zones_path()}/{zone_name}/TXT/{relative_name}"
            f"?api-version={self.API_VERSION}"
        )
        
        success, result = self._request("DELETE", path)
        
        if not success:
            if "not found" in str(result).lower():
                return True, "Record not found (already deleted?)"
            return False, f"Failed to delete record: {result}"
        
        logger.info(f"Azure: Deleted TXT record {record_name}")
        return True, "Record deleted successfully"
    
    def test_connection(self) -> Tuple[bool, str]:
        """Test Azure DNS API connection"""
        success, result = self._request("GET", f"{self._zones_path()}?api-version={self.API_VERSION}")
        if success:
            zones = result.get("value", [])
            zone_names = [z["name"] for z in zones]
            return True, f"Connected successfully. Found {len(zones)} zone(s): {', '.join(zone_names)}"
        return False, f"Connection failed: {result}"
    
    @classmethod
    def get_credential_schema(cls) -> List[Dict[str, Any]]:
        return [
            {"name": "tenant_id", "label": "Tenant ID", "type": "text", "required": True,
             "help": "Azure AD Tenant ID (Directory ID) from Azure Portal > Azure Active Directory > Overview"},
            {"name": "client_id", "label": "Client ID", "type": "text", "required": True,
             "help": "Application (Client) ID from Azure Portal > App registrations"},
            {"name": "client_secret", "label": "Client Secret", "type": "password", "required": True,
             "help": "Client secret from App registrations > Certificates & secrets"},
            {"name": "subscription_id", "label": "Subscription ID", "type": "text", "required": True,
             "help": "Azure Subscription ID from Azure Portal > Subscriptions"},
            {"name": "resource_group", "label": "Resource Group", "type": "text", "required": True,
             "help": "Resource group containing the DNS zones"},
        ]
