"""
Certificate Service - Certificate Management
Handles certificate generation, signing, revocation, and operations
"""
import base64
import uuid
from datetime import datetime
from typing import Dict, List, Optional
from pathlib import Path

from cryptography import x509
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.backends import default_backend

from models import db, CA, Certificate, AuditLog
from services.trust_store import TrustStoreService
from config.settings import Config


class CertificateService:
    """Service for Certificate operations"""
    
    @staticmethod
    def create_certificate(
        descr: str,
        caref: str,
        dn: Dict[str, str],
        cert_type: str = 'server_cert',
        key_type: str = '2048',
        validity_days: int = 397,
        digest: str = 'sha256',
        san_dns: Optional[List[str]] = None,
        san_ip: Optional[List[str]] = None,
        san_uri: Optional[List[str]] = None,
        san_email: Optional[List[str]] = None,
        username: str = 'system'
    ) -> Certificate:
        """
        Create a certificate signed by a CA
        
        Args:
            descr: Description
            caref: CA refid
            dn: Distinguished Name
            cert_type: usr_cert, server_cert, combined_server_client
            key_type: Key type
            validity_days: Validity in days
            digest: Hash algorithm
            san_dns: DNS SANs
            san_ip: IP SANs
            san_uri: URI SANs
            san_email: Email SANs
            username: User creating certificate
            
        Returns:
            Certificate model instance
        """
        # Get CA
        ca = CA.query.filter_by(refid=caref).first()
        if not ca:
            raise ValueError(f"CA not found: {caref}")
        
        if not ca.prv:
            raise ValueError("CA has no private key - cannot sign certificates")
        
        # Load CA certificate and private key
        ca_cert_pem = base64.b64decode(ca.crt)
        ca_cert = x509.load_pem_x509_certificate(ca_cert_pem, default_backend())
        
        ca_key_pem = base64.b64decode(ca.prv)
        ca_private_key = serialization.load_pem_private_key(
            ca_key_pem, password=None, backend=default_backend()
        )
        
        # Build subject
        subject = TrustStoreService.build_subject(dn)
        
        # Create certificate
        cert_pem, key_pem = TrustStoreService.create_certificate(
            subject=subject,
            ca_cert=ca_cert,
            ca_private_key=ca_private_key,
            cert_type=cert_type,
            validity_days=validity_days,
            digest=digest,
            key_type=key_type,
            san_dns=san_dns,
            san_ip=san_ip,
            san_uri=san_uri,
            san_email=san_email
        )
        
        # Parse certificate
        cert = x509.load_pem_x509_certificate(cert_pem, default_backend())
        
        # Increment CA serial
        ca.serial = (ca.serial or 0) + 1
        
        # Create certificate record
        certificate = Certificate(
            refid=str(uuid.uuid4()),
            descr=descr,
            caref=caref,
            crt=base64.b64encode(cert_pem).decode('utf-8'),
            prv=base64.b64encode(key_pem).decode('utf-8'),
            cert_type=cert_type,
            subject=cert.subject.rfc4514_string(),
            issuer=cert.issuer.rfc4514_string(),
            serial_number=str(cert.serial_number),
            valid_from=cert.not_valid_before,
            valid_to=cert.not_valid_after,
            revoked=False,
            imported_from='generated',
            created_by=username
        )
        
        db.session.add(certificate)
        db.session.commit()
        
        # Audit log
        log = AuditLog(
            username=username,
            action='cert_created',
            resource_type='certificate',
            resource_id=certificate.refid,
            details=f'Created certificate: {descr}',
            success=True
        )
        db.session.add(log)
        db.session.commit()
        
        # Save files
        cert_path = Config.CERT_DIR / f"{certificate.refid}.crt"
        with open(cert_path, 'wb') as f:
            f.write(cert_pem)
        
        key_path = Config.PRIVATE_DIR / f"cert_{certificate.refid}.key"
        with open(key_path, 'wb') as f:
            f.write(key_pem)
        key_path.chmod(0o600)
        
        return certificate
    
    @staticmethod
    def generate_csr(
        descr: str,
        dn: Dict[str, str],
        key_type: str = '2048',
        digest: str = 'sha256',
        san_dns: Optional[List[str]] = None,
        san_ip: Optional[List[str]] = None,
        username: str = 'system'
    ) -> Certificate:
        """
        Generate a Certificate Signing Request
        
        Args:
            descr: Description
            dn: Distinguished Name
            key_type: Key type
            digest: Hash algorithm
            san_dns: DNS SANs
            san_ip: IP SANs
            username: User generating CSR
            
        Returns:
            Certificate record with CSR
        """
        # Build subject
        subject = TrustStoreService.build_subject(dn)
        
        # Generate CSR
        csr_pem, key_pem = TrustStoreService.generate_csr(
            subject=subject,
            key_type=key_type,
            digest=digest,
            san_dns=san_dns,
            san_ip=san_ip
        )
        
        # Parse CSR
        csr = x509.load_pem_x509_csr(csr_pem, default_backend())
        
        # Create certificate record (CSR only, no cert yet)
        certificate = Certificate(
            refid=str(uuid.uuid4()),
            descr=descr,
            caref=None,  # Not signed yet
            csr=base64.b64encode(csr_pem).decode('utf-8'),
            prv=base64.b64encode(key_pem).decode('utf-8'),
            subject=csr.subject.rfc4514_string(),
            imported_from='csr_generated',
            created_by=username
        )
        
        db.session.add(certificate)
        db.session.commit()
        
        # Audit log
        log = AuditLog(
            username=username,
            action='csr_generated',
            resource_type='certificate',
            resource_id=certificate.refid,
            details=f'Generated CSR: {descr}',
            success=True
        )
        db.session.add(log)
        db.session.commit()
        
        # Save files
        csr_path = Config.CERT_DIR / f"{certificate.refid}.csr"
        with open(csr_path, 'wb') as f:
            f.write(csr_pem)
        
        key_path = Config.PRIVATE_DIR / f"cert_{certificate.refid}.key"
        with open(key_path, 'wb') as f:
            f.write(key_pem)
        key_path.chmod(0o600)
        
        return certificate
    
    @staticmethod
    def sign_csr(
        cert_id: int,
        caref: str,
        cert_type: str = 'server_cert',
        validity_days: int = 397,
        digest: str = 'sha256',
        username: str = 'system'
    ) -> Certificate:
        """
        Sign a CSR with a CA
        
        Args:
            cert_id: Certificate ID (with CSR)
            caref: CA refid to sign with
            cert_type: Certificate type
            validity_days: Validity in days
            digest: Hash algorithm
            username: User signing
            
        Returns:
            Updated Certificate with signed cert
        """
        # Get certificate with CSR
        certificate = Certificate.query.get(cert_id)
        if not certificate:
            raise ValueError("Certificate not found")
        
        if not certificate.csr:
            raise ValueError("Certificate has no CSR")
        
        if certificate.crt:
            raise ValueError("Certificate already signed")
        
        # Get CA
        ca = CA.query.filter_by(refid=caref).first()
        if not ca:
            raise ValueError(f"CA not found: {caref}")
        
        if not ca.prv:
            raise ValueError("CA has no private key")
        
        # Load CA cert and key
        ca_cert_pem = base64.b64decode(ca.crt)
        ca_cert = x509.load_pem_x509_certificate(ca_cert_pem, default_backend())
        
        ca_key_pem = base64.b64decode(ca.prv)
        ca_private_key = serialization.load_pem_private_key(
            ca_key_pem, password=None, backend=default_backend()
        )
        
        # Load CSR
        csr_pem = base64.b64decode(certificate.csr)
        
        # Sign CSR
        cert_pem = TrustStoreService.sign_csr(
            csr_pem=csr_pem,
            ca_cert=ca_cert,
            ca_private_key=ca_private_key,
            validity_days=validity_days,
            digest=digest,
            cert_type=cert_type
        )
        
        # Parse signed certificate
        cert = x509.load_pem_x509_certificate(cert_pem, default_backend())
        
        # Update certificate record
        certificate.caref = caref
        certificate.crt = base64.b64encode(cert_pem).decode('utf-8')
        certificate.cert_type = cert_type
        certificate.issuer = cert.issuer.rfc4514_string()
        certificate.serial_number = str(cert.serial_number)
        certificate.valid_from = cert.not_valid_before
        certificate.valid_to = cert.not_valid_after
        
        # Increment CA serial
        ca.serial = (ca.serial or 0) + 1
        
        db.session.commit()
        
        # Audit log
        log = AuditLog(
            username=username,
            action='csr_signed',
            resource_type='certificate',
            resource_id=certificate.refid,
            details=f'Signed CSR: {certificate.descr}',
            success=True
        )
        db.session.add(log)
        db.session.commit()
        
        # Save signed certificate
        cert_path = Config.CERT_DIR / f"{certificate.refid}.crt"
        with open(cert_path, 'wb') as f:
            f.write(cert_pem)
        
        return certificate
    
    @staticmethod
    def import_certificate(
        descr: str,
        cert_pem: str,
        key_pem: Optional[str] = None,
        username: str = 'system'
    ) -> Certificate:
        """
        Import an existing certificate
        
        Args:
            descr: Description
            cert_pem: Certificate PEM
            key_pem: Optional private key PEM
            username: User importing
            
        Returns:
            Certificate instance
        """
        # Parse certificate
        cert = x509.load_pem_x509_certificate(
            cert_pem.encode() if isinstance(cert_pem, str) else cert_pem,
            default_backend()
        )
        
        # Create certificate record
        certificate = Certificate(
            refid=str(uuid.uuid4()),
            descr=descr,
            crt=base64.b64encode(cert_pem.encode() if isinstance(cert_pem, str) else cert_pem).decode('utf-8'),
            prv=base64.b64encode(key_pem.encode()).decode('utf-8') if key_pem else None,
            subject=cert.subject.rfc4514_string(),
            issuer=cert.issuer.rfc4514_string(),
            serial_number=str(cert.serial_number),
            valid_from=cert.not_valid_before,
            valid_to=cert.not_valid_after,
            imported_from='manual',
            created_by=username
        )
        
        db.session.add(certificate)
        db.session.commit()
        
        # Audit log
        log = AuditLog(
            username=username,
            action='cert_imported',
            resource_type='certificate',
            resource_id=certificate.refid,
            details=f'Imported certificate: {descr}',
            success=True
        )
        db.session.add(log)
        db.session.commit()
        
        # Save files
        cert_path = Config.CERT_DIR / f"{certificate.refid}.crt"
        with open(cert_path, 'wb') as f:
            f.write(cert_pem.encode() if isinstance(cert_pem, str) else cert_pem)
        
        if key_pem:
            key_path = Config.PRIVATE_DIR / f"cert_{certificate.refid}.key"
            with open(key_path, 'wb') as f:
                f.write(key_pem.encode() if isinstance(key_pem, str) else key_pem)
            key_path.chmod(0o600)
        
        return certificate
    
    @staticmethod
    def revoke_certificate(
        cert_id: int,
        reason: str = 'unspecified',
        username: str = 'system'
    ) -> Certificate:
        """
        Revoke a certificate
        
        Args:
            cert_id: Certificate ID
            reason: Revocation reason
            username: User revoking
            
        Returns:
            Updated certificate
        """
        certificate = Certificate.query.get(cert_id)
        if not certificate:
            raise ValueError("Certificate not found")
        
        if certificate.revoked:
            raise ValueError("Certificate already revoked")
        
        certificate.revoked = True
        certificate.revoked_at = datetime.utcnow()
        certificate.revoke_reason = reason
        
        db.session.commit()
        
        # Audit log
        log = AuditLog(
            username=username,
            action='cert_revoked',
            resource_type='certificate',
            resource_id=certificate.refid,
            details=f'Revoked certificate: {certificate.descr} - Reason: {reason}',
            success=True
        )
        db.session.add(log)
        db.session.commit()
        
        return certificate
    
    @staticmethod
    def export_certificate(
        cert_id: int,
        format: str = 'pem',
        password: Optional[str] = None
    ) -> bytes:
        """
        Export certificate
        
        Args:
            cert_id: Certificate ID
            format: pem, der, or pkcs12
            password: Password for PKCS#12 (required if format=pkcs12)
            
        Returns:
            Certificate bytes
        """
        certificate = Certificate.query.get(cert_id)
        if not certificate:
            raise ValueError("Certificate not found")
        
        if not certificate.crt:
            raise ValueError("Certificate not yet signed")
        
        cert_pem = base64.b64decode(certificate.crt)
        
        if format == 'pem':
            return cert_pem
        elif format == 'der':
            cert = x509.load_pem_x509_certificate(cert_pem, default_backend())
            return cert.public_bytes(serialization.Encoding.DER)
        elif format == 'pkcs12':
            if not password:
                raise ValueError("Password required for PKCS#12 export")
            if not certificate.prv:
                raise ValueError("Certificate has no private key")
            
            key_pem = base64.b64decode(certificate.prv)
            return TrustStoreService.export_pkcs12(
                cert_pem, key_pem, password, certificate.descr
            )
        else:
            raise ValueError(f"Unsupported format: {format}")
    
    @staticmethod
    def list_certificates(caref: Optional[str] = None) -> List[Certificate]:
        """List all certificates, optionally filtered by CA"""
        query = Certificate.query
        if caref:
            query = query.filter_by(caref=caref)
        return query.order_by(Certificate.created_at.desc()).all()
    
    @staticmethod
    def get_certificate(cert_id: int) -> Optional[Certificate]:
        """Get certificate by ID"""
        return Certificate.query.get(cert_id)
    
    @staticmethod
    def delete_certificate(cert_id: int, username: str = 'system') -> bool:
        """
        Delete a certificate
        
        Args:
            cert_id: Certificate ID
            username: User deleting
            
        Returns:
            True if deleted
        """
        certificate = Certificate.query.get(cert_id)
        if not certificate:
            return False
        
        # Delete files
        cert_path = Config.CERT_DIR / f"{certificate.refid}.crt"
        csr_path = Config.CERT_DIR / f"{certificate.refid}.csr"
        key_path = Config.PRIVATE_DIR / f"cert_{certificate.refid}.key"
        
        for path in [cert_path, csr_path, key_path]:
            if path.exists():
                path.unlink()
        
        # Audit log
        log = AuditLog(
            username=username,
            action='cert_deleted',
            resource_type='certificate',
            resource_id=certificate.refid,
            details=f'Deleted certificate: {certificate.descr}',
            success=True
        )
        db.session.add(log)
        
        # Delete from database
        db.session.delete(certificate)
        db.session.commit()
        
        return True
    
    @staticmethod
    def export_certificate_with_options(
        cert_id: int,
        export_format: str = 'pem',
        include_key: bool = False,
        include_chain: bool = False,
        password: Optional[str] = None
    ) -> bytes:
        """
        Export certificate with multiple format options
        
        Args:
            cert_id: Certificate ID
            export_format: pem, der, pkcs12
            include_key: Include private key (PEM only)
            include_chain: Include CA chain (PEM only)
            password: Password for PKCS#12
            
        Returns:
            Export bytes
        """
        certificate = Certificate.query.get(cert_id)
        if not certificate:
            raise ValueError("Certificate not found")
        
        if not certificate.crt:
            raise ValueError("Certificate not yet signed")
        
        cert_pem = base64.b64decode(certificate.crt)
        
        if export_format == 'pkcs12':
            if not password:
                raise ValueError("Password required for PKCS#12 export")
            if not certificate.prv:
                raise ValueError("Certificate has no private key")
            
            key_pem = base64.b64decode(certificate.prv)
            return TrustStoreService.export_pkcs12(
                cert_pem, key_pem, password, certificate.descr
            )
        
        elif export_format == 'der':
            cert = x509.load_pem_x509_certificate(cert_pem, default_backend())
            return cert.public_bytes(serialization.Encoding.DER)
        
        elif export_format == 'pem':
            result = cert_pem
            
            if include_key and certificate.prv:
                key_pem = base64.b64decode(certificate.prv)
                result += b'\n' + key_pem
            
            if include_chain and certificate.caref:
                # Get CA chain
                ca = CA.query.filter_by(refid=certificate.caref).first()
                if ca:
                    from services.ca_service import CAService
                    chain = CAService.get_ca_chain(ca.id)
                    for chain_cert in chain:
                        result += b'\n' + chain_cert
            
            return result
        
        else:
            raise ValueError(f"Unsupported format: {export_format}")
    
    @staticmethod
    def get_certificate_fingerprints(cert_id: int) -> Dict[str, str]:
        """
        Get certificate fingerprints
        
        Args:
            cert_id: Certificate ID
            
        Returns:
            Dictionary with sha256, sha1, md5 fingerprints
        """
        certificate = Certificate.query.get(cert_id)
        if not certificate:
            raise ValueError("Certificate not found")
        
        if not certificate.crt:
            raise ValueError("Certificate not yet signed")
        
        cert_pem = base64.b64decode(certificate.crt)
        return TrustStoreService.get_certificate_fingerprints(cert_pem)
    
    @staticmethod
    def get_certificate_details(cert_id: int) -> Dict:
        """
        Get detailed certificate information
        
        Args:
            cert_id: Certificate ID
            
        Returns:
            Detailed certificate information
        """
        certificate = Certificate.query.get(cert_id)
        if not certificate:
            raise ValueError("Certificate not found")
        
        if not certificate.crt:
            raise ValueError("Certificate not yet signed")
        
        cert_pem = base64.b64decode(certificate.crt)
        details = TrustStoreService.parse_certificate_details(cert_pem)
        details['fingerprints'] = TrustStoreService.get_certificate_fingerprints(cert_pem)
        details['has_private_key'] = bool(certificate.prv and len(certificate.prv) > 0)
        details['revoked'] = certificate.revoked
        
        return details
