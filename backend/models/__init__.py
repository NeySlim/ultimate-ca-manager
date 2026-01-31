import json
"""
Database Models for Ultimate CA Manager
"""
from datetime import datetime
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash

db = SQLAlchemy()

# Import sub-models
from models.certificate_template import CertificateTemplate
from models.truststore import TrustedCertificate


class User(db.Model):
    """User model for authentication"""
    __tablename__ = "users"
    
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False, index=True)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    full_name = db.Column(db.String(255))  # Full name for WebAuthn/certificates
    role = db.Column(db.String(20), nullable=False, default="viewer")  # admin, operator, viewer
    active = db.Column(db.Boolean, default=True)
    mfa_enabled = db.Column(db.Boolean, default=False)  # MFA enabled for this user
    
    # 2FA/TOTP fields
    totp_secret = db.Column(db.String(32))  # Base32-encoded TOTP secret
    totp_confirmed = db.Column(db.Boolean, default=False)  # TOTP setup confirmed
    backup_codes = db.Column(db.Text)  # JSON array of backup codes (hashed)
    
    # Login tracking
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    last_login = db.Column(db.DateTime)
    login_count = db.Column(db.Integer, default=0)  # Total successful logins
    failed_logins = db.Column(db.Integer, default=0)  # Failed login attempts
    
    def set_password(self, password: str):
        """Hash and set password"""
        self.password_hash = generate_password_hash(password)
    
    def check_password(self, password: str) -> bool:
        """Verify password"""
        return check_password_hash(self.password_hash, password)
    
    def to_dict(self):
        """Convert to dictionary"""
        return {
            "id": self.id,
            "username": self.username,
            "email": self.email,
            "full_name": self.full_name,
            "role": self.role,
            "active": self.active,
            "mfa_enabled": self.mfa_enabled,
            "totp_enabled": self.totp_confirmed,  # Legacy compatibility
            "two_factor_enabled": self.totp_confirmed,  # For frontend
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "last_login": self.last_login.isoformat() if self.last_login else None,
            "login_count": self.login_count or 0,
            "failed_logins": self.failed_logins or 0,
        }


class SystemConfig(db.Model):
    """System configuration stored in database"""
    __tablename__ = "system_config"
    
    id = db.Column(db.Integer, primary_key=True)
    key = db.Column(db.String(100), unique=True, nullable=False, index=True)
    value = db.Column(db.Text)
    encrypted = db.Column(db.Boolean, default=False)
    description = db.Column(db.String(255))
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    updated_by = db.Column(db.String(80))
    
    def to_dict(self):
        """Convert to dictionary"""
        return {
            "id": self.id,
            "key": self.key,
            "value": self.value if not self.encrypted else "***",
            "encrypted": self.encrypted,
            "description": self.description,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
            "updated_by": self.updated_by,
        }


