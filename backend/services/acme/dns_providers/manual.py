"""
Manual DNS Provider
For users who manually add TXT records to their DNS.
No API calls - just displays instructions.
"""
from typing import Tuple
from .base import BaseDnsProvider


class ManualDnsProvider(BaseDnsProvider):
    """
    Manual DNS provider for users without API access.
    Displays instructions for manually adding TXT records.
    """
    
    PROVIDER_TYPE = "manual"
    PROVIDER_NAME = "Manual"
    PROVIDER_DESCRIPTION = "Manually add DNS TXT records (no API required)"
    REQUIRED_CREDENTIALS = []
    OPTIONAL_CREDENTIALS = []
    
    def create_txt_record(
        self, 
        domain: str, 
        record_name: str, 
        record_value: str, 
        ttl: int = 300
    ) -> Tuple[bool, str]:
        """
        For manual provider, we don't actually create records.
        Return success with instructions.
        """
        instructions = (
            f"Please add the following TXT record to your DNS:\n"
            f"  Name:  {record_name}\n"
            f"  Type:  TXT\n"
            f"  Value: {record_value}\n"
            f"  TTL:   {ttl}\n\n"
            f"Click 'Verify' once the record has been added and propagated."
        )
        return True, instructions
    
    def delete_txt_record(
        self, 
        domain: str, 
        record_name: str
    ) -> Tuple[bool, str]:
        """
        For manual provider, remind user to clean up.
        """
        message = (
            f"You can now remove the TXT record:\n"
            f"  Name: {record_name}\n"
            f"This is optional but recommended for DNS hygiene."
        )
        return True, message
    
    def test_connection(self) -> Tuple[bool, str]:
        """
        Manual provider always succeeds - no API to test.
        """
        return True, "Manual provider - no API connection required"
    
    @classmethod
    def get_credential_schema(cls):
        """No credentials needed for manual provider"""
        return []
