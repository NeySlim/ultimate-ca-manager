"""
WebAuthn Credentials Model
Store FIDO2/U2F authentication credentials
"""
from datetime import datetime
from models import db


class WebAuthnCredential(db.Model):
    """WebAuthn/FIDO2 credential for passwordless authentication"""
    __tablename__ = 'webauthn_credentials'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    
    # Credential identification (from WebAuthn spec)
    credential_id = db.Column(db.LargeBinary, unique=True, nullable=False, index=True)  # Binary credential ID
    public_key = db.Column(db.LargeBinary, nullable=False)  # COSE-encoded public key
    
    # Counter for replay protection (increments with each use)
    sign_count = db.Column(db.Integer, default=0, nullable=False)
    
    # Authenticator metadata
    name = db.Column(db.String(128))  # User-friendly name ("YubiKey 5 NFC", "TouchID", etc.)
    aaguid = db.Column(db.String(36))  # Authenticator GUID (identifies model)
    
    # Transports supported by authenticator
    transports = db.Column(db.Text)  # JSON: ["usb", "nfc", "ble", "internal"]
    
    # Credential flags
    is_backup_eligible = db.Column(db.Boolean, default=False)  # Can be backed up (passkey)
    is_backup_device = db.Column(db.Boolean, default=False)  # Is currently backed up
    user_verified = db.Column(db.Boolean, default=False)  # Requires user verification (PIN/biometric)
    
    # Status
    enabled = db.Column(db.Boolean, default=True, nullable=False)
    
    # Usage tracking
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    last_used_at = db.Column(db.DateTime)
    
    # Relationship
    user = db.relationship('User', backref=db.backref('webauthn_credentials', lazy='dynamic'))
    
    def to_dict(self):
        """Convert to dictionary"""
        import base64
        import json
        
        return {
            'id': self.id,
            'user_id': self.user_id,
            'credential_id': base64.b64encode(self.credential_id).decode('utf-8'),
            'name': self.name,
            'aaguid': self.aaguid,
            'transports': json.loads(self.transports) if self.transports else [],
            'is_backup_eligible': self.is_backup_eligible,
            'is_backup_device': self.is_backup_device,
            'user_verified': self.user_verified,
            'enabled': self.enabled,
            'sign_count': self.sign_count,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'last_used_at': self.last_used_at.isoformat() if self.last_used_at else None,
        }


class WebAuthnChallenge(db.Model):
    """Temporary challenge for WebAuthn registration/authentication"""
    __tablename__ = 'webauthn_challenges'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    
    challenge = db.Column(db.String(128), unique=True, nullable=False, index=True)
    challenge_type = db.Column(db.String(20), nullable=False)  # 'registration' or 'authentication'
    
    # Expires after a short time (typically 2-5 minutes)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    expires_at = db.Column(db.DateTime, nullable=False)
    used = db.Column(db.Boolean, default=False)
    
    # Relationship
    user = db.relationship('User', backref=db.backref('webauthn_challenges', lazy='dynamic'))
    
    def is_valid(self) -> bool:
        """Check if challenge is still valid"""
        return not self.used and datetime.utcnow() < self.expires_at