class CA(db.Model):
    """Certificate Authority model"""
    __tablename__ = "certificate_authorities"
    
    id = db.Column(db.Integer, primary_key=True)
    refid = db.Column(db.String(36), unique=True, nullable=False, index=True)
    descr = db.Column(db.String(255), nullable=False)
    crt = db.Column(db.Text, nullable=False)  # Base64 encoded
    prv = db.Column(db.Text)  # Base64 encoded private key
    serial = db.Column(db.Integer, default=0)
    caref = db.Column(db.String(36))  # Parent CA refid for intermediate
    
    # Certificate details (parsed from crt)
    subject = db.Column(db.Text)
    issuer = db.Column(db.Text)
    valid_from = db.Column(db.DateTime)
    valid_to = db.Column(db.DateTime)
    
    # Metadata
    imported_from = db.Column(db.String(50))  # 'opnsense', 'manual', 'generated'
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    created_by = db.Column(db.String(80))
    
    # CRL Distribution Points (CDP)
    cdp_enabled = db.Column(db.Boolean, default=False)
    cdp_url = db.Column(db.String(512))  # Ex: http://ucm.local:8443/cdp/{ca_refid}/crl.pem
    
    # OCSP (Online Certificate Status Protocol)
    ocsp_enabled = db.Column(db.Boolean, default=False)
    ocsp_url = db.Column(db.String(512))  # Ex: http://ucm.local:8443/ocsp
    
    # Relationships
    certificates = db.relationship("Certificate", back_populates="ca", lazy="dynamic")
    
    @property
    def has_private_key(self) -> bool:
        """Check if CA has a private key"""
        return bool(self.prv and len(self.prv) > 0)
    
    @property
    def common_name(self) -> str:
        """Extract Common Name from subject"""
        if not self.subject:
            return ""
        for part in self.subject.split(','):
            if part.strip().startswith('CN='):
                return part.strip()[3:]
        return ""
    
    @property
    def organization(self) -> str:
        """Extract Organization from subject"""
        if not self.subject:
            return ""
        for part in self.subject.split(','):
            if part.strip().startswith('O='):
                return part.strip()[2:]
        return ""
    
    @property
    def organizational_unit(self) -> str:
        """Extract Organizational Unit from subject"""
        if not self.subject:
            return ""
        for part in self.subject.split(','):
            if part.strip().startswith('OU='):
                return part.strip()[3:]
        return ""
    
    @property
    def country(self) -> str:
        """Extract Country from subject"""
        if not self.subject:
            return ""
        for part in self.subject.split(','):
            if part.strip().startswith('C='):
                return part.strip()[2:]
        return ""
    
    @property
    def state(self) -> str:
        """Extract State/Province from subject"""
        if not self.subject:
            return ""
        for part in self.subject.split(','):
            if part.strip().startswith('ST='):
                return part.strip()[3:]
        return ""
    
    @property
    def locality(self) -> str:
        """Extract Locality/City from subject"""
        if not self.subject:
            return ""
        for part in self.subject.split(','):
            if part.strip().startswith('L='):
                return part.strip()[2:]
        return ""
    
    @property
    def is_root(self) -> bool:
        """Check if this is a root CA (self-signed)"""
        return self.subject == self.issuer if self.subject and self.issuer else False
    
    @property
    def key_type(self) -> str:
        """Parse key type from certificate"""
        if not self.crt:
            return "N/A"
        try:
            from cryptography import x509
            from cryptography.hazmat.backends import default_backend
            from cryptography.hazmat.primitives.asymmetric import rsa, ec, dsa
            import base64
            
            cert_pem = base64.b64decode(self.crt).decode('utf-8')
            cert = x509.load_pem_x509_certificate(cert_pem.encode(), default_backend())
            public_key = cert.public_key()
            
            if isinstance(public_key, rsa.RSAPublicKey):
                return f"RSA {public_key.key_size}"
            elif isinstance(public_key, ec.EllipticCurvePublicKey):
                return f"EC {public_key.curve.name}"
            elif isinstance(public_key, dsa.DSAPublicKey):
                return f"DSA {public_key.key_size}"
            return "Unknown"
        except:
            return "N/A"
    
    @property
    def hash_algorithm(self) -> str:
        """Parse hash algorithm from certificate"""
        if not self.crt:
            return "N/A"
        try:
            from cryptography import x509
            from cryptography.hazmat.backends import default_backend
            import base64
            
            cert_pem = base64.b64decode(self.crt).decode('utf-8')
            cert = x509.load_pem_x509_certificate(cert_pem.encode(), default_backend())
            return cert.signature_algorithm_oid._name.upper().replace('SHA', 'SHA-')
        except:
            return "N/A"
    
    def to_dict(self, include_private=False):
        """Convert to dictionary"""
        # Determine CA type (lowercase for frontend)
        ca_type = "root" if self.is_root else "intermediate"
        
        # Determine status based on expiry
        status = "Active"
        if self.valid_to:
            if self.valid_to < datetime.utcnow():
                status = "Expired"
        
        # Format dates for frontend
        issued = self.valid_from.strftime("%Y-%m-%d") if self.valid_from else ""
        expires = self.valid_to.strftime("%Y-%m-%d") if self.valid_to else ""
        expiry = self.valid_to.strftime("%Y-%m-%d") if self.valid_to else ""
        
        # Get parent_id (numeric id) from caref (uuid)
        parent_id = None
        if self.caref:
            parent_ca = CA.query.filter_by(refid=self.caref).first()
            parent_id = parent_ca.id if parent_ca else None
        
        data = {
            "id": self.id,
            "refid": self.refid,
            "descr": self.descr,
            "name": self.descr,  # Alias for frontend
            "serial": self.serial,
            "caref": self.caref,
            "parent_id": parent_id,  # Numeric parent ID for frontend tree
            "subject": self.subject,
            "issuer": self.issuer,
            "valid_from": self.valid_from.isoformat() if self.valid_from else None,
            "valid_to": self.valid_to.isoformat() if self.valid_to else None,
            "issued": issued,  # Frontend-friendly date
            "expires": expires,  # Frontend-friendly date
            "expiry": expiry,  # Frontend-friendly date
            "imported_from": self.imported_from,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "created_by": self.created_by,
            "has_private_key": self.has_private_key,
            # Computed properties for display
            "common_name": self.common_name,
            "organization": self.organization,
            "organizational_unit": self.organizational_unit,
            "country": self.country,
            "state": self.state,
            "locality": self.locality,
            "is_root": self.is_root,
            "type": ca_type,  # "Root CA" or "Intermediate"
            "status": status,  # "Active" or "Expired"
            "certs": self.certificates.count() if self.certificates else 0,  # Count of issued certificates
            "key_type": self.key_type,
            "hash_algorithm": self.hash_algorithm,
            # CRL/CDP configuration
            "cdp_enabled": self.cdp_enabled,
            "cdp_url": self.cdp_url,
            # OCSP configuration
            "ocsp_enabled": self.ocsp_enabled,
            "ocsp_url": self.ocsp_url,
            # PEM for display/copy
            "pem": self._decode_pem(self.crt),
        }
        if include_private:
            data["crt"] = self.crt
            data["prv"] = self.prv
        return data
    
    def _decode_pem(self, encoded):
        """Decode base64 encoded PEM"""
        if not encoded:
            return None
        try:
            import base64
            return base64.b64decode(encoded).decode('utf-8')
        except:
            return None


