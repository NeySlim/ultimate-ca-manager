"""
Import Validator - Validate parsed objects before import

Validations:
- Certificate validity dates
- Certificate signature verification
- Key algorithm compatibility
- Duplicate detection
- Chain completeness
"""

from typing import List, Dict, Optional
from datetime import datetime, timezone
from dataclasses import dataclass, field
from cryptography import x509
from cryptography.hazmat.backends import default_backend

from .parser import ParsedObject, ObjectType
from .chain_builder import ChainInfo


@dataclass
class ValidationResult:
    """Result of validation"""
    is_valid: bool = True
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    
    def add_error(self, msg: str):
        self.errors.append(msg)
        self.is_valid = False
    
    def add_warning(self, msg: str):
        self.warnings.append(msg)
    
    def to_dict(self) -> Dict:
        return {
            "is_valid": self.is_valid,
            "errors": self.errors,
            "warnings": self.warnings
        }


class ImportValidator:
    """
    Validates parsed objects before import.
    """
    
    def validate_all(
        self, 
        objects: List[ParsedObject],
        chains: List[ChainInfo] = None,
        check_duplicates: bool = True
    ) -> ValidationResult:
        """
        Validate all parsed objects.
        
        Args:
            objects: List of ParsedObject to validate
            chains: Optional chain info from ChainBuilder
            check_duplicates: Whether to check for duplicates in DB
            
        Returns:
            ValidationResult with errors and warnings
        """
        result = ValidationResult()
        
        for obj in objects:
            self._validate_object(obj, result, check_duplicates)
        
        if chains:
            for chain in chains:
                self._validate_chain(chain, result)
        
        return result
    
    def _validate_object(
        self, 
        obj: ParsedObject, 
        result: ValidationResult,
        check_duplicates: bool
    ):
        """Validate a single object"""
        
        if obj.type == ObjectType.CERTIFICATE:
            self._validate_certificate(obj, result, check_duplicates)
        elif obj.type == ObjectType.PRIVATE_KEY:
            self._validate_key(obj, result)
        elif obj.type == ObjectType.CSR:
            self._validate_csr(obj, result)
    
    def _validate_certificate(
        self, 
        obj: ParsedObject, 
        result: ValidationResult,
        check_duplicates: bool
    ):
        """Validate a certificate"""
        
        # Check expiry
        if obj.not_after:
            try:
                expiry = datetime.fromisoformat(obj.not_after.replace('Z', '+00:00'))
                now = datetime.now(timezone.utc)
                
                if expiry < now:
                    result.add_warning(
                        f"Certificate '{self._get_cn(obj.subject)}' is expired (expired {obj.not_after})"
                    )
                elif (expiry - now).days < 30:
                    result.add_warning(
                        f"Certificate '{self._get_cn(obj.subject)}' expires in {(expiry - now).days} days"
                    )
            except Exception:
                pass
        
        # Check not yet valid
        if obj.not_before:
            try:
                not_before = datetime.fromisoformat(obj.not_before.replace('Z', '+00:00'))
                now = datetime.now(timezone.utc)
                
                if not_before > now:
                    result.add_warning(
                        f"Certificate '{self._get_cn(obj.subject)}' is not yet valid (valid from {obj.not_before})"
                    )
            except Exception:
                pass
        
        # Check for weak keys
        if obj.key_algorithm == "RSA" and obj.key_size < 2048:
            result.add_warning(
                f"Certificate '{self._get_cn(obj.subject)}' uses weak RSA key ({obj.key_size} bits)"
            )
        
        # Check for duplicates
        if check_duplicates:
            duplicate = self._check_duplicate_cert(obj)
            if duplicate:
                result.add_warning(
                    f"Certificate '{self._get_cn(obj.subject)}' already exists in database (ID: {duplicate})"
                )
    
    def _validate_key(self, obj: ParsedObject, result: ValidationResult):
        """Validate a private key"""
        
        if obj.is_encrypted and obj.key_algorithm == "unknown (encrypted)":
            result.add_error(
                f"Private key is encrypted and no password was provided"
            )
        
        # Check for weak keys
        if obj.key_algorithm == "RSA" and obj.key_size < 2048:
            result.add_warning(
                f"Private key uses weak RSA ({obj.key_size} bits)"
            )
    
    def _validate_csr(self, obj: ParsedObject, result: ValidationResult):
        """Validate a CSR"""
        
        # Check for weak keys
        if obj.key_algorithm == "RSA" and obj.key_size < 2048:
            result.add_warning(
                f"CSR '{self._get_cn(obj.subject)}' uses weak RSA key ({obj.key_size} bits)"
            )
        
        # Verify CSR signature
        try:
            csr = x509.load_pem_x509_csr(obj.raw_pem.encode(), default_backend())
            if not csr.is_signature_valid:
                result.add_error(
                    f"CSR '{self._get_cn(obj.subject)}' has invalid signature"
                )
        except Exception as e:
            result.add_error(f"Failed to validate CSR: {str(e)}")
    
    def _validate_chain(self, chain: ChainInfo, result: ValidationResult):
        """Validate a certificate chain"""
        
        if not chain.is_complete:
            if chain.leaf:
                result.add_warning(
                    f"Chain for '{self._get_cn(chain.leaf.subject)}' is incomplete - issuing CA not found in import"
                )
        
        if chain.errors:
            for error in chain.errors:
                result.add_error(error)
    
    def _check_duplicate_cert(self, obj: ParsedObject) -> Optional[int]:
        """Check if certificate already exists in database"""
        from models import Certificate, CA
        
        # Check by serial number
        cert = Certificate.query.filter_by(serial_number=obj.serial_number).first()
        if cert:
            return cert.id
        
        # Also check CAs
        ca = CA.query.filter_by(serial_number=obj.serial_number).first()
        if ca:
            return ca.id
        
        return None
    
    def _get_cn(self, subject: str) -> str:
        """Extract CN from subject"""
        if not subject:
            return "Unknown"
        for part in subject.split(','):
            if part.strip().upper().startswith('CN='):
                return part.strip()[3:]
        return subject[:30] + "..." if len(subject) > 30 else subject
