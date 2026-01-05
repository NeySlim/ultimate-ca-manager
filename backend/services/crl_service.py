"""
CRL Service - Certificate Revocation List Management
RFC 5280 compliant CRL generation and management
"""
import base64
from datetime import datetime, timedelta
from typing import List, Optional, Tuple

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.backends import default_backend
from cryptography.x509.oid import ExtensionOID

from models import db, CA, Certificate, AuditLog
from models.crl import CRLMetadata


class CRLService:
    """Service for CRL generation and management"""
    
    DEFAULT_VALIDITY_DAYS = 7  # CRL valid for 7 days by default
    
    @staticmethod
    def get_revoked_certificates(ca_id: int) -> List[Certificate]:
        """
        Get all revoked certificates for a CA
        
        Args:
            ca_id: CA database ID
            
        Returns:
            List of revoked Certificate objects
        """
        ca = CA.query.get(ca_id)
        if not ca:
            raise ValueError(f"CA with id {ca_id} not found")
        
        # Get all revoked certificates issued by this CA
        revoked_certs = Certificate.query.filter_by(
            caref=ca.refid,
            revoked=True
        ).all()
        
        return revoked_certs
    
    @staticmethod
    def generate_crl(
        ca_id: int,
        validity_days: int = DEFAULT_VALIDITY_DAYS,
        username: str = 'system'
    ) -> CRLMetadata:
        """
        Generate a new CRL for a CA
        
        Args:
            ca_id: CA database ID
            validity_days: Number of days CRL is valid
            username: User who triggered generation
            
        Returns:
            CRLMetadata object with generated CRL
        """
        ca = CA.query.get(ca_id)
        if not ca:
            raise ValueError(f"CA with id {ca_id} not found")
        
        if not ca.has_private_key:
            raise ValueError(f"CA {ca.descr} does not have a private key - cannot sign CRL")
        
        # Load CA certificate
        ca_cert_pem = base64.b64decode(ca.crt).decode('utf-8')
        ca_cert = x509.load_pem_x509_certificate(ca_cert_pem.encode(), default_backend())
        
        # Load CA private key
        ca_key_pem = base64.b64decode(ca.prv).decode('utf-8')
        ca_private_key = serialization.load_pem_private_key(
            ca_key_pem.encode(),
            password=None,
            backend=default_backend()
        )
        
        # Get revoked certificates
        revoked_certs = CRLService.get_revoked_certificates(ca_id)
        
        # Determine next CRL number
        last_crl = CRLMetadata.query.filter_by(ca_id=ca_id).order_by(
            CRLMetadata.crl_number.desc()
        ).first()
        crl_number = 1 if not last_crl else last_crl.crl_number + 1
        
        # Build CRL
        now = datetime.utcnow()
        builder = x509.CertificateRevocationListBuilder()
        builder = builder.issuer_name(ca_cert.subject)
        builder = builder.last_update(now)
        builder = builder.next_update(now + timedelta(days=validity_days))
        
        # Add revoked certificates
        for cert in revoked_certs:
            if not cert.serial_number:
                continue
            
            # Parse serial number (hex string to int)
            try:
                serial_int = int(cert.serial_number.replace(':', ''), 16)
                # RFC 5280: CRL serial numbers must be <= 20 octets (160 bits)
                # cryptography library enforces 159 bits max
                if serial_int.bit_length() > 159:
                    # Truncate to 159 bits by masking
                    serial_int = serial_int & ((1 << 159) - 1)
            except (ValueError, AttributeError):
                continue
            
            revoked_builder = x509.RevokedCertificateBuilder()
            revoked_builder = revoked_builder.serial_number(serial_int)
            revoked_builder = revoked_builder.revocation_date(cert.revoked_at or now)
            
            # Add revocation reason if available
            if cert.revoke_reason:
                reason_map = {
                    'unspecified': x509.ReasonFlags.unspecified,
                    'keyCompromise': x509.ReasonFlags.key_compromise,
                    'CACompromise': x509.ReasonFlags.ca_compromise,
                    'affiliationChanged': x509.ReasonFlags.affiliation_changed,
                    'superseded': x509.ReasonFlags.superseded,
                    'cessationOfOperation': x509.ReasonFlags.cessation_of_operation,
                    'certificateHold': x509.ReasonFlags.certificate_hold,
                    'removeFromCRL': x509.ReasonFlags.remove_from_crl,
                    'privilegeWithdrawn': x509.ReasonFlags.privilege_withdrawn,
                    'aACompromise': x509.ReasonFlags.aa_compromise,
                }
                reason = reason_map.get(cert.revoke_reason, x509.ReasonFlags.unspecified)
                revoked_builder = revoked_builder.add_extension(
                    x509.CRLReason(reason),
                    critical=False
                )
            
            builder = builder.add_revoked_certificate(revoked_builder.build())
        
        # Add CRL Number extension (RFC 5280 - Section 5.2.3)
        builder = builder.add_extension(
            x509.CRLNumber(crl_number),
            critical=False
        )
        
        # Add Authority Key Identifier (RFC 5280 - Section 5.2.1)
        try:
            aki = ca_cert.extensions.get_extension_for_oid(
                ExtensionOID.AUTHORITY_KEY_IDENTIFIER
            ).value
            builder = builder.add_extension(aki, critical=False)
        except x509.ExtensionNotFound:
            # If CA cert doesn't have AKI, create from subject key identifier
            try:
                ski = ca_cert.extensions.get_extension_for_oid(
                    ExtensionOID.SUBJECT_KEY_IDENTIFIER
                ).value
                aki = x509.AuthorityKeyIdentifier(
                    key_identifier=ski.digest,
                    authority_cert_issuer=None,
                    authority_cert_serial_number=None
                )
                builder = builder.add_extension(aki, critical=False)
            except x509.ExtensionNotFound:
                pass  # Skip if neither AKI nor SKI available
        
        # Sign CRL
        crl = builder.sign(ca_private_key, hashes.SHA256(), default_backend())
        
        # Encode to PEM and DER
        crl_pem = crl.public_bytes(serialization.Encoding.PEM).decode('utf-8')
        crl_der = crl.public_bytes(serialization.Encoding.DER)
        
        # Create metadata record
        crl_metadata = CRLMetadata(
            ca_id=ca_id,
            crl_number=crl_number,
            this_update=now,
            next_update=now + timedelta(days=validity_days),
            crl_pem=crl_pem,
            crl_der=crl_der,
            revoked_count=len(revoked_certs),
            generated_by=username
        )
        
        db.session.add(crl_metadata)
        
        # Audit log
        audit = AuditLog(
            username=username,
            action='generate_crl',
            resource_type='crl',
            resource_id=str(ca_id),
            details=f"Generated CRL #{crl_number} for CA {ca.descr} with {len(revoked_certs)} revoked certificates",
            success=True
        )
        db.session.add(audit)
        
        db.session.commit()
        
        return crl_metadata
    
    @staticmethod
    def get_latest_crl(ca_id: int) -> Optional[CRLMetadata]:
        """
        Get the latest CRL for a CA
        
        Args:
            ca_id: CA database ID
            
        Returns:
            Latest CRLMetadata object or None if no CRL exists
        """
        return CRLMetadata.query.filter_by(ca_id=ca_id).order_by(
            CRLMetadata.crl_number.desc()
        ).first()
    
    @staticmethod
    def get_latest_crl_by_refid(ca_refid: str) -> Optional[CRLMetadata]:
        """
        Get the latest CRL for a CA by refid
        
        Args:
            ca_refid: CA reference ID
            
        Returns:
            Latest CRLMetadata object or None
        """
        ca = CA.query.filter_by(refid=ca_refid).first()
        if not ca:
            return None
        
        return CRLService.get_latest_crl(ca.id)
    
    @staticmethod
    def update_crl(ca_id: int, username: str = 'system') -> CRLMetadata:
        """
        Force update/regenerate CRL for a CA
        
        Args:
            ca_id: CA database ID
            username: User who triggered update
            
        Returns:
            New CRLMetadata object
        """
        return CRLService.generate_crl(ca_id, username=username)
    
    @staticmethod
    def get_crl_pem(ca_refid: str) -> Optional[str]:
        """
        Get CRL in PEM format by CA refid
        
        Args:
            ca_refid: CA reference ID
            
        Returns:
            PEM encoded CRL string or None
        """
        crl = CRLService.get_latest_crl_by_refid(ca_refid)
        return crl.crl_pem if crl else None
    
    @staticmethod
    def get_crl_der(ca_refid: str) -> Optional[bytes]:
        """
        Get CRL in DER format by CA refid
        
        Args:
            ca_refid: CA reference ID
            
        Returns:
            DER encoded CRL bytes or None
        """
        crl = CRLService.get_latest_crl_by_refid(ca_refid)
        return crl.crl_der if crl else None
    
    @staticmethod
    def auto_generate_on_revocation(ca_id: int, username: str = 'system') -> Optional[CRLMetadata]:
        """
        Auto-generate CRL after certificate revocation
        
        Args:
            ca_id: CA database ID
            username: User who triggered revocation
            
        Returns:
            CRLMetadata object or None if CA doesn't have CDP enabled
        """
        ca = CA.query.get(ca_id)
        if not ca:
            return None
        
        # Only auto-generate if CDP is enabled
        if not ca.cdp_enabled:
            return None
        
        return CRLService.generate_crl(ca_id, username=username)