class Certificate(db.Model):
    """Certificate model"""
    __tablename__ = "certificates"
    
    id = db.Column(db.Integer, primary_key=True)
    refid = db.Column(db.String(36), unique=True, nullable=False, index=True)
    descr = db.Column(db.String(255), nullable=False)
    caref = db.Column(db.String(36), db.ForeignKey("certificate_authorities.refid"))
    crt = db.Column(db.Text)  # Nullable - CSR doesn't have cert yet
    csr = db.Column(db.Text)  # Base64 encoded CSR
    prv = db.Column(db.Text)  # Base64 encoded private key
    
    # Certificate details
    cert_type = db.Column(db.String(50))  # client_cert, server_cert, combined_cert, ca_cert
    subject = db.Column(db.Text)
    issuer = db.Column(db.Text)
    serial_number = db.Column(db.String(100))
    valid_from = db.Column(db.DateTime)
    valid_to = db.Column(db.DateTime)
    
    # Subject Alternative Names (SAN)
    san_dns = db.Column(db.Text)  # JSON array of DNS names
    san_ip = db.Column(db.Text)   # JSON array of IP addresses
    san_email = db.Column(db.Text)  # JSON array of email addresses
    san_uri = db.Column(db.Text)  # JSON array of URIs
    
    # OCSP
    ocsp_uri = db.Column(db.String(255))
    
    # Private key management
    private_key_location = db.Column(db.String(20), default='stored')  # 'stored' or 'download_only'
    
    # Status
    revoked = db.Column(db.Boolean, default=False)
    revoked_at = db.Column(db.DateTime)
    revoke_reason = db.Column(db.String(100))
    archived = db.Column(db.Boolean, default=False)  # For renewed certificates
    
    # Metadata
    imported_from = db.Column(db.String(50))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    created_by = db.Column(db.String(80))
    
    # Template reference (optional - null if created without template)
    template_id = db.Column(db.Integer, db.ForeignKey("certificate_templates.id"), nullable=True)
    
    # Relationships
    ca = db.relationship("CA", back_populates="certificates")
    template = db.relationship("CertificateTemplate", foreign_keys=[template_id])
    
    @property
    def has_private_key(self) -> bool:
        """Check if certificate has a private key"""
        return bool(self.prv and len(self.prv) > 0)
    
    @property
    def san_dns_list(self) -> list:
        """Get list of DNS SANs"""
        import json
        if not self.san_dns:
            return []
        try:
            return json.loads(self.san_dns)
        except:
            return []
    
    @property
    def san_ip_list(self) -> list:
        """Get list of IP SANs"""
        import json
        if not self.san_ip:
            return []
        try:
            return json.loads(self.san_ip)
        except:
            return []
    
    @property
    def san_email_list(self) -> list:
        """Get list of Email SANs"""
        import json
        if not self.san_email:
            return []
        try:
            return json.loads(self.san_email)
        except:
            return []
    
    @property
    def san_uri_list(self) -> list:
        """Get list of URI SANs"""
        import json
        if not self.san_uri:
            return []
        try:
            return json.loads(self.san_uri)
        except:
            return []
            
    @property
    def key_type(self) -> str:
        """Parse key type from certificate or CSR"""
        try:
            from cryptography import x509
            from cryptography.hazmat.backends import default_backend
            from cryptography.hazmat.primitives.asymmetric import rsa, ec, dsa
            import base64
            
            # Try parsing CRT first
            if self.crt:
                pem_data = base64.b64decode(self.crt).decode('utf-8')
                obj = x509.load_pem_x509_certificate(pem_data.encode(), default_backend())
                public_key = obj.public_key()
            # Then try parsing CSR
            elif self.csr:
                pem_data = base64.b64decode(self.csr).decode('utf-8')
                obj = x509.load_pem_x509_csr(pem_data.encode(), default_backend())
                public_key = obj.public_key()
            else:
                return "N/A"
            
            if isinstance(public_key, rsa.RSAPublicKey):
                return f"RSA {public_key.key_size}"
            elif isinstance(public_key, ec.EllipticCurvePublicKey):
                return f"EC {public_key.curve.name}"
            elif isinstance(public_key, dsa.DSAPublicKey):
                return f"DSA {public_key.key_size}"
            return "Unknown"
        except Exception:
            return "N/A"
    
    @property
    def common_name(self) -> str:
        """Extract Common Name from subject"""
        if not self.subject:
            return ""
        # Subject format: "CN=example.com,O=Company,..."
        for part in self.subject.split(','):
            if part.strip().startswith('CN='):
                return part.strip()[3:]
        return ""
    
    @property
    def organization(self) -> str:
        """Extract Organization from subject"""
        if not self.subject:
            return ""
        # Subject format: "CN=example.com,O=Company,..."
        for part in self.subject.split(','):
            if part.strip().startswith('O='):
                return part.strip()[2:]
        return ""

    @property
    def organizational_unit(self) -> str:
        """Extract Organizational Unit from subject"""
        if not self.subject:
            return ""
        # Subject format: "CN=example.com,O=Company,OU=Dept,..."
        for part in self.subject.split(','):
            if part.strip().startswith('OU='):
                return part.strip()[3:]
        return ""
    
    @property
    def issuer_name(self) -> str:
        """Extract issuer Common Name"""
        if not self.issuer:
            return ""
        # Issuer format: "CN=CA Name,O=Company,..."
        for part in self.issuer.split(','):
            if part.strip().startswith('CN='):
                return part.strip()[3:]
        return self.issuer
    
    @property
    def not_valid_before(self) -> str:
        """Formatted valid from date"""
        if not self.valid_from:
            return ""
        return self.valid_from.strftime("%Y-%m-%d %H:%M:%S UTC")
    
    @property
    def not_valid_after(self) -> str:
        """Formatted valid until date"""
        if not self.valid_to:
            return ""
        return self.valid_to.strftime("%Y-%m-%d %H:%M:%S UTC")
    
    def to_dict(self, include_private=False):
        """Convert to dictionary"""
        from datetime import datetime, timedelta
        
        # Calculate status
        status = "valid"
        if self.revoked:
            status = "revoked"
        elif self.valid_to:
            now = datetime.utcnow()
            if self.valid_to < now:
                status = "expired"
            elif self.valid_to < now + timedelta(days=30):
                status = "expiring"
        
        data = {
            "id": self.id,
            "refid": self.refid,
            "descr": self.descr,
            "caref": self.caref,
            "cert_type": self.cert_type,
            "subject": self.subject,
            "issuer": self.issuer,
            "serial_number": self.serial_number,
            "valid_from": self.valid_from.isoformat() if self.valid_from else None,
            "valid_to": self.valid_to.isoformat() if self.valid_to else None,
            "revoked": self.revoked,
            "revoked_at": self.revoked_at.isoformat() if self.revoked_at else None,
            "revoke_reason": self.revoke_reason,
            "archived": self.archived or False,
            "imported_from": self.imported_from,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "created_by": self.created_by,
            "has_private_key": self.has_private_key,
            "private_key_location": self.private_key_location,
            # Subject Alternative Names
            "san_dns": self.san_dns,
            "san_ip": self.san_ip,
            "san_email": self.san_email,
            "san_uri": self.san_uri,
            # OCSP
            "ocsp_uri": self.ocsp_uri,
            # Computed properties for display
            "common_name": self.common_name,
            "organization": self.organization,
            "issuer_name": self.issuer_name,
            "not_valid_before": self.not_valid_before,
            "not_valid_after": self.not_valid_after,
            "status": status,
            # PEM for display/copy
            "pem": self._decode_pem(self.crt),
        }
        if include_private:
            data["crt"] = self.crt
            data["csr"] = self.csr
            data["prv"] = self.prv
        return data
    
    def _decode_pem(self, encoded):
        """Decode base64 encoded PEM"""
        if not encoded:
            return None
        try:
            import base64
            return base64.b64decode(encoded).decode('utf-8')
        except:
            return None


