"""
CRL (Certificate Revocation List) Model
RFC 5280 compliant CRL metadata storage
"""
from datetime import datetime
from . import db


class CRLMetadata(db.Model):
    """Certificate Revocation List metadata and storage"""
    __tablename__ = "crl_metadata"
    
    id = db.Column(db.Integer, primary_key=True)
    ca_id = db.Column(db.Integer, db.ForeignKey("certificate_authorities.id"), nullable=False, index=True)
    
    # CRL versioning
    crl_number = db.Column(db.Integer, nullable=False, default=1)
    
    # Validity period (RFC 5280 - Section 5.1.2.4-5)
    this_update = db.Column(db.DateTime, nullable=False)
    next_update = db.Column(db.DateTime, nullable=False)
    
    # CRL data in multiple formats
    crl_pem = db.Column(db.Text, nullable=False)  # PEM encoded CRL
    crl_der = db.Column(db.LargeBinary, nullable=False)  # DER encoded CRL
    
    # Statistics
    revoked_count = db.Column(db.Integer, default=0)
    
    # Metadata
    created_at = db.Column(db.DateTime, default=datetime.utcnow, index=True)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    generated_by = db.Column(db.String(80))  # Username who triggered generation
    
    # Relationship to CA
    ca = db.relationship("CA", backref=db.backref("crl_history", lazy="dynamic"))
    
    def __repr__(self):
        return f"<CRLMetadata ca_id={self.ca_id} number={self.crl_number} revoked={self.revoked_count}>"
    
    @property
    def is_stale(self) -> bool:
        """Check if CRL is past next_update time"""
        if not self.next_update:
            return True
        return datetime.utcnow() > self.next_update
    
    @property
    def days_until_expiry(self) -> int:
        """Calculate days until next_update"""
        if not self.next_update:
            return 0
        delta = self.next_update - datetime.utcnow()
        return max(0, delta.days)
    
    def to_dict(self, include_crl_data=False):
        """Convert to dictionary for API responses"""
        data = {
            "id": self.id,
            "ca_id": self.ca_id,
            "crl_number": self.crl_number,
            "this_update": self.this_update.isoformat() if self.this_update else None,
            "next_update": self.next_update.isoformat() if self.next_update else None,
            "revoked_count": self.revoked_count,
            "is_stale": self.is_stale,
            "days_until_expiry": self.days_until_expiry,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
            "generated_by": self.generated_by,
        }
        if include_crl_data:
            data["crl_pem"] = self.crl_pem
            # crl_der is binary, don't include in JSON by default
        return data
