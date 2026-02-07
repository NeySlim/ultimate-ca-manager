"""
Trusted Certificate Model
Store of trusted root/intermediate certificates
"""
from datetime import datetime
from models import db


class TrustedCertificate(db.Model):
    """Trusted certificate for trust store"""
    __tablename__ = "trusted_certificates"
    
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), nullable=False, index=True)
    description = db.Column(db.Text)
    
    # Certificate data
    certificate_pem = db.Column(db.Text, nullable=False)
    fingerprint_sha256 = db.Column(db.String(64), unique=True, nullable=False, index=True)
    fingerprint_sha1 = db.Column(db.String(40), index=True)
    
    # Certificate details (extracted)
    subject = db.Column(db.String(500))
    issuer = db.Column(db.String(500))
    serial_number = db.Column(db.String(100))
    not_before = db.Column(db.DateTime)
    not_after = db.Column(db.DateTime)
    
    # Purpose
    purpose = db.Column(db.String(100))  # root_ca, intermediate_ca, code_signing, tls_server, custom
    
    # Metadata
    added_by = db.Column(db.String(80))
    added_at = db.Column(db.DateTime, default=datetime.utcnow)
    notes = db.Column(db.Text)
    
    def to_dict(self):
        """Convert to dictionary"""
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "certificate_pem": self.certificate_pem,
            "fingerprint_sha256": self.fingerprint_sha256,
            "fingerprint_sha1": self.fingerprint_sha1,
            "subject": self.subject,
            "issuer": self.issuer,
            "serial_number": self.serial_number,
            "not_before": self.not_before.isoformat() if self.not_before else None,
            "not_after": self.not_after.isoformat() if self.not_after else None,
            "purpose": self.purpose,
            "added_by": self.added_by,
            "added_at": self.added_at.isoformat() if self.added_at else None,
            "notes": self.notes,
        }
