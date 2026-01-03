"""
CA Service - Certificate Authority Management
Handles CA creation, import, export, and operations
"""
import base64
import uuid
from datetime import datetime
from typing import Dict, List, Optional, Tuple
from pathlib import Path

from cryptography import x509
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.backends import default_backend

from models import db, CA, Certificate, AuditLog
from services.trust_store import TrustStoreService
from config.settings import Config


class CAService:
    """Service for Certificate Authority operations"""
    
    @staticmethod
    def create_internal_ca(
        descr: str,
        dn: Dict[str, str],
        key_type: str = '2048',
        validity_days: int = 825,
        digest: str = 'sha256',
        caref: Optional[str] = None,
        ocsp_uri: Optional[str] = None,
        username: str = 'system'
    ) -> CA:
        """
        Create an internal Certificate Authority
        
        Args:
            descr: Description
            dn: Distinguished Name components (CN, O, OU, C, ST, L, email)
            key_type: Key type
            validity_days: Validity in days
            digest: Hash algorithm
            caref: Parent CA refid (for intermediate CA)
            ocsp_uri: Optional OCSP URI
            username: User creating the CA
            
        Returns:
            CA model instance
        """
        # Build subject
        subject = TrustStoreService.build_subject(dn)
        
        # Generate private key
        private_key = TrustStoreService.generate_private_key(key_type)
        
        # Get parent CA if intermediate
        issuer = None
        issuer_private_key = None
        if caref:
            parent_ca = CA.query.filter_by(refid=caref).first()
            if not parent_ca:
                raise ValueError(f"Parent CA not found: {caref}")
            
            # Load parent CA certificate
            parent_cert_pem = base64.b64decode(parent_ca.crt)
            parent_cert = x509.load_pem_x509_certificate(
                parent_cert_pem, default_backend()
            )
            issuer = parent_cert.subject
            
            # Load parent CA private key
            if not parent_ca.prv:
                raise ValueError("Parent CA has no private key")
            parent_key_pem = base64.b64decode(parent_ca.prv)
            issuer_private_key = serialization.load_pem_private_key(
                parent_key_pem, password=None, backend=default_backend()
            )
            
            # Increment parent CA serial
            parent_ca.serial = (parent_ca.serial or 0) + 1
        
        # Create CA certificate
        cert_pem, key_pem = TrustStoreService.create_ca_certificate(
            subject=subject,
            private_key=private_key,
            issuer=issuer,
            issuer_private_key=issuer_private_key,
            validity_days=validity_days,
            digest=digest,
            ocsp_uri=ocsp_uri
        )
        
        # Parse certificate for details
        cert = x509.load_pem_x509_certificate(cert_pem, default_backend())
        
        # Create CA record
        ca = CA(
            refid=str(uuid.uuid4()),
            descr=descr,
            crt=base64.b64encode(cert_pem).decode('utf-8'),
            prv=base64.b64encode(key_pem).decode('utf-8'),
            serial=0,
            caref=caref,
            subject=cert.subject.rfc4514_string(),
            issuer=cert.issuer.rfc4514_string(),
            valid_from=cert.not_valid_before,
            valid_to=cert.not_valid_after,
            imported_from='generated',
            created_by=username
        )
        
        db.session.add(ca)
        db.session.commit()
        
        # Audit log
        log = AuditLog(
            username=username,
            action='ca_created',
            resource_type='ca',
            resource_id=ca.refid,
            details=f'Created CA: {descr}',
            success=True
        )
        db.session.add(log)
        db.session.commit()
        
        # Save certificate to file
        cert_path = Config.CA_DIR / f"{ca.refid}.crt"
        with open(cert_path, 'wb') as f:
            f.write(cert_pem)
        
        # Save private key to file
        key_path = Config.PRIVATE_DIR / f"ca_{ca.refid}.key"
        with open(key_path, 'wb') as f:
            f.write(key_pem)
        key_path.chmod(0o600)
        
        return ca
    
    @staticmethod
    def import_ca(
        descr: str,
        cert_pem: str,
        key_pem: Optional[str] = None,
        username: str = 'system'
    ) -> CA:
        """
        Import an existing CA certificate
        
        Args:
            descr: Description
            cert_pem: Certificate in PEM format
            key_pem: Optional private key in PEM format
            username: User importing
            
        Returns:
            CA model instance
        """
        # Parse certificate
        cert = x509.load_pem_x509_certificate(
            cert_pem.encode() if isinstance(cert_pem, str) else cert_pem,
            default_backend()
        )
        
        # Validate it's a CA certificate
        try:
            bc = cert.extensions.get_extension_for_oid(
                x509.oid.ExtensionOID.BASIC_CONSTRAINTS
            )
            if not bc.value.ca:
                raise ValueError("Certificate is not a CA certificate")
        except x509.ExtensionNotFound:
            raise ValueError("Certificate has no BasicConstraints extension")
        
        # Create CA record
        ca = CA(
            refid=str(uuid.uuid4()),
            descr=descr,
            crt=base64.b64encode(cert_pem.encode() if isinstance(cert_pem, str) else cert_pem).decode('utf-8'),
            prv=base64.b64encode(key_pem.encode()).decode('utf-8') if key_pem else None,
            serial=0,
            subject=cert.subject.rfc4514_string(),
            issuer=cert.issuer.rfc4514_string(),
            valid_from=cert.not_valid_before,
            valid_to=cert.not_valid_after,
            imported_from='manual',
            created_by=username
        )
        
        db.session.add(ca)
        db.session.commit()
        
        # Audit log
        log = AuditLog(
            username=username,
            action='ca_imported',
            resource_type='ca',
            resource_id=ca.refid,
            details=f'Imported CA: {descr}',
            success=True
        )
        db.session.add(log)
        db.session.commit()
        
        # Save files
        cert_path = Config.CA_DIR / f"{ca.refid}.crt"
        with open(cert_path, 'wb') as f:
            f.write(cert_pem.encode() if isinstance(cert_pem, str) else cert_pem)
        
        if key_pem:
            key_path = Config.PRIVATE_DIR / f"ca_{ca.refid}.key"
            with open(key_path, 'wb') as f:
                f.write(key_pem.encode() if isinstance(key_pem, str) else key_pem)
            key_path.chmod(0o600)
        
        return ca
    
    @staticmethod
    def get_ca(ca_id: int) -> Optional[CA]:
        """Get CA by ID"""
        return CA.query.get(ca_id)
    
    @staticmethod
    def get_ca_by_refid(refid: str) -> Optional[CA]:
        """Get CA by refid"""
        return CA.query.filter_by(refid=refid).first()
    
    @staticmethod
    def list_cas() -> List[CA]:
        """List all CAs"""
        return CA.query.order_by(CA.created_at.desc()).all()
    
    @staticmethod
    def delete_ca(ca_id: int, username: str = 'system') -> bool:
        """
        Delete a CA
        
        Args:
            ca_id: CA ID
            username: User deleting
            
        Returns:
            True if deleted
        """
        ca = CA.query.get(ca_id)
        if not ca:
            return False
        
        # Check if CA is used by certificates
        cert_count = Certificate.query.filter_by(caref=ca.refid).count()
        if cert_count > 0:
            raise ValueError(f"CA is used by {cert_count} certificate(s)")
        
        # Check if CA is parent of other CAs
        child_ca_count = CA.query.filter_by(caref=ca.refid).count()
        if child_ca_count > 0:
            raise ValueError(f"CA is parent of {child_ca_count} intermediate CA(s)")
        
        # Delete files
        cert_path = Config.CA_DIR / f"{ca.refid}.crt"
        key_path = Config.PRIVATE_DIR / f"ca_{ca.refid}.key"
        
        if cert_path.exists():
            cert_path.unlink()
        if key_path.exists():
            key_path.unlink()
        
        # Audit log
        log = AuditLog(
            username=username,
            action='ca_deleted',
            resource_type='ca',
            resource_id=ca.refid,
            details=f'Deleted CA: {ca.descr}',
            success=True
        )
        db.session.add(log)
        
        # Delete from database
        db.session.delete(ca)
        db.session.commit()
        
        return True
    
    @staticmethod
    def export_ca(ca_id: int, format: str = 'pem') -> bytes:
        """
        Export CA certificate
        
        Args:
            ca_id: CA ID
            format: Export format (pem, der)
            
        Returns:
            Certificate bytes
        """
        ca = CA.query.get(ca_id)
        if not ca:
            raise ValueError("CA not found")
        
        cert_pem = base64.b64decode(ca.crt)
        
        if format == 'pem':
            return cert_pem
        elif format == 'der':
            cert = x509.load_pem_x509_certificate(cert_pem, default_backend())
            return cert.public_bytes(serialization.Encoding.DER)
        else:
            raise ValueError(f"Unsupported format: {format}")
    
    @staticmethod
    def get_ca_chain(ca_id: int) -> List[bytes]:
        """
        Get CA certificate chain
        
        Args:
            ca_id: CA ID
            
        Returns:
            List of certificate PEMs (leaf to root)
        """
        chain = []
        ca = CA.query.get(ca_id)
        
        while ca:
            cert_pem = base64.b64decode(ca.crt)
            chain.append(cert_pem)
            
            # Get parent CA
            if ca.caref:
                ca = CA.query.filter_by(refid=ca.caref).first()
            else:
                break
        
        return chain
    
    @staticmethod
    def increment_serial(ca_id: int) -> int:
        """
        Increment CA serial number
        
        Args:
            ca_id: CA ID
            
        Returns:
            New serial number
        """
        ca = CA.query.get(ca_id)
        if not ca:
            raise ValueError("CA not found")
        
        ca.serial = (ca.serial or 0) + 1
        db.session.commit()
        
        return ca.serial
