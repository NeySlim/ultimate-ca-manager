"""
HSM Models - UCM Pro
Hardware Security Module integration
Secrets are encrypted at rest using Fernet encryption
"""

from models import db
from datetime import datetime
import json


class HSMProvider(db.Model):
    """HSM Provider configuration"""
    __tablename__ = 'pro_hsm_providers'
    
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False, unique=True)
    provider_type = db.Column(db.String(50), nullable=False)  # pkcs11, aws-cloudhsm, azure-keyvault, google-kms
    enabled = db.Column(db.Boolean, default=False)
    is_default = db.Column(db.Boolean, default=False)
    
    # PKCS#11 settings
    pkcs11_library_path = db.Column(db.String(500))
    pkcs11_slot_id = db.Column(db.Integer)
    _pkcs11_pin = db.Column('pkcs11_pin', db.String(500))  # Encrypted
    pkcs11_token_label = db.Column(db.String(200))
    
    # AWS CloudHSM settings
    aws_cluster_id = db.Column(db.String(200))
    aws_region = db.Column(db.String(50))
    aws_access_key = db.Column(db.String(200))
    _aws_secret_key = db.Column('aws_secret_key', db.String(500))  # Encrypted
    aws_crypto_user = db.Column(db.String(200))
    _aws_crypto_password = db.Column('aws_crypto_password', db.String(500))  # Encrypted
    
    # Azure Key Vault settings
    azure_vault_url = db.Column(db.String(500))
    azure_tenant_id = db.Column(db.String(200))
    azure_client_id = db.Column(db.String(200))
    _azure_client_secret = db.Column('azure_client_secret', db.String(500))  # Encrypted
    
    # Google Cloud KMS settings
    gcp_project_id = db.Column(db.String(200))
    gcp_location = db.Column(db.String(100))
    gcp_keyring = db.Column(db.String(200))
    _gcp_credentials_json = db.Column('gcp_credentials_json', db.Text)  # Encrypted
    
    # Connection settings
    connection_timeout = db.Column(db.Integer, default=30)
    retry_count = db.Column(db.Integer, default=3)
    
    # Status
    last_connected_at = db.Column(db.DateTime)
    last_error = db.Column(db.Text)
    
    # Timestamps
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Keys stored in this HSM
    keys = db.relationship('HSMKey', backref='provider', lazy='dynamic', cascade='all, delete-orphan')
    
    # Encrypted property helpers
    def _encrypt(self, value):
        if not value:
            return None
        try:
            from pro.encryption import encrypt_if_needed
            return encrypt_if_needed(value)
        except:
            return value
    
    def _decrypt(self, value):
        if not value:
            return None
        try:
            from pro.encryption import decrypt_if_needed
            return decrypt_if_needed(value)
        except:
            return value
    
    # PKCS#11 PIN
    @property
    def pkcs11_pin(self):
        return self._decrypt(self._pkcs11_pin)
    
    @pkcs11_pin.setter
    def pkcs11_pin(self, value):
        self._pkcs11_pin = self._encrypt(value)
    
    # AWS Secret Key
    @property
    def aws_secret_key(self):
        return self._decrypt(self._aws_secret_key)
    
    @aws_secret_key.setter
    def aws_secret_key(self, value):
        self._aws_secret_key = self._encrypt(value)
    
    # AWS Crypto Password
    @property
    def aws_crypto_password(self):
        return self._decrypt(self._aws_crypto_password)
    
    @aws_crypto_password.setter
    def aws_crypto_password(self, value):
        self._aws_crypto_password = self._encrypt(value)
    
    # Azure Client Secret
    @property
    def azure_client_secret(self):
        return self._decrypt(self._azure_client_secret)
    
    @azure_client_secret.setter
    def azure_client_secret(self, value):
        self._azure_client_secret = self._encrypt(value)
    
    # GCP Credentials JSON
    @property
    def gcp_credentials_json(self):
        return self._decrypt(self._gcp_credentials_json)
    
    @gcp_credentials_json.setter
    def gcp_credentials_json(self, value):
        self._gcp_credentials_json = self._encrypt(value)
    
    def to_dict(self, include_secrets=False):
        """Convert to dictionary"""
        data = {
            'id': self.id,
            'name': self.name,
            'provider_type': self.provider_type,
            'enabled': self.enabled,
            'is_default': self.is_default,
            'connection_timeout': self.connection_timeout,
            'retry_count': self.retry_count,
            'last_connected_at': self.last_connected_at.isoformat() if self.last_connected_at else None,
            'last_error': self.last_error,
            'key_count': self.keys.count(),
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
        }
        
        # Type-specific fields
        if self.provider_type == 'pkcs11':
            data.update({
                'pkcs11_library_path': self.pkcs11_library_path,
                'pkcs11_slot_id': self.pkcs11_slot_id,
                'pkcs11_token_label': self.pkcs11_token_label,
                'pkcs11_pin': '***' if self.pkcs11_pin else None,
            })
            if include_secrets:
                data['pkcs11_pin'] = self.pkcs11_pin
                
        elif self.provider_type == 'aws-cloudhsm':
            data.update({
                'aws_cluster_id': self.aws_cluster_id,
                'aws_region': self.aws_region,
                'aws_access_key': self.aws_access_key,
                'aws_crypto_user': self.aws_crypto_user,
                'aws_secret_key': '***' if self.aws_secret_key else None,
                'aws_crypto_password': '***' if self.aws_crypto_password else None,
            })
            if include_secrets:
                data['aws_secret_key'] = self.aws_secret_key
                data['aws_crypto_password'] = self.aws_crypto_password
                
        elif self.provider_type == 'azure-keyvault':
            data.update({
                'azure_vault_url': self.azure_vault_url,
                'azure_tenant_id': self.azure_tenant_id,
                'azure_client_id': self.azure_client_id,
                'azure_client_secret': '***' if self.azure_client_secret else None,
            })
            if include_secrets:
                data['azure_client_secret'] = self.azure_client_secret
                
        elif self.provider_type == 'google-kms':
            data.update({
                'gcp_project_id': self.gcp_project_id,
                'gcp_location': self.gcp_location,
                'gcp_keyring': self.gcp_keyring,
                'gcp_credentials_json': '***' if self.gcp_credentials_json else None,
            })
            if include_secrets:
                data['gcp_credentials_json'] = self.gcp_credentials_json
        
        return data


