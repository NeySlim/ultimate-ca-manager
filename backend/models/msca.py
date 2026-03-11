"""
Microsoft AD CS Models
Connection configuration and request tracking for Microsoft Certificate Authority integration.
Secrets are encrypted at rest using Fernet encryption.
"""

from models import db
from datetime import datetime


class MicrosoftCA(db.Model):
    """Microsoft AD CS connection configuration"""
    __tablename__ = 'microsoft_cas'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False, unique=True)
    server = db.Column(db.String(500), nullable=False)
    ca_name = db.Column(db.String(200))
    auth_method = db.Column(db.String(20), nullable=False, default='certificate')

    # Basic auth credentials (encrypted)
    username = db.Column(db.String(500))
    _password = db.Column('password', db.String(500))

    # Client certificate auth (encrypted)
    client_cert_pem = db.Column(db.Text)
    _client_key_pem = db.Column('client_key_pem', db.Text)

    # Kerberos auth
    kerberos_principal = db.Column(db.String(500))
    kerberos_keytab_path = db.Column(db.String(500))

    # SSL/TLS settings
    use_ssl = db.Column(db.Boolean, default=True)
    verify_ssl = db.Column(db.Boolean, default=True)
    ca_bundle = db.Column(db.Text)

    # Default settings
    default_template = db.Column(db.String(200), default='WebServer')

    # Status
    enabled = db.Column(db.Boolean, default=True)
    last_test_at = db.Column(db.DateTime)
    last_test_result = db.Column(db.String(500))

    # Timestamps
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    created_by = db.Column(db.String(80))

    # Relationships
    requests = db.relationship('MSCARequest', backref='msca', lazy='dynamic',
                               cascade='all, delete-orphan')

    # --- Encrypted property accessors ---

    @property
    def password(self):
        if not self._password:
            return None
        try:
            from utils.encryption import decrypt_if_needed
            return decrypt_if_needed(self._password)
        except Exception:
            return self._password

    @password.setter
    def password(self, value):
        if value:
            try:
                from utils.encryption import encrypt_if_needed
                self._password = encrypt_if_needed(value)
            except Exception:
                self._password = value
        else:
            self._password = None

    @property
    def client_key_pem(self):
        if not self._client_key_pem:
            return None
        try:
            from utils.encryption import decrypt_if_needed
            return decrypt_if_needed(self._client_key_pem)
        except Exception:
            return self._client_key_pem

    @client_key_pem.setter
    def client_key_pem(self, value):
        if value:
            try:
                from utils.encryption import encrypt_if_needed
                self._client_key_pem = encrypt_if_needed(value)
            except Exception:
                self._client_key_pem = value
        else:
            self._client_key_pem = None

    def to_dict(self, include_secrets=False):
        """Convert to dictionary, masking secrets by default"""
        data = {
            'id': self.id,
            'name': self.name,
            'server': self.server,
            'ca_name': self.ca_name,
            'auth_method': self.auth_method,
            'use_ssl': self.use_ssl,
            'verify_ssl': self.verify_ssl,
            'ca_bundle': self.ca_bundle or '',
            'default_template': self.default_template,
            'enabled': self.enabled,
            'last_test_at': self.last_test_at.isoformat() if self.last_test_at else None,
            'last_test_result': self.last_test_result,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
            'created_by': self.created_by,
        }

        if self.auth_method == 'basic':
            data['username'] = self.username
            data['password'] = '***' if self._password else None
            if include_secrets:
                data['password'] = self.password
        elif self.auth_method == 'certificate':
            data['client_cert_pem'] = self.client_cert_pem or ''
            data['client_key_pem'] = '***' if self._client_key_pem else None
            if include_secrets:
                data['client_key_pem'] = self.client_key_pem
        elif self.auth_method == 'kerberos':
            data['kerberos_principal'] = self.kerberos_principal
            data['kerberos_keytab_path'] = self.kerberos_keytab_path

        return data


class MSCARequest(db.Model):
    """Track CSR signing requests submitted to Microsoft AD CS"""
    __tablename__ = 'msca_requests'

    id = db.Column(db.Integer, primary_key=True)
    msca_id = db.Column(db.Integer, db.ForeignKey('microsoft_cas.id'), nullable=False)
    csr_id = db.Column(db.Integer, db.ForeignKey('certificates.id'))
    cert_id = db.Column(db.Integer, db.ForeignKey('certificates.id'))
    request_id = db.Column(db.Integer)
    disposition_message = db.Column(db.Text)
    template = db.Column(db.String(200), nullable=False)
    status = db.Column(db.String(20), default='submitted')
    submitted_at = db.Column(db.DateTime, default=datetime.utcnow)
    issued_at = db.Column(db.DateTime)
    error_message = db.Column(db.Text)
    cert_pem = db.Column(db.Text)
    submitted_by = db.Column(db.String(80))

    def to_dict(self):
        return {
            'id': self.id,
            'msca_id': self.msca_id,
            'msca_name': self.msca.name if self.msca else None,
            'csr_id': self.csr_id,
            'cert_id': self.cert_id,
            'request_id': self.request_id,
            'disposition_message': self.disposition_message,
            'template': self.template,
            'status': self.status,
            'submitted_at': self.submitted_at.isoformat() if self.submitted_at else None,
            'issued_at': self.issued_at.isoformat() if self.issued_at else None,
            'error_message': self.error_message,
            'submitted_by': self.submitted_by,
        }
