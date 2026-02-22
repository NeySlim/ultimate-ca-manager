"""
mTLS Authentication Service
Handle client certificate authentication
"""
from typing import Optional, Tuple
from datetime import datetime, timezone
from models import db, User
from models.auth_certificate import AuthCertificate
from services.certificate_parser import CertificateParser
import logging

logger = logging.getLogger(__name__)


class MTLSAuthService:
    """Service for mTLS (client certificate) authentication"""
    
    @staticmethod
    def authenticate_certificate(cert_info: dict) -> Tuple[Optional[User], Optional[AuthCertificate], str]:
        """
        Authenticate user by client certificate
        
        Args:
            cert_info: Dictionary with certificate information from parser
            
        Returns:
            Tuple of (User, AuthCertificate, error_message)
            Returns (None, None, error) if authentication fails
        """
        if not cert_info:
            return None, None, "No certificate information provided"
        
        serial = cert_info.get('serial')
        fingerprint = cert_info.get('fingerprint')
        
        if not serial:
            return None, None, "Certificate serial number not found"
        
        # Try to find certificate by serial number
        auth_cert = AuthCertificate.query.filter_by(cert_serial=serial).first()
        
        # If not found by serial, try fingerprint
        if not auth_cert and fingerprint:
            auth_cert = AuthCertificate.query.filter_by(cert_fingerprint=fingerprint).first()
        
        if not auth_cert:
            logger.warning(f"Certificate not enrolled: serial={serial}, fingerprint={fingerprint}")
            return None, None, "Certificate not enrolled"
        
        # Check if certificate is enabled
        if not auth_cert.enabled:
            logger.warning(f"Certificate disabled: serial={serial}, user_id={auth_cert.user_id}")
            return None, None, "Certificate is disabled"
        
        # Check validity dates if available
        if cert_info.get('valid_until'):
            valid_until = cert_info['valid_until']
            now = datetime.now(timezone.utc) if valid_until.tzinfo else datetime.utcnow()
            if now > valid_until:
                logger.warning(f"Certificate expired: serial={serial}")
                return None, None, "Certificate has expired"
        
        if cert_info.get('valid_from'):
            valid_from = cert_info['valid_from']
            now = datetime.now(timezone.utc) if valid_from.tzinfo else datetime.utcnow()
            if now < valid_from:
                logger.warning(f"Certificate not yet valid: serial={serial}")
                return None, None, "Certificate is not yet valid"
        
        # Get associated user
        user = User.query.get(auth_cert.user_id)
        
        if not user:
            logger.error(f"User not found for certificate: user_id={auth_cert.user_id}")
            return None, None, "User not found"
        
        if not user.active:
            logger.warning(f"User account disabled: user_id={user.id}")
            return None, None, "User account is disabled"
        
        # Update last used timestamp
        auth_cert.last_used_at = datetime.utcnow()
        db.session.commit()
        
        logger.info(f"Certificate authentication successful: user={user.username}, serial={serial}")
        return user, auth_cert, ""
    
    @staticmethod
    def enroll_certificate(user_id: int, cert_pem: str, name: Optional[str] = None) -> Tuple[bool, str, Optional[AuthCertificate]]:
        """
        Enroll a client certificate for a user
        
        Args:
            user_id: User ID to associate certificate with
            cert_pem: PEM-encoded certificate
            name: Optional friendly name for the certificate
            
        Returns:
            Tuple of (success, message, AuthCertificate)
        """
        # Parse certificate
        cert = CertificateParser.parse_pem_certificate(cert_pem)
        
        if not cert:
            return False, "Invalid certificate format", None
        
        cert_info = CertificateParser.extract_certificate_info(cert)
        
        # Check if certificate already enrolled
        existing = AuthCertificate.query.filter_by(cert_serial=cert_info['serial']).first()
        if existing:
            return False, "Certificate already enrolled", None
        
        # Check validity
        if not cert_info['is_valid']:
            return False, "Certificate is not valid (expired or not yet valid)", None
        
        # Create auth certificate record
        auth_cert = AuthCertificate(
            user_id=user_id,
            cert_serial=cert_info['serial'],
            cert_subject=cert_info['subject_dn'],
            cert_issuer=cert_info['issuer_dn'],
            cert_fingerprint=cert_info['fingerprint'],
            name=name or cert_info.get('common_name') or f"Certificate {cert_info['serial'][:8]}",
            valid_from=cert_info['valid_from'],
            valid_until=cert_info['valid_until'],
            enabled=True
        )
        
        db.session.add(auth_cert)
        db.session.commit()
        
        logger.info(f"Certificate enrolled: user_id={user_id}, serial={cert_info['serial']}")
        return True, "Certificate enrolled successfully", auth_cert
    
    @staticmethod
    def revoke_certificate(cert_id: int, user_id: Optional[int] = None) -> Tuple[bool, str]:
        """
        Revoke (disable) a client certificate
        
        Args:
            cert_id: AuthCertificate ID
            user_id: Optional user ID for authorization check
            
        Returns:
            Tuple of (success, message)
        """
        auth_cert = AuthCertificate.query.get(cert_id)
        
        if not auth_cert:
            return False, "Certificate not found"
        
        # Check authorization if user_id provided
        if user_id and auth_cert.user_id != user_id:
            user = User.query.get(user_id)
            if not user or user.role != 'admin':
                return False, "Not authorized to revoke this certificate"
        
        auth_cert.enabled = False
        db.session.commit()
        
        logger.info(f"Certificate revoked: id={cert_id}, serial={auth_cert.cert_serial}")
        return True, "Certificate revoked successfully"
    
    @staticmethod
    def delete_certificate(cert_id: int, user_id: Optional[int] = None) -> Tuple[bool, str]:
        """
        Delete a client certificate
        
        Args:
            cert_id: AuthCertificate ID
            user_id: Optional user ID for authorization check
            
        Returns:
            Tuple of (success, message)
        """
        auth_cert = AuthCertificate.query.get(cert_id)
        
        if not auth_cert:
            return False, "Certificate not found"
        
        # Check authorization
        if user_id and auth_cert.user_id != user_id:
            user = User.query.get(user_id)
            if not user or user.role != 'admin':
                return False, "Not authorized to delete this certificate"
        
        serial = auth_cert.cert_serial
        db.session.delete(auth_cert)
        db.session.commit()
        
        logger.info(f"Certificate deleted: id={cert_id}, serial={serial}")
        return True, "Certificate deleted successfully"
    
    @staticmethod
    def is_mtls_enabled() -> bool:
        """
        Check if mTLS authentication is enabled globally
        
        Returns:
            True if mTLS is enabled
        """
        from models import SystemConfig
        
        config = SystemConfig.query.filter_by(key='mtls_enabled').first()
        if config and config.value:
            return config.value.lower() in ('true', '1', 'yes')
        
        return False
    
    @staticmethod
    def get_user_certificates(user_id: int) -> list:
        """
        Get all certificates for a user
        
        Args:
            user_id: User ID
            
        Returns:
            List of AuthCertificate objects
        """
        return AuthCertificate.query.filter_by(user_id=user_id).all()
