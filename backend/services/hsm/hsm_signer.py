"""
HSM Signing Helper

Provides HSM-backed signing for certificate operations.
Works with cryptography library's certificate builder.
"""

import logging
from typing import Optional

from cryptography import x509
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives.asymmetric import padding

logger = logging.getLogger(__name__)


class HsmSigner:
    """
    HSM Signer - adapts HSM signing to work with cryptography library
    
    This class provides a compatible interface for certificate signing
    when the private key is stored in an HSM rather than locally.
    """
    
    def __init__(self, hsm_service, key_id: int, algorithm: str):
        """
        Initialize HSM Signer
        
        Args:
            hsm_service: HsmService instance
            key_id: Database ID of the HSM key
            algorithm: Key algorithm (RSA-2048, EC-P256, etc.)
        """
        from services.hsm import HsmService
        
        self.hsm_service = HsmService
        self.key_id = key_id
        self.algorithm = algorithm
        self._public_key = None
    
    def get_public_key(self):
        """Get the public key from HSM for certificate building"""
        if self._public_key is None:
            pem = self.hsm_service.get_public_key(self.key_id)
            from cryptography.hazmat.primitives import serialization
            self._public_key = serialization.load_pem_public_key(
                pem.encode() if isinstance(pem, str) else pem,
                backend=default_backend()
            )
        return self._public_key
    
    def sign_certificate(
        self,
        builder: x509.CertificateBuilder,
        hash_algorithm: hashes.HashAlgorithm = hashes.SHA256()
    ) -> x509.Certificate:
        """
        Sign a certificate using HSM key
        
        This works by:
        1. Building the TBS (To Be Signed) certificate data
        2. Signing via HSM
        3. Reconstructing the full certificate
        
        Args:
            builder: Certificate builder with all fields set
            hash_algorithm: Hash algorithm for signing
            
        Returns:
            Signed certificate
        """
        # For now, we need to use a workaround since cryptography library
        # doesn't support external signing directly
        # 
        # The approach:
        # 1. Create certificate with dummy signature
        # 2. Extract TBS bytes
        # 3. Sign with HSM
        # 4. Replace signature
        #
        # However, this is complex and version-dependent.
        # A simpler approach for MVP: use HSM key for CA operations only
        # where we generate the full certificate in one operation.
        
        raise NotImplementedError(
            "Direct HSM signing not yet implemented. "
            "For now, generate keys locally and use HSM for CA root keys only."
        )


def sign_with_hsm(
    data: bytes,
    hsm_key_id: int,
    algorithm: Optional[str] = None
) -> bytes:
    """
    Sign data using HSM key
    
    Args:
        data: Data to sign
        hsm_key_id: Database ID of the HSM key
        algorithm: Optional algorithm override
        
    Returns:
        Signature bytes
    """
    from services.hsm import HsmService
    return HsmService.sign(hsm_key_id, data)


def get_hsm_public_key(hsm_key_id: int) -> str:
    """
    Get public key PEM from HSM key
    
    Args:
        hsm_key_id: Database ID of the HSM key
        
    Returns:
        Public key in PEM format
    """
    from services.hsm import HsmService
    return HsmService.get_public_key(hsm_key_id)


def verify_hsm_available(provider_id: int) -> bool:
    """
    Verify HSM provider is connected and available
    
    Args:
        provider_id: Provider database ID
        
    Returns:
        True if provider is available
    """
    from services.hsm import HsmService
    result = HsmService.test_provider(provider_id)
    return result.get('success', False)
