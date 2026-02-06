"""
Key Matcher - Match private keys to certificates and CSRs

Features:
- Match key to certificate by public key comparison
- Match key to CSR by public key comparison
- Detect orphan keys (no matching cert)
- Detect certificates missing keys
"""

from typing import List, Dict, Optional, Tuple
from cryptography import x509
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives.asymmetric import rsa, ec

from .parser import ParsedObject, ObjectType


class KeyMatcher:
    """
    Matches private keys to their corresponding certificates or CSRs.
    """
    
    def match_all(self, objects: List[ParsedObject]) -> Dict[str, any]:
        """
        Match all keys to certificates and CSRs.
        
        Args:
            objects: List of ParsedObject
            
        Returns:
            Dict with matching info:
            {
                "matched_pairs": [(key_idx, cert_idx), ...],
                "orphan_keys": [key_idx, ...],
                "certs_without_key": [cert_idx, ...],
                "csr_key_pairs": [(csr_idx, key_idx), ...]
            }
        """
        keys = [(i, o) for i, o in enumerate(objects) if o.type == ObjectType.PRIVATE_KEY]
        certs = [(i, o) for i, o in enumerate(objects) if o.type == ObjectType.CERTIFICATE]
        csrs = [(i, o) for i, o in enumerate(objects) if o.type == ObjectType.CSR]
        
        matched_pairs: List[Tuple[int, int]] = []  # (key_idx, cert_idx)
        csr_key_pairs: List[Tuple[int, int]] = []  # (csr_idx, key_idx)
        matched_key_indices = set()
        matched_cert_indices = set()
        matched_csr_indices = set()
        
        # Match keys to certificates
        for key_idx, key_obj in keys:
            for cert_idx, cert_obj in certs:
                if cert_idx in matched_cert_indices:
                    continue
                    
                if self._keys_match(key_obj, cert_obj):
                    matched_pairs.append((key_idx, cert_idx))
                    matched_key_indices.add(key_idx)
                    matched_cert_indices.add(cert_idx)
                    
                    # Update objects with match info
                    key_obj.matched_cert_index = cert_idx
                    cert_obj.matched_key_index = key_idx
                    break
        
        # Match remaining keys to CSRs
        for key_idx, key_obj in keys:
            if key_idx in matched_key_indices:
                continue
                
            for csr_idx, csr_obj in csrs:
                if csr_idx in matched_csr_indices:
                    continue
                    
                if self._key_matches_csr(key_obj, csr_obj):
                    csr_key_pairs.append((csr_idx, key_idx))
                    matched_key_indices.add(key_idx)
                    matched_csr_indices.add(csr_idx)
                    
                    key_obj.matched_cert_index = csr_idx  # Using same field for CSR
                    csr_obj.matched_key_index = key_idx
                    break
        
        # Find orphans
        orphan_keys = [i for i, _ in keys if i not in matched_key_indices]
        certs_without_key = [i for i, _ in certs if i not in matched_cert_indices]
        
        return {
            "matched_pairs": matched_pairs,
            "orphan_keys": orphan_keys,
            "certs_without_key": certs_without_key,
            "csr_key_pairs": csr_key_pairs
        }
    
    def _keys_match(self, key_obj: ParsedObject, cert_obj: ParsedObject) -> bool:
        """
        Check if a private key matches a certificate's public key.
        """
        try:
            # Load private key
            key = serialization.load_pem_private_key(
                key_obj.raw_pem.encode(),
                password=None,
                backend=default_backend()
            )
            
            # Load certificate
            cert = x509.load_pem_x509_certificate(
                cert_obj.raw_pem.encode(),
                default_backend()
            )
            
            # Compare public keys
            return self._public_keys_equal(key.public_key(), cert.public_key())
            
        except Exception:
            return False
    
    def _key_matches_csr(self, key_obj: ParsedObject, csr_obj: ParsedObject) -> bool:
        """
        Check if a private key matches a CSR's public key.
        """
        try:
            # Load private key
            key = serialization.load_pem_private_key(
                key_obj.raw_pem.encode(),
                password=None,
                backend=default_backend()
            )
            
            # Load CSR
            csr = x509.load_pem_x509_csr(
                csr_obj.raw_pem.encode(),
                default_backend()
            )
            
            # Compare public keys
            return self._public_keys_equal(key.public_key(), csr.public_key())
            
        except Exception:
            return False
    
    def _public_keys_equal(self, key1, key2) -> bool:
        """
        Compare two public keys for equality.
        """
        try:
            # Serialize both to DER and compare
            der1 = key1.public_bytes(
                encoding=serialization.Encoding.DER,
                format=serialization.PublicFormat.SubjectPublicKeyInfo
            )
            der2 = key2.public_bytes(
                encoding=serialization.Encoding.DER,
                format=serialization.PublicFormat.SubjectPublicKeyInfo
            )
            return der1 == der2
        except Exception:
            return False
    
    def find_key_in_db(self, cert_obj: ParsedObject) -> bool:
        """
        Check if a matching private key exists in the database.
        
        Returns True if a key is found.
        """
        from models import Certificate
        
        try:
            cert = x509.load_pem_x509_certificate(
                cert_obj.raw_pem.encode(),
                default_backend()
            )
            
            # Search by serial number
            db_cert = Certificate.query.filter_by(
                serial_number=str(cert.serial_number)
            ).first()
            
            if db_cert and db_cert.prv:
                return True
                
        except Exception:
            pass
            
        return False