class HSMKey(db.Model):
    """Keys stored in HSM"""
    __tablename__ = 'pro_hsm_keys'
    
    id = db.Column(db.Integer, primary_key=True)
    provider_id = db.Column(db.Integer, db.ForeignKey('pro_hsm_providers.id'), nullable=False)
    
    # Key identification
    key_label = db.Column(db.String(200), nullable=False)
    key_id = db.Column(db.String(500))  # HSM-specific key ID/handle
    key_type = db.Column(db.String(50))  # rsa, ec, aes
    key_size = db.Column(db.Integer)  # 2048, 4096 for RSA; 256, 384 for EC
    
    # Usage
    purpose = db.Column(db.String(100))  # ca_signing, code_signing, encryption
    is_exportable = db.Column(db.Boolean, default=False)
    
    # Associated CA (if this key is for a CA)
    ca_id = db.Column(db.Integer, db.ForeignKey('certificate_authorities.id'))
    
    # Status
    status = db.Column(db.String(50), default='active')  # active, disabled, destroyed
    
    # Timestamps
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    last_used_at = db.Column(db.DateTime)
    
    def to_dict(self):
        return {
            'id': self.id,
            'provider_id': self.provider_id,
            'provider_name': self.provider.name if self.provider else None,
            'key_label': self.key_label,
            'key_id': self.key_id,
            'key_type': self.key_type,
            'key_size': self.key_size,
            'purpose': self.purpose,
            'is_exportable': self.is_exportable,
            'ca_id': self.ca_id,
            'status': self.status,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'last_used_at': self.last_used_at.isoformat() if self.last_used_at else None,
        }
