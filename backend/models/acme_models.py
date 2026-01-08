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
    account_id = db.Column(db.String(64), unique=True, nullable=False, index=True, default=lambda: secrets.token_urlsafe(32))
    jwk = db.Column(db.Text, nullable=False)  # JSON Web Key (public key)
    jwk_thumbprint = db.Column(db.String(128), unique=True, nullable=False, index=True)
    contact = db.Column(db.Text)  # JSON array of contact URIs (mailto:)
    status = db.Column(db.String(20), default='valid', nullable=False)  # valid, deactivated, revoked
    terms_of_service_agreed = db.Column(db.Boolean, default=False)
    external_account_binding = db.Column(db.Text)  # EAB for external account binding
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    orders = db.relationship('AcmeOrder', back_populates='account', lazy='dynamic', cascade='all, delete-orphan')
    
    @property
    def contact_list(self):
        """Parse contact JSON to list"""
        if not self.contact:
            return []
        try:
            return json.loads(self.contact)
        except:
            return []
    
    def to_dict(self):
        """Convert to ACME account object"""
        return {
            'status': self.status,
            'contact': self.contact_list,
            'termsOfServiceAgreed': self.terms_of_service_agreed,
            'orders': f'/acme/acct/{self.account_id}/orders',
            'createdAt': self.created_at.isoformat() + 'Z' if self.created_at else None
        }
    
    def __repr__(self):
        return f'<AcmeAccount {self.account_id}>'


class AcmeOrder(db.Model):
    """ACME Order - RFC 8555 Section 7.1.3"""
    __tablename__ = 'acme_orders'
    
    id = db.Column(db.Integer, primary_key=True)
    order_id = db.Column(db.String(64), unique=True, nullable=False, index=True, default=lambda: secrets.token_urlsafe(32))
    account_id = db.Column(db.String(64), db.ForeignKey('acme_accounts.account_id'), nullable=False)
    status = db.Column(db.String(20), default='pending', nullable=False)
    # Status: pending → ready → processing → valid/invalid
    
    identifiers = db.Column(db.Text, nullable=False)  # JSON array of identifier objects
    not_before = db.Column(db.DateTime)  # Requested validity start
    not_after = db.Column(db.DateTime)   # Requested validity end
    
    error = db.Column(db.Text)  # JSON error object if status=invalid
    csr = db.Column(db.Text)  # Certificate Signing Request (PEM)
    
    # Certificate reference when issued
    certificate_id = db.Column(db.Integer, db.ForeignKey('certificates.id'))
    certificate_url = db.Column(db.String(512))  # URL to download certificate
    
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    expires = db.Column(db.DateTime, default=lambda: datetime.utcnow() + timedelta(days=7), nullable=False)
    
    # Relationships
    account = db.relationship('AcmeAccount', back_populates='orders')
    authorizations = db.relationship('AcmeAuthorization', back_populates='order', lazy='dynamic', cascade='all, delete-orphan')
    certificate = db.relationship('Certificate', foreign_keys=[certificate_id])
    
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
    authorization_id = db.Column(db.String(64), unique=True, nullable=False, index=True, default=lambda: secrets.token_urlsafe(32))
    order_id = db.Column(db.String(64), db.ForeignKey('acme_orders.order_id'), nullable=False)
    
    identifier = db.Column(db.Text, nullable=False)  # JSON of {"type": "dns", "value": "example.com"}
    
    status = db.Column(db.String(20), default='pending', nullable=False)
    # Status: pending → valid/invalid/deactivated/expired/revoked
    
    expires = db.Column(db.DateTime, default=lambda: datetime.utcnow() + timedelta(days=7), nullable=False)
    wildcard = db.Column(db.Boolean, default=False)
    
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    
    # Relationships
    order = db.relationship('AcmeOrder', back_populates='authorizations')
    challenges = db.relationship('AcmeChallenge', back_populates='authorization', lazy='dynamic', cascade='all, delete-orphan')
    
    def to_dict(self):
        """Convert to ACME authorization object"""
        identifier_obj = json.loads(self.identifier) if isinstance(self.identifier, str) else self.identifier
        
        result = {
            'identifier': identifier_obj,
            'status': self.status,
            'expires': self.expires.isoformat() + 'Z' if self.expires else None,
            'challenges': [challenge.to_dict() for challenge in self.challenges]
        }
        
        if self.wildcard:
            result['wildcard'] = True
            
        return result
    
    def __repr__(self):
        return f'<AcmeAuthorization {self.authorization_id} status={self.status}>'


class AcmeChallenge(db.Model):
    """ACME Challenge - RFC 8555 Section 7.1.5"""
    __tablename__ = 'acme_challenges'
    
    id = db.Column(db.Integer, primary_key=True)
    challenge_id = db.Column(db.String(64), unique=True, nullable=False, index=True, default=lambda: secrets.token_urlsafe(32))
    authorization_id = db.Column(db.String(64), db.ForeignKey('acme_authorizations.authorization_id'), nullable=False)
    
    type = db.Column(db.String(20), nullable=False)  # http-01, dns-01, tls-alpn-01
    status = db.Column(db.String(20), default='pending', nullable=False)
    # Status: pending → processing → valid/invalid
    
    token = db.Column(db.String(64), nullable=False, default=lambda: secrets.token_urlsafe(32))
    url = db.Column(db.String(512))  # Challenge URL
    
    validated = db.Column(db.DateTime)
    error = db.Column(db.Text)  # JSON error object
    
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    
    # Relationships
    authorization = db.relationship('AcmeAuthorization', back_populates='challenges')
    
    def to_dict(self):
        """Convert to ACME challenge object"""
        result = {
            'type': self.type,
            'status': self.status,
            'url': self.url or f'/acme/chall/{self.challenge_id}',
            'token': self.token
        }
        
        if self.validated:
            result['validated'] = self.validated.isoformat() + 'Z'
        if self.error:
            result['error'] = json.loads(self.error) if isinstance(self.error, str) else self.error
            
        return result
    
    def __repr__(self):
        return f'<AcmeChallenge {self.type} status={self.status}>'


class AcmeNonce(db.Model):
    """ACME Nonce - Anti-replay protection (RFC 8555 Section 6.5)"""
    __tablename__ = 'acme_nonces'
    
    id = db.Column(db.Integer, primary_key=True)
    token = db.Column(db.String(64), unique=True, nullable=False, index=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    expires_at = db.Column(db.DateTime, nullable=False)
    used = db.Column(db.Boolean, default=False)
    used_at = db.Column(db.DateTime)
    
    # Index for cleanup
    __table_args__ = (
        db.Index('idx_nonce_expires', 'expires_at'),
    )
    
    @staticmethod
    def cleanup_expired():
        """Remove expired nonces"""
        expired = AcmeNonce.query.filter(AcmeNonce.expires_at < datetime.utcnow()).delete()
        db.session.commit()
        return expired
    
    def __repr__(self):
        return f'<AcmeNonce {self.token[:16]}...>'
