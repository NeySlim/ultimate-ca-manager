"""
Discovered Certificate Model
Stores certificates found through network scanning
"""
from datetime import datetime
from models import db, Certificate


class DiscoveredCertificate(db.Model):
    """Model for certificates discovered through network scanning"""
    
    __tablename__ = 'discovered_certificate'
    
    id = db.Column(db.Integer, primary_key=True)
    target = db.Column(db.String(1024), nullable=False, index=True)
    certificate = db.Column(db.Text, nullable=False)
    issuer = db.Column(db.String(1024))
    subject = db.Column(db.String(1024))
    serial = db.Column(db.String(64), index=True)
    not_before = db.Column(db.DateTime)
    not_after = db.Column(db.DateTime)
    fingerprint = db.Column(db.String(64), unique=True, index=True)
    status = db.Column(db.String(32), default='unknown', index=True)
    last_seen = db.Column(db.DateTime, default=datetime.utcnow, index=True)
    ucm_certificate_id = db.Column(db.Integer, db.ForeignKey('certificates.id'))
    
    # Relationship
    ucm_certificate = db.relationship('Certificate', backref='discovered_certificates')
    
    def __repr__(self):
        return f'<DiscoveredCertificate {self.target} - {self.subject}>'
    
    def to_dict(self):
        """Convert model to dictionary"""
        return {
            'id': self.id,
            'target': self.target,
            'certificate': self.certificate,
            'issuer': self.issuer,
            'subject': self.subject,
            'serial': self.serial,
            'not_before': self.not_before.isoformat() if self.not_before else None,
            'not_after': self.not_after.isoformat() if self.not_after else None,
            'fingerprint': self.fingerprint,
            'status': self.status,
            'last_seen': self.last_seen.isoformat(),
            'ucm_certificate_id': self.ucm_certificate_id,
            'is_expired': self.is_expired()
        }
    
    def is_expired(self):
        """Check if certificate is expired"""
        if not self.not_after:
            return False
        return datetime.utcnow() > self.not_after
    
    def is_known(self):
        """Check if certificate is already in UCM"""
        return self.status == 'known'
    
    def is_unknown(self):
        """Check if certificate is not in UCM"""
        return self.status == 'unknown'
