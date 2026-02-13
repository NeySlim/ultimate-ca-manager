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


# =============================================================================
# ACME Client Models (UCM as ACME client towards Let's Encrypt)
# =============================================================================

class DnsProvider(db.Model):
    """DNS Provider for automated DNS-01 challenge validation"""
    __tablename__ = 'dns_providers'
    
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    provider_type = db.Column(db.String(50), nullable=False)  # ovh, cloudflare, hetzner, manual, etc.
    credentials = db.Column(db.Text)  # Encrypted JSON with API keys
    zones = db.Column(db.Text)  # JSON array of managed zones/domains
    is_default = db.Column(db.Boolean, default=False)
    enabled = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    client_orders = db.relationship('AcmeClientOrder', back_populates='dns_provider', lazy='dynamic')
    
    @property
    def zones_list(self):
        """Parse zones JSON to list"""
        if not self.zones:
            return []
        try:
            return json.loads(self.zones)
        except:
            return []
    
    def set_zones_list(self, zones):
        """Set zones from array"""
        self.zones = json.dumps(zones)
    
    def to_dict(self, include_credentials=False):
        """Convert to dictionary for API responses"""
        result = {
            'id': self.id,
            'name': self.name,
            'provider_type': self.provider_type,
            'zones': self.zones_list,
            'is_default': self.is_default,
            'enabled': self.enabled,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
        }
        if include_credentials and self.credentials:
            # Only return credential keys, not values (for UI display)
            try:
                creds = json.loads(self.credentials)
                result['credential_keys'] = list(creds.keys())
            except:
                result['credential_keys'] = []
        return result
    
    def __repr__(self):
        return f'<DnsProvider {self.name} ({self.provider_type})>'


class AcmeClientOrder(db.Model):
    """ACME Client Order - Orders initiated BY UCM to external ACME (Let's Encrypt)"""
    __tablename__ = 'acme_client_orders'
    
    id = db.Column(db.Integer, primary_key=True)
    
    # Domain(s) to request certificate for
    domains = db.Column(db.Text, nullable=False)  # JSON array of domains
    
    # Challenge configuration
    challenge_type = db.Column(db.String(20), nullable=False, default='dns-01')  # http-01, dns-01
    environment = db.Column(db.String(20), nullable=False, default='staging')  # staging, production
    
    # Order status
    status = db.Column(db.String(20), default='pending', nullable=False)
    # Status: pending → processing → validating → valid → issued / invalid / expired
    
    # Let's Encrypt references
    order_url = db.Column(db.String(500))  # LE order URL
    account_url = db.Column(db.String(500))  # LE account URL
    finalize_url = db.Column(db.String(500))  # LE finalize URL
    certificate_url = db.Column(db.String(500))  # LE certificate download URL
    
    # Challenge data (for display and verification)
    challenges_data = db.Column(db.Text)  # JSON with challenge tokens, values, etc.
    
    # DNS Provider for DNS-01 challenges
    dns_provider_id = db.Column(db.Integer, db.ForeignKey('dns_providers.id'))
    
    # Resulting certificate (after issuance)
    certificate_id = db.Column(db.Integer, db.ForeignKey('certificates.id'))
    
    # Auto-renewal settings
    renewal_enabled = db.Column(db.Boolean, default=True)
    last_renewal_at = db.Column(db.DateTime)
    renewal_failures = db.Column(db.Integer, default=0)
    
    # Error tracking
    error_message = db.Column(db.Text)
    last_error_at = db.Column(db.DateTime)
    
    # Proxy order fields
    is_proxy_order = db.Column(db.Boolean, default=False)
    dns_records_created = db.Column(db.Text)  # JSON array of record IDs
    client_jwk_thumbprint = db.Column(db.String(64))
    upstream_order_url = db.Column(db.Text)
    upstream_authz_urls = db.Column(db.Text)  # JSON array of authorization URLs
    
    # Timestamps
    expires_at = db.Column(db.DateTime)  # Order expiration
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    dns_provider = db.relationship('DnsProvider', back_populates='client_orders')
    certificate = db.relationship('Certificate', foreign_keys=[certificate_id])
    
    @property
    def domains_list(self):
        """Parse domains JSON to list"""
        if not self.domains:
            return []
        try:
            return json.loads(self.domains)
        except:
            return []
    
    def set_domains_list(self, domains):
        """Set domains from array"""
        self.domains = json.dumps(domains)
    
    @property
    def challenges_dict(self):
        """Parse challenges JSON to dict"""
        if not self.challenges_data:
            return {}
        try:
            return json.loads(self.challenges_data)
        except:
            return {}
    
    def set_challenges_dict(self, challenges):
        """Set challenges from dict"""
        self.challenges_data = json.dumps(challenges)
    
    @property
    def primary_domain(self):
        """Get the primary (first) domain"""
        domains = self.domains_list
        return domains[0] if domains else None
    
    @property
    def is_wildcard(self):
        """Check if order includes wildcard domains"""
        return any(d.startswith('*.') for d in self.domains_list)
    
    def to_dict(self):
        """Convert to dictionary for API responses"""
        return {
            'id': self.id,
            'domains': self.domains_list,
            'primary_domain': self.primary_domain,
            'challenge_type': self.challenge_type,
            'environment': self.environment,
            'status': self.status,
            'order_url': self.order_url,
            'challenges': self.challenges_dict,
            'dns_provider_id': self.dns_provider_id,
            'dns_provider_name': self.dns_provider.name if self.dns_provider else None,
            'certificate_id': self.certificate_id,
            'renewal_enabled': self.renewal_enabled,
            'error_message': self.error_message,
            'expires_at': self.expires_at.isoformat() if self.expires_at else None,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
        }
    
    def __repr__(self):
        return f'<AcmeClientOrder {self.primary_domain} status={self.status}>'


class AcmeDomain(db.Model):
    """ACME Domain - Maps domains to DNS providers and issuing CAs"""
    __tablename__ = 'acme_domains'
    
    id = db.Column(db.Integer, primary_key=True)
    domain = db.Column(db.String(255), unique=True, nullable=False, index=True)
    dns_provider_id = db.Column(db.Integer, db.ForeignKey('dns_providers.id'), nullable=False)
    issuing_ca_id = db.Column(db.Integer, db.ForeignKey('certificate_authorities.id'), nullable=True)
    is_wildcard_allowed = db.Column(db.Boolean, default=True)
    auto_approve = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    created_by = db.Column(db.String(80))
    
    # Relationships
    dns_provider = db.relationship('DnsProvider', backref=db.backref('domains', lazy='dynamic'))
    issuing_ca = db.relationship('CA', foreign_keys='AcmeDomain.issuing_ca_id')
    
    def to_dict(self):
        """Convert to dictionary for API responses"""
        return {
            'id': self.id,
            'domain': self.domain,
            'dns_provider_id': self.dns_provider_id,
            'dns_provider_name': self.dns_provider.name if self.dns_provider else None,
            'dns_provider_type': self.dns_provider.provider_type if self.dns_provider else None,
            'issuing_ca_id': self.issuing_ca_id,
            'issuing_ca_name': self.issuing_ca.common_name if self.issuing_ca else None,
            'is_wildcard_allowed': self.is_wildcard_allowed,
            'auto_approve': self.auto_approve,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
            'created_by': self.created_by,
        }
    
    def __repr__(self):
        return f'<AcmeDomain {self.domain} -> {self.dns_provider.name if self.dns_provider else "?"}>'
