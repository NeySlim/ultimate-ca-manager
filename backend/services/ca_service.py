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
from utils.file_naming import ca_cert_path, ca_key_path, cleanup_old_files

# Import key encryption (optional - fallback if not available)
try:
    from security.encryption import decrypt_private_key, encrypt_private_key
    HAS_ENCRYPTION = True
except ImportError:
    HAS_ENCRYPTION = False
    def decrypt_private_key(data):
        return data
    def encrypt_private_key(data):
        return data


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
            
            # Load parent CA private key (decrypt if encrypted)
            if not parent_ca.prv:
                raise ValueError("Parent CA has no private key")
            parent_prv_decrypted = decrypt_private_key(parent_ca.prv)
            parent_key_pem = base64.b64decode(parent_prv_decrypted)
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
        
        # Encrypt private key if encryption is enabled
        prv_encoded = base64.b64encode(key_pem).decode('utf-8')
        try:
            from security.encryption import key_encryption
            if key_encryption.is_enabled:
                prv_encoded = key_encryption.encrypt(prv_encoded)
        except ImportError:
            pass  # Security module not available
        
        # Extract SKI from generated cert
        from cryptography.x509.oid import ExtensionOID
        ca_ski = None
        try:
            ext = cert.extensions.get_extension_for_oid(ExtensionOID.SUBJECT_KEY_IDENTIFIER)
            ca_ski = ext.value.key_identifier.hex(':').upper()
        except Exception:
            pass

        # Create CA record
        ca = CA(
            refid=str(uuid.uuid4()),
            descr=descr,
            crt=base64.b64encode(cert_pem).decode('utf-8'),
            prv=prv_encoded,
            serial=0,
            caref=caref,
            subject=cert.subject.rfc4514_string(),
            issuer=cert.issuer.rfc4514_string(),
            ski=ca_ski,
            valid_from=cert.not_valid_before,
            valid_to=cert.not_valid_after,
            imported_from='generated',
            created_by=username
        )
        
        db.session.add(ca)
        db.session.commit()
        
        # Audit log
        from services.audit_service import AuditService
        AuditService.log_ca('ca_created', ca, f'Created CA: {descr}')
        
        # Save certificate to file
        cert_path = ca_cert_path(ca)
        with open(cert_path, 'wb') as f:
            f.write(cert_pem)
        
        # Save private key to file
        key_path = ca_key_path(ca)
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
        from services.audit_service import AuditService
        AuditService.log_ca('ca_imported', ca, f'Imported CA: {descr}')
        
        # Save files
        cert_path = ca_cert_path(ca)
        with open(cert_path, 'wb') as f:
            f.write(cert_pem.encode() if isinstance(cert_pem, str) else cert_pem)
        
        if key_pem:
            key_path = ca_key_path(ca)
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
        
        # Delete files (cleanup old UUID names first, then new names)
        cleanup_old_files(ca=ca)
        cert_path = ca_cert_path(ca)
        key_path = ca_key_path(ca)
        
        if cert_path.exists():
            cert_path.unlink()
        if key_path.exists():
            key_path.unlink()
        
        # Audit log
        from services.audit_service import AuditService
        AuditService.log_ca('ca_deleted', ca, f'Deleted CA: {ca.descr}')
        
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
    
    @staticmethod
    def generate_crl(ca_id: int, validity_days: int = 30) -> bytes:
        """
        Generate Certificate Revocation List for a CA
        
        Args:
            ca_id: CA ID
            validity_days: CRL validity in days
            
        Returns:
            CRL in PEM format
        """
        ca = CA.query.get(ca_id)
        if not ca:
            raise ValueError("CA not found")
        
        if not ca.prv:
            raise ValueError("CA has no private key - cannot sign CRL")
        
        # Load CA certificate and private key
        ca_cert_pem = base64.b64decode(ca.crt)
        ca_cert = x509.load_pem_x509_certificate(ca_cert_pem, default_backend())
        
        # Decrypt CA private key if encrypted
        ca_prv_decrypted = decrypt_private_key(ca.prv)
        ca_key_pem = base64.b64decode(ca_prv_decrypted)
        ca_private_key = serialization.load_pem_private_key(
            ca_key_pem, password=None, backend=default_backend()
        )
        
        # Get all revoked certificates signed by this CA
        revoked_certs = Certificate.query.filter_by(
            caref=ca.refid,
            revoked=True
        ).all()
        
        # Build list of (serial, revocation_date) tuples
        revoked_list = []
        for cert in revoked_certs:
            # Use created_at as revocation date if not tracked separately
            revoked_list.append((cert.serial, cert.created_at))
        
        # Generate CRL
        crl_pem = TrustStoreService.generate_crl(
            ca_cert=ca_cert,
            ca_private_key=ca_private_key,
            revoked_certs=revoked_list,
            validity_days=validity_days,
            digest='sha256'
        )
        
        return crl_pem
    
    @staticmethod
    def export_ca_with_options(
        ca_id: int,
        export_format: str = 'pem',
        include_key: bool = False,
        include_chain: bool = False,
        password: Optional[str] = None
    ) -> bytes:
        """
        Export CA with multiple format options
        
        Args:
            ca_id: CA ID
            export_format: pem, der, pkcs12
            include_key: Include private key (PEM only)
            include_chain: Include certificate chain (PEM only)
            password: Password for PKCS#12
            
        Returns:
            Export bytes
        """
        ca = CA.query.get(ca_id)
        if not ca:
            raise ValueError("CA not found")
        
        cert_pem = base64.b64decode(ca.crt)
        
        if export_format == 'pkcs12':
            if not password:
                raise ValueError("Password required for PKCS#12 export")
            if not ca.prv:
                raise ValueError("CA has no private key")
            
            # Decrypt private key if encrypted
            prv_decrypted = decrypt_private_key(ca.prv)
            key_pem = base64.b64decode(prv_decrypted)
            return TrustStoreService.export_pkcs12(
                cert_pem, key_pem, password, ca.descr
            )
        
        elif export_format == 'der':
            cert = x509.load_pem_x509_certificate(cert_pem, default_backend())
            return cert.public_bytes(serialization.Encoding.DER)
        
        elif export_format == 'pem':
            result = cert_pem
            
            if include_key and ca.prv:
                # Decrypt private key if encrypted
                prv_decrypted = decrypt_private_key(ca.prv)
                key_pem = base64.b64decode(prv_decrypted)
                result += b'\n' + key_pem
            
            if include_chain:
                chain = CAService.get_ca_chain(ca_id)
                # Skip first cert (already included)
                for chain_cert in chain[1:]:
                    result += b'\n' + chain_cert
            
            return result
        
        else:
            raise ValueError(f"Unsupported format: {export_format}")
    
    @staticmethod
    def get_ca_fingerprints(ca_id: int) -> Dict[str, str]:
        """
        Get CA certificate fingerprints
        
        Args:
            ca_id: CA ID
            
        Returns:
            Dictionary with sha256, sha1, md5 fingerprints
        """
        ca = CA.query.get(ca_id)
        if not ca:
            raise ValueError("CA not found")
        
        cert_pem = base64.b64decode(ca.crt)
        return TrustStoreService.get_certificate_fingerprints(cert_pem)
    
    @staticmethod
    def get_ca_details(ca_id: int) -> Dict:
        """
        Get detailed CA certificate information
        
        Args:
            ca_id: CA ID
            
        Returns:
            Detailed certificate information
        """
        ca = CA.query.get(ca_id)
        if not ca:
            raise ValueError("CA not found")
        
        cert_pem = base64.b64decode(ca.crt)
        details = TrustStoreService.parse_certificate_details(cert_pem)
        details['fingerprints'] = TrustStoreService.get_certificate_fingerprints(cert_pem)
        details['has_private_key'] = bool(ca.prv and len(ca.prv) > 0)
        
        return details
