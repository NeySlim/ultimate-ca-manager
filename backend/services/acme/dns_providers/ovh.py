"""
OVH DNS Provider
Uses OVH API for DNS record management
https://api.ovh.com/
"""
import hashlib
import time
import requests
from typing import Tuple, Dict, Any, Optional
import logging

from .base import BaseDnsProvider

logger = logging.getLogger(__name__)


class OvhDnsProvider(BaseDnsProvider):
    """
    OVH DNS Provider using OVH API.
    
    Required credentials:
    - application_key: OVH Application Key
    - application_secret: OVH Application Secret
    - consumer_key: OVH Consumer Key (generated after authorization)
    - endpoint: API endpoint (ovh-eu, ovh-ca, ovh-us, etc.)
    
    Get credentials at: https://api.ovh.com/createToken/
    Required permissions: GET/POST/DELETE /domain/zone/*
    """
    
    PROVIDER_TYPE = "ovh"
    PROVIDER_NAME = "OVH"
    PROVIDER_DESCRIPTION = "OVH DNS API (France/Europe)"
    REQUIRED_CREDENTIALS = ["application_key", "application_secret", "consumer_key"]
    OPTIONAL_CREDENTIALS = ["endpoint"]
    
    ENDPOINTS = {
        'ovh-eu': 'https://eu.api.ovh.com/1.0',
        'ovh-ca': 'https://ca.api.ovh.com/1.0',
        'ovh-us': 'https://api.us.ovhcloud.com/1.0',
        'kimsufi-eu': 'https://eu.api.kimsufi.com/1.0',
        'kimsufi-ca': 'https://ca.api.kimsufi.com/1.0',
        'soyoustart-eu': 'https://eu.api.soyoustart.com/1.0',
        'soyoustart-ca': 'https://ca.api.soyoustart.com/1.0',
    }
    
    def __init__(self, credentials: Dict[str, Any]):
        super().__init__(credentials)
        endpoint_key = credentials.get('endpoint', 'ovh-eu')
        self.base_url = self.ENDPOINTS.get(endpoint_key, self.ENDPOINTS['ovh-eu'])
        self._time_delta = None
    
    def _get_time_delta(self) -> int:
        """Get time difference between local and OVH server"""
        if self._time_delta is None:
            try:
                response = requests.get(f"{self.base_url}/auth/time", timeout=10)
                server_time = int(response.text)
                self._time_delta = server_time - int(time.time())
            except Exception:
                self._time_delta = 0
        return self._time_delta
    
    def _sign_request(self, method: str, url: str, body: str, timestamp: str) -> str:
        """Generate OVH API signature"""
        app_secret = self.credentials['application_secret']
        consumer_key = self.credentials['consumer_key']
        
        # Signature = SHA1(AS+"+"+CK+"+"+METHOD+"+"+QUERY+"+"+BODY+"+"+TSTAMP)
        to_sign = f"{app_secret}+{consumer_key}+{method}+{url}+{body}+{timestamp}"
        signature = hashlib.sha1(to_sign.encode('utf-8')).hexdigest()
        return f"$1${signature}"
    
    def _request(self, method: str, path: str, data: Optional[Dict] = None) -> Tuple[bool, Any]:
        """Make authenticated OVH API request"""
        url = f"{self.base_url}{path}"
        body = ""
        
        if data:
            import json
            body = json.dumps(data)
        
        timestamp = str(int(time.time()) + self._get_time_delta())
        signature = self._sign_request(method.upper(), url, body, timestamp)
        
        headers = {
            'X-Ovh-Application': self.credentials['application_key'],
            'X-Ovh-Consumer': self.credentials['consumer_key'],
            'X-Ovh-Signature': signature,
            'X-Ovh-Timestamp': timestamp,
            'Content-Type': 'application/json',
        }
        
        try:
            response = requests.request(
                method=method,
                url=url,
                headers=headers,
                data=body if body else None,
                timeout=30
            )
            
            if response.status_code >= 400:
                error = response.json() if response.text else {'message': response.reason}
                return False, error.get('message', str(error))
            
            return True, response.json() if response.text else None
            
        except requests.RequestException as e:
            logger.error(f"OVH API request failed: {e}")
            return False, str(e)
    
    def _get_zone(self, domain: str) -> Optional[str]:
        """Find the zone that manages this domain"""
        # Try to find matching zone
        success, zones = self._request('GET', '/domain/zone')
        if not success:
            return None
        
        # Find the best matching zone
        domain_parts = domain.split('.')
        for i in range(len(domain_parts)):
            potential_zone = '.'.join(domain_parts[i:])
            if potential_zone in zones:
                return potential_zone
        
        return None
    
    def create_txt_record(
        self, 
        domain: str, 
        record_name: str, 
        record_value: str, 
        ttl: int = 300
    ) -> Tuple[bool, str]:
        """Create TXT record via OVH API"""
        zone = self._get_zone(domain)
        if not zone:
            return False, f"Could not find zone for domain {domain}"
        
        # Get relative subdomain
        subdomain = self.get_relative_record_name(record_name, zone)
        
        # Create record
        data = {
            'fieldType': 'TXT',
            'subDomain': subdomain,
            'target': record_value,
            'ttl': ttl,
        }
        
        success, result = self._request('POST', f'/domain/zone/{zone}/record', data)
        if not success:
            return False, f"Failed to create record: {result}"
        
        # Refresh zone
        self._request('POST', f'/domain/zone/{zone}/refresh')
        
        logger.info(f"OVH: Created TXT record {record_name} = {record_value}")
        return True, f"Record created successfully (ID: {result.get('id', 'unknown')})"
    
    def delete_txt_record(self, domain: str, record_name: str) -> Tuple[bool, str]:
        """Delete TXT record via OVH API"""
        zone = self._get_zone(domain)
        if not zone:
            return False, f"Could not find zone for domain {domain}"
        
        subdomain = self.get_relative_record_name(record_name, zone)
        
        # Find record ID
        success, records = self._request(
            'GET', 
            f'/domain/zone/{zone}/record?fieldType=TXT&subDomain={subdomain}'
        )
        if not success:
            return False, f"Failed to list records: {records}"
        
        if not records:
            return True, "Record not found (already deleted?)"
        
        # Delete all matching records
        deleted = 0
        for record_id in records:
            success, _ = self._request('DELETE', f'/domain/zone/{zone}/record/{record_id}')
            if success:
                deleted += 1
        
        # Refresh zone
        self._request('POST', f'/domain/zone/{zone}/refresh')
        
        logger.info(f"OVH: Deleted {deleted} TXT record(s) for {record_name}")
        return True, f"Deleted {deleted} record(s)"
    
    def test_connection(self) -> Tuple[bool, str]:
        """Test OVH API connection"""
        success, zones = self._request('GET', '/domain/zone')
        if success:
            zone_count = len(zones) if zones else 0
            return True, f"Connected successfully. Found {zone_count} zone(s)."
        return False, f"Connection failed: {zones}"
    
    @classmethod
    def get_credential_schema(cls):
        return [
            {'name': 'application_key', 'label': 'Application Key', 'type': 'text', 'required': True},
            {'name': 'application_secret', 'label': 'Application Secret', 'type': 'password', 'required': True},
            {'name': 'consumer_key', 'label': 'Consumer Key', 'type': 'password', 'required': True},
            {'name': 'endpoint', 'label': 'Endpoint', 'type': 'select', 'required': False, 'default': 'ovh-eu',
             'options': [
                 {'value': 'ovh-eu', 'label': 'OVH Europe (ovh-eu)'},
                 {'value': 'ovh-ca', 'label': 'OVH Canada (ovh-ca)'},
                 {'value': 'ovh-us', 'label': 'OVH US (ovh-us)'},
                 {'value': 'kimsufi-eu', 'label': 'Kimsufi Europe'},
                 {'value': 'kimsufi-ca', 'label': 'Kimsufi Canada'},
                 {'value': 'soyoustart-eu', 'label': 'So You Start Europe'},
                 {'value': 'soyoustart-ca', 'label': 'So You Start Canada'},
             ]},
        ]
