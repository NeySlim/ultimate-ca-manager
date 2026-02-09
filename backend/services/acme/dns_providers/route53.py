"""
AWS Route53 DNS Provider
Uses boto3 for AWS Route 53 API
"""
import logging
from typing import Tuple, Dict, Any, Optional

from .base import BaseDnsProvider

logger = logging.getLogger(__name__)


class Route53DnsProvider(BaseDnsProvider):
    """
    AWS Route 53 DNS Provider.
    
    Required credentials:
    - aws_access_key_id: AWS Access Key ID
    - aws_secret_access_key: AWS Secret Access Key
    - aws_region: AWS Region (default: us-east-1)
    
    Create credentials at: AWS Console > IAM > Users > Security credentials
    Required permissions: route53:ChangeResourceRecordSets, route53:ListHostedZones, route53:GetHostedZone
    """
    
    PROVIDER_TYPE = "route53"
    PROVIDER_NAME = "AWS Route 53"
    PROVIDER_DESCRIPTION = "Amazon Route 53 DNS (AWS)"
    REQUIRED_CREDENTIALS = ["aws_access_key_id", "aws_secret_access_key"]
    
    def __init__(self, credentials: Dict[str, Any]):
        super().__init__(credentials)
        self._zone_cache: Dict[str, Dict] = {}
        self._client = None
    
    def _get_client(self):
        """Get or create boto3 Route53 client"""
        if self._client is None:
            try:
                import boto3
            except ImportError:
                raise ImportError("boto3 is required for Route53. Install with: pip install boto3")
            
            self._client = boto3.client(
                'route53',
                aws_access_key_id=self.credentials['aws_access_key_id'],
                aws_secret_access_key=self.credentials['aws_secret_access_key'],
                region_name=self.credentials.get('aws_region', 'us-east-1')
            )
        return self._client
    
    def _get_zone(self, domain: str) -> Optional[Dict]:
        """Get hosted zone for domain"""
        if domain in self._zone_cache:
            return self._zone_cache[domain]
        
        client = self._get_client()
        
        try:
            response = client.list_hosted_zones()
            zones = response.get('HostedZones', [])
            
            # Find best matching zone (longest suffix)
            domain_parts = domain.split('.')
            for i in range(len(domain_parts) - 1):
                zone_name = '.'.join(domain_parts[i:]) + '.'  # Route53 uses trailing dot
                for zone in zones:
                    if zone['Name'] == zone_name:
                        self._zone_cache[domain] = zone
                        return zone
            
            return None
            
        except Exception as e:
            logger.error(f"Failed to list Route53 zones: {e}")
            return None
    
    def create_txt_record(
        self, 
        domain: str, 
        record_name: str, 
        record_value: str, 
        ttl: int = 300
    ) -> Tuple[bool, str]:
        """Create TXT record via Route53"""
        zone = self._get_zone(domain)
        if not zone:
            return False, f"Could not find hosted zone for domain {domain}"
        
        client = self._get_client()
        
        # Ensure record name ends with dot (FQDN)
        fqdn = record_name if record_name.endswith('.') else f"{record_name}."
        
        try:
            response = client.change_resource_record_sets(
                HostedZoneId=zone['Id'],
                ChangeBatch={
                    'Comment': 'ACME DNS-01 challenge',
                    'Changes': [{
                        'Action': 'UPSERT',
                        'ResourceRecordSet': {
                            'Name': fqdn,
                            'Type': 'TXT',
                            'TTL': ttl,
                            'ResourceRecords': [
                                {'Value': f'"{record_value}"'}
                            ]
                        }
                    }]
                }
            )
            
            change_id = response['ChangeInfo']['Id']
            logger.info(f"Route53: Created TXT record {record_name} (change: {change_id})")
            return True, f"Record created successfully (change: {change_id})"
            
        except Exception as e:
            logger.error(f"Route53 create record failed: {e}")
            return False, str(e)
    
    def delete_txt_record(self, domain: str, record_name: str) -> Tuple[bool, str]:
        """Delete TXT record via Route53"""
        zone = self._get_zone(domain)
        if not zone:
            return False, f"Could not find hosted zone for domain {domain}"
        
        client = self._get_client()
        fqdn = record_name if record_name.endswith('.') else f"{record_name}."
        
        try:
            # First, get current record to delete
            response = client.list_resource_record_sets(
                HostedZoneId=zone['Id'],
                StartRecordName=fqdn,
                StartRecordType='TXT',
                MaxItems='1'
            )
            
            records = response.get('ResourceRecordSets', [])
            txt_record = None
            for r in records:
                if r['Name'] == fqdn and r['Type'] == 'TXT':
                    txt_record = r
                    break
            
            if not txt_record:
                return True, "Record not found (already deleted?)"
            
            # Delete the record
            client.change_resource_record_sets(
                HostedZoneId=zone['Id'],
                ChangeBatch={
                    'Comment': 'ACME cleanup',
                    'Changes': [{
                        'Action': 'DELETE',
                        'ResourceRecordSet': txt_record
                    }]
                }
            )
            
            logger.info(f"Route53: Deleted TXT record {record_name}")
            return True, "Record deleted successfully"
            
        except Exception as e:
            if 'ResourceRecordSet not found' in str(e) or 'was not found' in str(e):
                return True, "Record not found (already deleted?)"
            logger.error(f"Route53 delete record failed: {e}")
            return False, str(e)
    
    def test_connection(self) -> Tuple[bool, str]:
        """Test Route53 API connection"""
        try:
            client = self._get_client()
            response = client.list_hosted_zones()
            zones = response.get('HostedZones', [])
            zone_names = [z['Name'].rstrip('.') for z in zones]
            return True, f"Connected successfully. Found {len(zones)} zone(s): {', '.join(zone_names[:5])}"
        except Exception as e:
            return False, f"Connection failed: {str(e)}"
    
    @classmethod
    def get_credential_schema(cls):
        return [
            {'name': 'aws_access_key_id', 'label': 'Access Key ID', 'type': 'text', 'required': True,
             'help': 'AWS IAM Access Key ID'},
            {'name': 'aws_secret_access_key', 'label': 'Secret Access Key', 'type': 'password', 'required': True,
             'help': 'AWS IAM Secret Access Key'},
            {'name': 'aws_region', 'label': 'Region', 'type': 'text', 'required': False,
             'default': 'us-east-1', 'help': 'AWS Region (default: us-east-1)'},
        ]
