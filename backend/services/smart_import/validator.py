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
from sqlalchemy import or_ as db_or

from .parser import ParsedObject, ObjectType
from .chain_builder import ChainInfo, find_ca_by_ski
from utils.csr_diagnostics import weak_csr_hash_error
from utils.key_type import unsignable_csr_key


def _trusted_dict(row) -> Dict:
    return {'id': row.id, 'name': row.name, 'certificate_pem': row.certificate_pem,
            'subject': row.subject, 'fingerprint_sha256': row.fingerprint_sha256}


def _compute_cert_fingerprint(pem_or_b64: Optional[str]) -> Optional[str]:
    """Compute SHA-256 fingerprint of a certificate stored as PEM or base64-encoded PEM.

    Returns hex string, or None if the input can't be parsed.
    """
    if not pem_or_b64:
        return None
    import base64
    from cryptography import x509 as _x509
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.backends import default_backend as _dfb
    try:
        data = pem_or_b64
        if "BEGIN CERTIFICATE" not in data:
            try:
                data = base64.b64decode(pem_or_b64).decode()
            except Exception:
                return None
        c = _x509.load_pem_x509_certificate(data.encode(), _dfb())
        return c.fingerprint(hashes.SHA256()).hex()
    except Exception:
        return None


def find_existing_cert_by_identity(model_cls, serial_number: Optional[str],
                                   issuer: Optional[str], new_pem: Optional[str]):
    """Find an existing cert/CA record matching the given identity.

    Strategy (issue #85):
      1. Pre-filter on serial_number (fast, indexed). Per RFC 5280, serial+issuer
         is unique per-issuer, so we narrow with issuer DN.
      2. Confirm with SHA-256 fingerprint of DER bytes — globally unique, immune
         to PEM reformatting.

    Returns the matching ORM record or None.
    """
    if not serial_number:
        return None
    from models import Certificate
    from utils.serial_format import canonical_serial
    if model_cls is Certificate:
        serial_number = canonical_serial(serial_number)
    candidates = model_cls.query.filter_by(serial_number=serial_number).all()
    if not candidates:
        return None

    new_fp = _compute_cert_fingerprint(new_pem) if new_pem else None

    for rec in candidates:
        # Filter by issuer DN if both sides have it (RFC 5280 narrowing)
        rec_issuer = getattr(rec, 'issuer', None)
        if issuer and rec_issuer and rec_issuer != issuer:
            continue
        # Confirm with fingerprint when possible
        if new_fp is None:
            return rec
        existing_fp = _compute_cert_fingerprint(getattr(rec, 'crt', None))
        if existing_fp is None or existing_fp == new_fp:
            return rec
    return None


