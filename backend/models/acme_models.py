"""
ACME Protocol Models (RFC 8555)
Automatic Certificate Management Environment
"""
from datetime import datetime, timedelta
from . import db
import secrets
import json


class AcmeAccount(db.Model):
    """ACME Account - RFC 8555 Section 7.1.2"""
    __tablename__ = 'acme_accounts'
    
    id = db.Column(db.Integer, primary_key=True)
    account_id = db.Column(db.String(64), unique=True, nullable=False, index=True)
    key_jwk = db.Column(db.Text, nullable=False)  # JSON Web Key (public key)
    contact = db.Column(db.Text)  # JSON array of contact URIs (mailto:)
    status = db.Column(db.String(20), default='valid', nullable=False)  # valid, deactivated, revoked
    terms_agreed = db.Column(db.Boolean, default=False)
    external_account_binding = db.Column(db.Text)  # EAB for external account binding
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    orders = db.relationship('AcmeOrder', back_populates='account', lazy='dynamic')
    
    @property
    def contact_list(self):
        """Parse contact JSON to list"""
        if not self.contact:
            return []
        try:
            return json.loads(self.contact)
        except:
            return []
    
    def set_contact_list(self, contacts):
        """Set contact list from array"""
        self.contact = json.dumps(contacts)
    
    def to_dict(self):
        """Convert to ACME account object"""
        return {
            'status': self.status,
            'contact': self.contact_list,
            'termsOfServiceAgreed': self.terms_agreed,
            'orders': f'/acme/acct/{self.account_id}/orders',
            'createdAt': self.created_at.isoformat() + 'Z' if self.created_at else None
        }
    
    def __repr__(self):
        return f'<AcmeAccount {self.account_id}>'


class AcmeOrder(db.Model):
    """ACME Order - RFC 8555 Section 7.1.3"""
    __tablename__ = 'acme_orders'
    
    id = db.Column(db.Integer, primary_key=True)
    order_id = db.Column(db.String(64), unique=True, nullable=False, index=True)
    account_id = db.Column(db.String(64), db.ForeignKey('acme_accounts.account_id'), nullable=False)
    status = db.Column(db.String(20), default='pending', nullable=False)
    # Status: pending → ready → processing → valid/invalid
    
    identifiers = db.Column(db.Text, nullable=False)  # JSON array of identifier objects
    not_before = db.Column(db.DateTime)  # Requested validity start
    not_after = db.Column(db.DateTime)   # Requested validity end
    
    error = db.Column(db.Text)  # JSON error object if status=invalid
    
    # Certificate reference when issued
    certificate_id = db.Column(db.Integer, db.ForeignKey('certificates.id'))
    certificate_url = db.Column(db.String(512))  # URL to download certificate
    
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    expires_at = db.Column(db.DateTime, nullable=False)
    
    # Relationships
    account = db.relationship('AcmeAccount', back_populates='orders')
    authorizations = db.relationship('AcmeAuthorization', back_populates='order', lazy='dynamic', cascade='all, delete-orphan')
    certificate = db.relationship('Certificate', foreign_keys=[certificate_id])
    
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        if not self.order_id:
            self.order_id = secrets.token_urlsafe(32)
        if not self.expires_at:
            self.expires_at = datetime.utcnow() + timedelta(days=7)  # Orders expire in 7 days
    
    @property
    def identifiers_list(self):
        """Parse identifiers JSON to list"""
        if not self.identifiers:
            return []
        try:
            return json.loads(self.identifiers)
        except:
            return []
    
    def set_identifiers_list(self, identifiers):
        """Set identifiers from array"""
        self.identifiers = json.dumps(identifiers)
    
    @property
    def authorization_urls(self):
        """Get list of authorization URLs"""
        return [f'/acme/authz/{authz.authz_id}' for authz in self.authorizations]
    
    def to_dict(self):
        """Convert to ACME order object"""
        result = {
            'status': self.status,
            'identifiers': self.identifiers_list,
            'authorizations': self.authorization_urls,
            'finalize': f'/acme/order/{self.order_id}/finalize',
            'expires': self.expires_at.isoformat() + 'Z' if self.expires_at else None
        }
        
        if self.not_before:
            result['notBefore'] = self.not_before.isoformat() + 'Z'
        if self.not_after:
            result['notAfter'] = self.not_after.isoformat() + 'Z'
        if self.error:
            result['error'] = json.loads(self.error) if isinstance(self.error, str) else self.error
        if self.certificate_url:
            result['certificate'] = self.certificate_url
            
        return result
    
    def __repr__(self):
        return f'<AcmeOrder {self.order_id} status={self.status}>'


