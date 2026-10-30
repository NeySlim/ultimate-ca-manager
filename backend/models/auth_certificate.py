"""
Authentication Certificate Model
Store client certificates for mTLS authentication
"""
from datetime import datetime
from models import db
from utils.datetime_utils import utc_now, utc_isoformat


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
    created_at = db.Column(db.DateTime, default=utc_now)
    last_used_at = db.Column(db.DateTime)
    
    # Relationship
    user = db.relationship('User', backref=db.backref('auth_certificates', lazy='dynamic'))
    
    @property
    def key_facts(self) -> dict:
        """Key facts of the enrolled certificate, from its stored PEM, else from its certificate row."""
        from cryptography import x509
        from utils.key_facts import UNREADABLE, key_facts
        try:
            if self.cert_pem:
                return key_facts(x509.load_pem_x509_certificate(bytes(self.cert_pem)))
            from services.mtls_enrollment import certificate_row_for
            row = certificate_row_for(self)
            return row.key_facts if row is not None else dict(UNREADABLE)
        except Exception:
            return dict(UNREADABLE)

    def to_dict(self):
        """Convert to dictionary"""
        facts = self.key_facts
        return {
            'id': self.id,
            'user_id': self.user_id,
            'cert_serial': self.cert_serial,
            'cert_subject': self.cert_subject,
            'cert_issuer': self.cert_issuer,
            'cert_fingerprint': self.cert_fingerprint,
            'name': self.name,
            'enabled': self.enabled,
            'valid_from': utc_isoformat(self.valid_from),
            'valid_until': utc_isoformat(self.valid_until),
            'created_at': utc_isoformat(self.created_at),
            'last_used_at': utc_isoformat(self.last_used_at),
            'key_type': facts['key_type'],
            'key_algorithm': facts['key_algorithm'],
            'key_size': facts['key_size'],
            'security_level': facts['security_level'],
            'post_quantum': facts['post_quantum'],
        }