@dataclass
class ValidationResult:
    """Result of validation"""
    is_valid: bool = True
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    infos: List[str] = field(default_factory=list)
    
    def add_error(self, msg: str):
        self.errors.append(msg)
        self.is_valid = False
    
    def add_warning(self, msg: str):
        self.warnings.append(msg)
    
    def add_info(self, msg: str):
        self.infos.append(msg)
    
    def to_dict(self) -> Dict:
        return {
            "is_valid": self.is_valid,
            "errors": self.errors,
            "warnings": self.warnings,
            "infos": self.infos
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
                        f"Certificate '{self._get_cn(obj)}' is expired (expired {obj.not_after})"
                    )
                elif (expiry - now).days < 30:
                    result.add_warning(
                        f"Certificate '{self._get_cn(obj)}' expires in {(expiry - now).days} days"
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
                        f"Certificate '{self._get_cn(obj)}' is not yet valid (valid from {obj.not_before})"
                    )
            except Exception:
                pass
        
        # Check for weak keys
        if obj.key_algorithm == "RSA" and obj.key_size < 2048:
            result.add_warning(
                f"Certificate '{self._get_cn(obj)}' uses weak RSA key ({obj.key_size} bits)"
            )
        
        # Check for duplicates
        if check_duplicates:
            duplicate = self._check_duplicate_cert(obj)
            if duplicate:
                result.add_warning(
                    f"Certificate '{self._get_cn(obj)}' already exists in database (ID: {duplicate})"
                )
    
    def _validate_key(self, obj: ParsedObject, result: ValidationResult):
        """Validate a private key"""
        
        if obj.error:
            result.add_error(f"Private key cannot be used: {obj.error}")
        elif obj.is_encrypted and obj.key_algorithm == "unknown (encrypted)":
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
                f"CSR '{self._get_cn(obj)}' uses weak RSA key ({obj.key_size} bits)"
            )
        
        # Verify CSR signature
        try:
            csr = x509.load_pem_x509_csr(obj.raw_pem.encode(), default_backend())
            unsignable = unsignable_csr_key(csr)
            if unsignable:
                result.add_error(f"CSR '{self._get_cn(obj)}' refused: {unsignable}")
            elif not csr.is_signature_valid:
                weak = weak_csr_hash_error(csr)
                result.add_error(f"CSR '{self._get_cn(obj)}' refused: {weak}" if weak
                                 else f"CSR '{self._get_cn(obj)}' has invalid signature")
        except Exception as e:
            result.add_error(f"Failed to validate CSR: {str(e)}")
    
    def _validate_chain(self, chain: ChainInfo, result: ValidationResult):
        """Validate a certificate chain against managed CAs and Trust Store"""
        from models import CA
        
        if not chain.is_complete:
            if chain.leaf:
                # Check if issuer CA exists in database
                issuer = chain.leaf.issuer
                top_cert = chain.leaf
                # Walk up the chain to find the top
                if chain.intermediates:
                    issuer = chain.intermediates[-1].issuer
                    top_cert = chain.intermediates[-1]
                
                # 1. Look for issuer in managed CAs (by AKI→SKI first, then subject)
                existing_ca = None
                if top_cert.aki:
                    existing_ca = find_ca_by_ski(top_cert.aki)
                if not existing_ca:
                    existing_ca = CA.query.filter(CA.subject == issuer).first()
                
                if existing_ca:
                    result.add_info(
                        f"Chain for '{self._get_cn(chain.leaf)}' will be linked to existing CA '{existing_ca.common_name}'"
                    )
                    chain.trust_source = 'managed_ca'
                    chain.trust_anchor = existing_ca.common_name
                else:
                    # 2. Look in Trust Store
                    trusted = self._find_in_trust_store(top_cert)
                    if trusted:
                        result.add_info(
                            f"Chain for '{self._get_cn(chain.leaf)}' verified against Trust Store CA '{trusted['name']}'"
                        )
                        chain.is_complete = True
                        chain.trust_source = 'trust_store'
                        chain.trust_anchor = trusted['name']
                    else:
                        result.add_warning(
                            f"Chain for '{self._get_cn(chain.leaf)}' is incomplete - issuing CA not found in managed CAs or Trust Store"
                        )
                        chain.trust_source = None
                        chain.trust_anchor = None
        else:
            chain.trust_source = 'self_contained'
            chain.trust_anchor = self._get_cn(chain.root) if chain.root else None
        
        if chain.errors:
            for error in chain.errors:
                result.add_error(error)
    
    def _find_in_trust_store(self, cert) -> Optional[Dict]:
        """Look for the issuer of a certificate in the Trust Store, through the application's
        database (SQLite or PostgreSQL); a candidate counts only if its SKI or key matches."""
        from cryptography import x509 as x509_mod
        from models.truststore import TrustedCertificate
        from services.smart_import.chain_builder import ChainBuilder

        rows = TrustedCertificate.query.filter(TrustedCertificate.subject == cert.issuer) \
            .order_by(TrustedCertificate.id).all() if cert.issuer else []
        if not rows:
            cn = self._get_cn(cert, issuer=True)
            rows = TrustedCertificate.query.filter(db_or(
                TrustedCertificate.name.contains(cn, autoescape=True),
                TrustedCertificate.subject.contains(cn, autoescape=True),
            )).order_by(TrustedCertificate.id).all()
        try:
            child_cert = (x509_mod.load_pem_x509_certificate(cert.raw_pem.encode(), default_backend())
                          if cert.raw_pem else None)
        except ValueError:
            child_cert = None

        for row in rows:
            try:
                trusted_cert = x509_mod.load_pem_x509_certificate(
                    row.certificate_blocks.encode(), default_backend())
                if cert.aki:
                    try:
                        ski = trusted_cert.extensions.get_extension_for_class(
                            x509_mod.SubjectKeyIdentifier).value.digest.hex()
                        if ski == cert.aki:
                            return _trusted_dict(row)
                    except x509_mod.ExtensionNotFound:
                        pass
                # Else the signature: raises when the trusted key did not sign the certificate
                if child_cert is not None:
                    ChainBuilder()._verify_signature(child_cert, trusted_cert.public_key())
                    return _trusted_dict(row)
            except Exception:
                continue
        return None

    def _check_duplicate_cert(self, obj: ParsedObject) -> Optional[int]:
        """Check if certificate already exists in database (issue #85).

        Uses (serial_number, issuer) RFC 5280 pre-filter + SHA-256 fingerprint
        confirmation to avoid false positives across different issuers.
        """
        from models import Certificate, CA

        existing = find_existing_cert_by_identity(
            Certificate, obj.serial_number, obj.issuer, obj.raw_pem
        )
        if existing:
            return existing.id

        existing_ca = find_existing_cert_by_identity(
            CA, obj.serial_number, obj.issuer, obj.raw_pem
        )
        if existing_ca:
            return existing_ca.id

        return None
    
    def _get_cn(self, obj: ParsedObject, issuer: bool = False) -> str:
        """The most specific CN the parser read on the subject (or issuer), else the DN cut at 30."""
        cn = obj.issuer_cn if issuer else obj.subject_cn
        if cn is not None:  # a CN present but empty stays ''
            return cn
        dn = obj.issuer if issuer else obj.subject
        if not dn:
            return "Unknown"
        return dn[:30] + "..." if len(dn) > 30 else dn
