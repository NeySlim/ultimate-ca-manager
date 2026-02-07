"""
OCSP Response Cache Model
Stores pre-signed OCSP responses for performance
"""
from . import db
from datetime import datetime

class OCSPResponse(db.Model):
    __tablename__ = 'ocsp_responses'
    
    id = db.Column(db.Integer, primary_key=True)
    ca_id = db.Column(db.Integer, db.ForeignKey('certificate_authorities.id'), nullable=False)
    cert_serial = db.Column(db.String(64), nullable=False, index=True)
    
    # OCSP response data
    response_der = db.Column(db.LargeBinary, nullable=False)  # DER-encoded OCSP response
    
    # Metadata
    status = db.Column(db.String(20), nullable=False)  # good, revoked, unknown
    this_update = db.Column(db.DateTime, nullable=False)
    next_update = db.Column(db.DateTime, nullable=False)
    
    # Revocation info (if status = revoked)
    revocation_time = db.Column(db.DateTime)
    revocation_reason = db.Column(db.Integer)  # RFC 5280 CRLReason
    
    # Timestamps
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    
    # Relationships
    ca = db.relationship('CA', backref='ocsp_responses')
    
    # Indexes
    __table_args__ = (
        db.Index('idx_ocsp_ca_serial', 'ca_id', 'cert_serial'),
        db.Index('idx_ocsp_next_update', 'next_update'),
    )
    
    def __repr__(self):
        return f'<OCSPResponse CA={self.ca_id} Serial={self.cert_serial} Status={self.status}>'
    
    def to_dict(self):
        """Convert to dictionary for API responses"""
        return {
            'id': self.id,
            'ca_id': self.ca_id,
            'cert_serial': self.cert_serial,
            'status': self.status,
            'this_update': self.this_update.isoformat() if self.this_update else None,
            'next_update': self.next_update.isoformat() if self.next_update else None,
            'revocation_time': self.revocation_time.isoformat() if self.revocation_time else None,
            'revocation_reason': self.revocation_reason,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
        }