class AcmeAuthorization(db.Model):
    """ACME Authorization - RFC 8555 Section 7.1.4"""
    __tablename__ = 'acme_authorizations'
    
    id = db.Column(db.Integer, primary_key=True)
    authz_id = db.Column(db.String(64), unique=True, nullable=False, index=True)
    order_id = db.Column(db.String(64), db.ForeignKey('acme_orders.order_id'), nullable=False)
    
    identifier = db.Column(db.String(255), nullable=False)  # Domain name or IP address
    identifier_type = db.Column(db.String(10), nullable=False)  # 'dns' or 'ip'
    
    status = db.Column(db.String(20), default='pending', nullable=False)
    # Status: pending → valid/invalid/deactivated/expired/revoked
    
    expires_at = db.Column(db.DateTime, nullable=False)
    wildcard = db.Column(db.Boolean, default=False)
    
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    validated_at = db.Column(db.DateTime)
    
    # Relationships
    order = db.relationship('AcmeOrder', back_populates='authorizations')
    challenges = db.relationship('AcmeChallenge', back_populates='authorization', lazy='dynamic', cascade='all, delete-orphan')
    
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        if not self.authz_id:
            self.authz_id = secrets.token_urlsafe(32)
        if not self.expires_at:
            self.expires_at = datetime.utcnow() + timedelta(days=7)
    
    def to_dict(self):
        """Convert to ACME authorization object"""
        result = {
            'identifier': {
                'type': self.identifier_type,
                'value': self.identifier
            },
            'status': self.status,
            'expires': self.expires_at.isoformat() + 'Z' if self.expires_at else None,
            'challenges': [challenge.to_dict() for challenge in self.challenges]
        }
        
        if self.wildcard:
            result['wildcard'] = True
            
        return result
    
    def __repr__(self):
        return f'<AcmeAuthorization {self.identifier} status={self.status}>'


class AcmeChallenge(db.Model):
    """ACME Challenge - RFC 8555 Section 7.1.5"""
    __tablename__ = 'acme_challenges'
    
    id = db.Column(db.Integer, primary_key=True)
    challenge_id = db.Column(db.String(64), unique=True, nullable=False, index=True)
    authz_id = db.Column(db.String(64), db.ForeignKey('acme_authorizations.authz_id'), nullable=False)
    
    type = db.Column(db.String(20), nullable=False)  # http-01, dns-01, tls-alpn-01
    status = db.Column(db.String(20), default='pending', nullable=False)
    # Status: pending → processing → valid/invalid
    
    token = db.Column(db.String(64), nullable=False)
    key_authorization = db.Column(db.String(512))  # token + '.' + thumbprint
    
    validated_at = db.Column(db.DateTime)
    error = db.Column(db.Text)  # JSON error object
    
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    
    # Relationships
    authorization = db.relationship('AcmeAuthorization', back_populates='challenges')
    
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        if not self.challenge_id:
            self.challenge_id = secrets.token_urlsafe(32)
        if not self.token:
            self.token = secrets.token_urlsafe(32)
    
    def to_dict(self):
        """Convert to ACME challenge object"""
        result = {
            'type': self.type,
            'status': self.status,
            'url': f'/acme/chall/{self.challenge_id}',
            'token': self.token
        }
        
        if self.validated_at:
            result['validated'] = self.validated_at.isoformat() + 'Z'
        if self.error:
            result['error'] = json.loads(self.error) if isinstance(self.error, str) else self.error
            
        return result
    
    def __repr__(self):
        return f'<AcmeChallenge {self.type} status={self.status}>'


class AcmeNonce(db.Model):
    """ACME Nonce - Anti-replay protection (RFC 8555 Section 6.5)"""
    __tablename__ = 'acme_nonces'
    
    nonce = db.Column(db.String(64), primary_key=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    expires_at = db.Column(db.DateTime, nullable=False)
    used = db.Column(db.Boolean, default=False)
    
    # Index for cleanup
    __table_args__ = (
        db.Index('idx_nonce_expires', 'expires_at'),
    )
    
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        if not self.nonce:
            self.nonce = secrets.token_urlsafe(32)
        if not self.expires_at:
            self.expires_at = datetime.utcnow() + timedelta(hours=1)  # Nonces valid for 1 hour
    
    @staticmethod
    def cleanup_expired():
        """Remove expired nonces"""
        expired = AcmeNonce.query.filter(AcmeNonce.expires_at < datetime.utcnow()).delete()
        db.session.commit()
        return expired
    
    def __repr__(self):
        return f'<AcmeNonce {self.nonce[:16]}...>'
