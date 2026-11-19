"""
CRL (Certificate Revocation List) Model
RFC 5280 compliant CRL metadata storage
"""
from datetime import datetime
from . import db
from utils.datetime_utils import utc_now, utc_isoformat


class CRLMetadata(db.Model):
    """Certificate Revocation List metadata and storage"""
    __tablename__ = "crl_metadata"
    # RFC 5280 §5.2.3: two CRLs of one issuer never share a number
    __table_args__ = (db.Index('uix_crl_ca_number', 'ca_id', 'crl_number', unique=True),)
    
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
    
    # Delta CRL support (RFC 5280 §5.2.4)
    is_delta = db.Column(db.Boolean, default=False)
    base_crl_number = db.Column(db.Integer)  # Base CRL number for delta CRLs

    # Externally-signed CRL uploaded for a key-less/offline CA (#302)
    is_external = db.Column(db.Boolean, default=False)
    
    # Statistics
    revoked_count = db.Column(db.Integer, default=0)
    
    # Metadata
    created_at = db.Column(db.DateTime, default=utc_now, index=True)
    updated_at = db.Column(db.DateTime, default=utc_now, onupdate=utc_now)
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
        return utc_now() > self.next_update
    
    @property
    def days_until_expiry(self) -> int:
        """Calculate days until next_update"""
        if not self.next_update:
            return 0
        delta = self.next_update - utc_now()
        return max(0, delta.days)
    
    def to_dict(self, include_crl_data=False):
        """Convert to dictionary for API responses"""
        data = {
            "id": self.id,
            "ca_id": self.ca_id,
            "crl_number": self.crl_number,
            "this_update": utc_isoformat(self.this_update),
            "next_update": utc_isoformat(self.next_update),
            "revoked_count": self.revoked_count,
            "is_stale": self.is_stale,
            "days_until_expiry": self.days_until_expiry,
            "created_at": utc_isoformat(self.created_at),
            "updated_at": utc_isoformat(self.updated_at),
            "generated_by": self.generated_by,
            "is_delta": self.is_delta or False,
            "base_crl_number": self.base_crl_number,
            "is_external": self.is_external or False,
        }
        if include_crl_data:
            data["crl_pem"] = self.crl_pem
            # crl_der is binary, don't include in JSON by default
        return data


class CRLNumberCounter(db.Model):
    """Highest CRL number an issuer has published, keyed by its name and key.

    No foreign key: it outlives the CA row, so a CA deleted then imported again,
    or restored elsewhere, continues its numbering (RFC 5280 §5.2.3).
    """
    __tablename__ = "crl_number_counters"

    id = db.Column(db.Integer, primary_key=True)
    # services/crl/numbering.py: SHA-256 of the subject DER and the SPKI DER
    issuer_key = db.Column(db.String(64), nullable=False, unique=True, index=True)
    last_number = db.Column(db.Integer, nullable=False, default=0)
    updated_at = db.Column(db.DateTime, default=utc_now, onupdate=utc_now)
