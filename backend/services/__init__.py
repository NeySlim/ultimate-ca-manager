"""
Database Models for Ultimate CA Manager
"""
from datetime import datetime
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash

db = SQLAlchemy()


class User(db.Model):
    """User model for authentication"""
    __tablename__ = "users"
    
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False, index=True)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(20), nullable=False, default="viewer")  # admin, operator, viewer
    active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    last_login = db.Column(db.DateTime)
    
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
            "role": self.role,
            "active": self.active,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "last_login": self.last_login.isoformat() if self.last_login else None,
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
    
    # Relationships
    certificates = db.relationship("Certificate", back_populates="ca", lazy="dynamic")
    
    def to_dict(self, include_private=False):
        """Convert to dictionary"""
        data = {
            "id": self.id,
            "refid": self.refid,
            "descr": self.descr,
            "serial": self.serial,
            "caref": self.caref,
            "subject": self.subject,
            "issuer": self.issuer,
            "valid_from": self.valid_from.isoformat() if self.valid_from else None,
            "valid_to": self.valid_to.isoformat() if self.valid_to else None,
            "imported_from": self.imported_from,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "has_private_key": bool(self.prv and len(self.prv) > 0),  # Boolean indicator
        }
        if include_private:
            data["crt"] = self.crt
            data["prv"] = self.prv
        return data


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
    
    # Metadata
    imported_from = db.Column(db.String(50))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    created_by = db.Column(db.String(80))
    
    # Relationships
    ca = db.relationship("CA", back_populates="certificates")
    
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
            "imported_from": self.imported_from,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "has_private_key": self.has_private_key,
            # Computed properties for display
            "common_name": self.common_name,
            "organization": self.organization,
            "issuer_name": self.issuer_name,
            "not_valid_before": self.not_valid_before,
            "not_valid_after": self.not_valid_after,
        }
        if include_private:
            data["crt"] = self.crt
            data["csr"] = self.csr
            data["prv"] = self.prv
        return data


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
    
    def to_dict(self):
        """Convert to dictionary"""
        return {
            "id": self.id,
            "caref": self.caref,
            "descr": self.descr,
            "serial": self.serial,
            "lifetime": self.lifetime,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


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
            "details": self.details,
            "ip_address": self.ip_address,
            "success": self.success,
        }
