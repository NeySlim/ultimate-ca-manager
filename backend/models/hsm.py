"""
HSM Models - Hardware Security Module integration
Supports PKCS#11, Azure Key Vault, Google Cloud KMS, AWS CloudHSM
"""

from datetime import datetime
import json

try:
    from models import db
except ImportError:
    db = None


class HsmProvider(db.Model if db else object):
    """
    HSM Provider configuration
    Stores connection details for various HSM types
    """
    
    __tablename__ = 'hsm_providers'
    
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(255), nullable=False, unique=True)
    
    # Provider type: pkcs11, aws-cloudhsm, azure-keyvault, google-kms
    type = db.Column(db.String(50), nullable=False, index=True)
    
    # JSON configuration (encrypted at application level)
    # Contains connection details, credentials, etc.
    config = db.Column(db.Text, nullable=False)
    
    # Connection status
    status = db.Column(db.String(20), default='unknown')  # connected, disconnected, error, unknown
    last_tested_at = db.Column(db.DateTime, nullable=True)
    error_message = db.Column(db.Text, nullable=True)
    
    # Audit fields
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    created_by = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    
    # Relationships
    keys = db.relationship('HsmKey', backref='provider', lazy='dynamic', cascade='all, delete-orphan')
    creator = db.relationship('User', foreign_keys=[created_by])
    
    # Valid provider types
    VALID_TYPES = ['pkcs11', 'aws-cloudhsm', 'azure-keyvault', 'google-kms']
    
    # Valid statuses
    VALID_STATUSES = ['connected', 'disconnected', 'error', 'unknown']
    
    def to_dict(self, include_config=False):
        """
        Convert to dict for API response
        Config is excluded by default for security
        """
        result = {
            'id': self.id,
            'name': self.name,
            'type': self.type,
            'status': self.status,
            'last_tested_at': self.last_tested_at.isoformat() if self.last_tested_at else None,
            'error_message': self.error_message,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
            'key_count': self.keys.count() if self.keys else 0
        }
        
        if include_config:
            # Parse config but mask sensitive fields
            try:
                config = json.loads(self.config)
                # Mask sensitive fields
                masked_config = {}
                for key, value in config.items():
                    if any(s in key.lower() for s in ['password', 'secret', 'pin', 'key', 'token', 'credential']):
                        masked_config[key] = '********' if value else None
                    else:
                        masked_config[key] = value
                result['config'] = masked_config
            except (json.JSONDecodeError, TypeError):
                result['config'] = {}
        
        return result
    
    def get_config(self):
        """Get parsed configuration"""
        try:
            return json.loads(self.config)
        except (json.JSONDecodeError, TypeError):
            return {}
    
    def set_config(self, config_dict):
        """Set configuration from dict"""
        self.config = json.dumps(config_dict)
    
    def __repr__(self):
        return f'<HsmProvider {self.name} ({self.type})>'


class HsmKey(db.Model if db else object):
    """
    HSM Key reference
    Represents a cryptographic key stored in an HSM
    """
    
    __tablename__ = 'hsm_keys'
    
    id = db.Column(db.Integer, primary_key=True)
    provider_id = db.Column(db.Integer, db.ForeignKey('hsm_providers.id', ondelete='CASCADE'), nullable=False, index=True)
    
    # HSM-internal key identifier (varies by provider)
    key_identifier = db.Column(db.String(255), nullable=False)
    
    # User-friendly label
    label = db.Column(db.String(255), nullable=False)
    
    # Key algorithm: RSA-2048, RSA-3072, RSA-4096, EC-P256, EC-P384, EC-P521, AES-128, AES-256
    algorithm = db.Column(db.String(50), nullable=False, index=True)
    
    # Key type: asymmetric, symmetric
    key_type = db.Column(db.String(20), nullable=False)
    
    # Purpose: signing, encryption, wrapping, all
    purpose = db.Column(db.String(50), nullable=False)
    
    # Public key in PEM format (for asymmetric keys only)
    public_key_pem = db.Column(db.Text, nullable=True)
    
    # Whether key can be extracted from HSM (should be False for security)
    is_extractable = db.Column(db.Boolean, default=False)
    
    # Timestamps
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Extra HSM-specific metadata as JSON
    extra_data = db.Column(db.Text, nullable=True)
    
    # Unique constraint on provider + key_identifier
    __table_args__ = (
        db.UniqueConstraint('provider_id', 'key_identifier', name='uq_hsm_key_provider_identifier'),
    )
    
    # Valid algorithms
    VALID_ALGORITHMS = [
        'RSA-2048', 'RSA-3072', 'RSA-4096',
        'EC-P256', 'EC-P384', 'EC-P521',
        'AES-128', 'AES-256'
    ]
    
    # Valid key types
    VALID_KEY_TYPES = ['asymmetric', 'symmetric']
    
    # Valid purposes
    VALID_PURPOSES = ['signing', 'encryption', 'wrapping', 'all']
    
    def to_dict(self):
        """Convert to dict for API response"""
        return {
            'id': self.id,
            'provider_id': self.provider_id,
            'key_identifier': self.key_identifier,
            'label': self.label,
            'algorithm': self.algorithm,
            'key_type': self.key_type,
            'purpose': self.purpose,
            'has_public_key': bool(self.public_key_pem),
            'is_extractable': self.is_extractable,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'metadata': json.loads(self.extra_data) if self.extra_data else None
        }
    
    def get_metadata(self):
        """Get parsed metadata"""
        try:
            return json.loads(self.extra_data) if self.extra_data else {}
        except (json.JSONDecodeError, TypeError):
            return {}
    
    def set_metadata(self, metadata_dict):
        """Set metadata from dict"""
        self.extra_data = json.dumps(metadata_dict) if metadata_dict else None
    
    def __repr__(self):
        return f'<HsmKey {self.label} ({self.algorithm})>'
