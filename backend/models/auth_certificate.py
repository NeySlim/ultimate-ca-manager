"""
Authentication Certificate Model
Store client certificates for mTLS authentication
"""
from datetime import datetime
from models import db


class AuthCertificate(db.Model):
    """Client certificate for mTLS authentication"""
    __tablename__ = 'auth_certificates'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    
    # Certificate data
    cert_pem = db.Column(db.LargeBinary)  # Store certificate PEM for re-download
    
    # Certificate identification
    cert_serial = db.Column(db.String(128), unique=True, nullable=False, index=True)
    cert_subject = db.Column(db.Text, nullable=False)  # Full DN
    cert_issuer = db.Column(db.Text)
    cert_fingerprint = db.Column(db.String(128), index=True)  # SHA256
    
    # Certificate metadata
    name = db.Column(db.String(128))  # User-friendly name
    enabled = db.Column(db.Boolean, default=True, nullable=False)
    
    # Validity dates
    valid_from = db.Column(db.DateTime)
    valid_until = db.Column(db.DateTime)
    
    # Usage tracking
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    last_used_at = db.Column(db.DateTime)
    
    # Relationship
    user = db.relationship('User', backref=db.backref('auth_certificates', lazy='dynamic'))
    
    def to_dict(self):
        """Convert to dictionary"""
        return {
            'id': self.id,
            'user_id': self.user_id,
            'cert_serial': self.cert_serial,
            'cert_subject': self.cert_subject,
            'cert_issuer': self.cert_issuer,
            'cert_fingerprint': self.cert_fingerprint,
            'name': self.name,
            'enabled': self.enabled,
            'valid_from': self.valid_from.isoformat() if self.valid_from else None,
            'valid_until': self.valid_until.isoformat() if self.valid_until else None,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'last_used_at': self.last_used_at.isoformat() if self.last_used_at else None,
        }