class CRL(db.Model):
    """Certificate Revocation List model"""
    __tablename__ = "crls"
    
    id = db.Column(db.Integer, primary_key=True)
    caref = db.Column(db.String(36), nullable=False, index=True)
    descr = db.Column(db.String(255), nullable=False)
    text = db.Column(db.Text, nullable=False)  # Base64 encoded CRL
    serial = db.Column(db.Integer, default=0)
    lifetime = db.Column(db.Integer, default=9999)
    
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    def to_dict(self, include_crl=False):
        """Convert to dictionary"""
        data = {
            "id": self.id,
            "caref": self.caref,
            "descr": self.descr,
            "serial": self.serial,
            "lifetime": self.lifetime,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }
        if include_crl:
            data["text"] = self.text
        return data


class SCEPRequest(db.Model):
    """SCEP enrollment request tracking"""
    __tablename__ = "scep_requests"
    
    id = db.Column(db.Integer, primary_key=True)
    transaction_id = db.Column(db.String(100), unique=True, nullable=False, index=True)
    csr = db.Column(db.Text, nullable=False)  # Base64 encoded
    status = db.Column(db.String(20), default="pending")  # pending, approved, rejected
    approved_by = db.Column(db.String(80))
    approved_at = db.Column(db.DateTime)
    rejection_reason = db.Column(db.String(255))
    
    # Generated certificate
    cert_refid = db.Column(db.String(36))
    
    # Request details
    subject = db.Column(db.Text)
    client_ip = db.Column(db.String(45))
    
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    def to_dict(self):
        """Convert to dictionary"""
        return {
            "id": self.id,
            "transaction_id": self.transaction_id,
            "status": self.status,
            "subject": self.subject,
            "client_ip": self.client_ip,
            "approved_by": self.approved_by,
            "approved_at": self.approved_at.isoformat() if self.approved_at else None,
            "rejection_reason": self.rejection_reason,
            "cert_refid": self.cert_refid,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class AuditLog(db.Model):
    """Audit log for all operations"""
    __tablename__ = "audit_logs"
    
    id = db.Column(db.Integer, primary_key=True)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow, index=True)
    username = db.Column(db.String(80), index=True)
    action = db.Column(db.String(100), nullable=False)  # create_ca, revoke_cert, etc.
    resource_type = db.Column(db.String(50))  # ca, certificate, user, etc.
    resource_id = db.Column(db.String(100))
    resource_name = db.Column(db.String(255))  # Human-readable name (cert CN, user name, CA name)
    details = db.Column(db.Text)
    ip_address = db.Column(db.String(45))
    user_agent = db.Column(db.String(255))
    success = db.Column(db.Boolean, default=True)
    
    def to_dict(self):
        """Convert to dictionary"""
        return {
            "id": self.id,
            "timestamp": self.timestamp.isoformat() if self.timestamp else None,
            "username": self.username,
            "action": self.action,
            "resource_type": self.resource_type,
            "resource_id": self.resource_id,
            "resource_name": self.resource_name,
            "details": self.details,
            "ip_address": self.ip_address,
            "user_agent": self.user_agent,
            "success": self.success,
        }


# Import CRL metadata model
from .crl import CRLMetadata
from .ocsp import OCSPResponse

# Import ACME models
from .acme_models import AcmeAccount, AcmeOrder, AcmeAuthorization, AcmeChallenge, AcmeNonce

__all__ = [
    "db", "User", "SystemConfig", "CA", "Certificate", "CRL", "SCEPRequest", 
    "AuditLog", "CRLMetadata", "OCSPResponse", "CertificateTemplate",
    "AcmeAccount", "AcmeOrder", "AcmeAuthorization", "AcmeChallenge", "AcmeNonce"
]
