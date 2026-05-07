"""
HSM Models - Hardware Security Module integration
Supports PKCS#11, Azure Key Vault, Google Cloud KMS, AWS CloudHSM
"""

from datetime import datetime
import json
from utils.datetime_utils import utc_now, utc_isoformat
from utils.encryption import encrypt_if_needed, decrypt_if_needed, is_encrypted

try:
    from models import db
except ImportError:
    db = None


# Field names whose values are credentials and MUST be encrypted at rest /
# masked in API responses. Exact-match set (case-insensitive) so non-secret
# fields whose names happen to contain a sensitive substring (e.g.
# pkcs11 "token_label", gcp "key_ring") are NOT inadvertently encrypted.
_SENSITIVE_KEYS = frozenset({
    'pin', 'user_pin',
    'password', 'hsm_password',
    'secret', 'client_secret',
    'token',                       # openbao token (NOT token_label)
    'service_account_json',        # gcp — contains private_key
    'private_key',
    'credential', 'access_key_secret',
})
# Values the frontend echoes back when an operator did NOT re-type a password
# (must be preserved as-is, NOT encrypted, NOT stored).
_MASK_SENTINELS = ('***', '********')


def _is_sensitive_key(key: str) -> bool:
    if not key:
        return False
    return key.lower() in _SENSITIVE_KEYS


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
    created_at = db.Column(db.DateTime, default=utc_now)
    updated_at = db.Column(db.DateTime, default=utc_now, onupdate=utc_now)
    created_by = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    
    # Relationships
    keys = db.relationship('HsmKey', backref='provider', lazy='dynamic', cascade='all, delete-orphan')
    creator = db.relationship('User', foreign_keys=[created_by])
    
    # Valid provider types
    VALID_TYPES = ['pkcs11', 'aws-cloudhsm', 'azure-keyvault', 'google-kms', 'openbao']
    
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
            'provider_type': self.type,
            'status': self.status,
            'enabled': self.status == 'connected',
            'last_tested_at': utc_isoformat(self.last_tested_at),
            'error_message': self.error_message,
            'created_at': utc_isoformat(self.created_at),
            'updated_at': utc_isoformat(self.updated_at),
            'key_count': self.keys.count() if self.keys else 0
        }
        
        if include_config:
            # Parse config but mask sensitive fields
            try:
                config = json.loads(self.config)
                # Mask sensitive fields
                masked_config = {}
                for key, value in config.items():
                    if _is_sensitive_key(key):
                        masked_config[key] = '********' if value else None
                    else:
                        masked_config[key] = value
                result['config'] = masked_config

                # Also expose flattened/prefixed fields for frontend form compatibility.
                # Map provider config keys -> provider_<type>_<field> aliases used by the UI.
                type_prefix = {
                    'pkcs11': 'pkcs11',
                    'aws-cloudhsm': 'aws',
                    'azure-keyvault': 'azure',
                    'google-kms': 'gcp',
                    'openbao': 'openbao',
                }.get(self.type)
                if type_prefix:
                    # Per-type field aliases (config_key -> form_field)
                    aliases = {
                        'pkcs11': {
                            'module_path': 'pkcs11_library_path',
                            'token_label': 'pkcs11_token_label',
                            'user_pin': 'pkcs11_pin',
                            'slot_index': 'pkcs11_slot_id',
                        },
                        'aws-cloudhsm': {
                            'cluster_id': 'aws_cluster_id',
                            'region': 'aws_region',
                            'access_key': 'aws_access_key',
                            'hsm_user': 'aws_crypto_user',
                            'hsm_password': 'aws_crypto_password',
                        },
                        'azure-keyvault': {
                            'vault_url': 'azure_vault_url',
                            'tenant_id': 'azure_tenant_id',
                            'client_id': 'azure_client_id',
                            'client_secret': 'azure_client_secret',
                        },
                        'google-kms': {
                            'project_id': 'gcp_project_id',
                            'location': 'gcp_location',
                            'key_ring': 'gcp_keyring',
                            'service_account_json': 'gcp_credentials_json',
                        },
                        'openbao': {
                            'url': 'openbao_url',
                            'token': 'openbao_token',
                            'mount_path': 'openbao_mount_path',
                            'namespace': 'openbao_namespace',
                            'tls_skip_verify': 'openbao_tls_skip_verify',
                        },
                    }.get(self.type, {})
                    for cfg_key, form_field in aliases.items():
                        if cfg_key in masked_config:
                            value = masked_config[cfg_key]
                            # The frontend treats '***' as the "value already set" sentinel
                            # for password-like fields. Translate the masked value.
                            if value == '********':
                                value = '***'
                            result[form_field] = value
            except (json.JSONDecodeError, TypeError):
                result['config'] = {}
        
        return result
    
    def get_config(self):
        """Get parsed configuration with sensitive fields decrypted."""
        try:
            raw = json.loads(self.config)
        except (json.JSONDecodeError, TypeError):
            return {}
        if not isinstance(raw, dict):
            return {}
        decrypted = {}
        for k, v in raw.items():
            if _is_sensitive_key(k) and isinstance(v, str) and v:
                # decrypt_if_needed is a no-op on plaintext (legacy rows pre-v2.152)
                decrypted[k] = decrypt_if_needed(v)
            else:
                decrypted[k] = v
        return decrypted

    def set_config(self, config_dict):
        """Set configuration: encrypt sensitive fields, drop mask sentinels."""
        if not isinstance(config_dict, dict):
            self.config = json.dumps({})
            return
        out = {}
        existing = self.get_config() if self.config else {}
        for k, v in config_dict.items():
            if _is_sensitive_key(k):
                # Frontend echoed back a masked sentinel without re-typing the
                # secret -> preserve the existing (encrypted) value, do NOT
                # overwrite with '***'.
                if isinstance(v, str) and v in _MASK_SENTINELS:
                    if k in existing and existing[k]:
                        out[k] = encrypt_if_needed(existing[k])
                    # else: drop, no value to keep
                    continue
                if isinstance(v, str) and v:
                    out[k] = encrypt_if_needed(v)
                else:
                    out[k] = v
            else:
                out[k] = v
        self.config = json.dumps(out)
    
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
    created_at = db.Column(db.DateTime, default=utc_now)
    
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
            'created_at': utc_isoformat(self.created_at),
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
