"""
Microsoft AD CS Models
Connection configuration and request tracking for Microsoft Certificate Authority integration.
Secrets are encrypted at rest using Fernet encryption.
"""

from models import db
from datetime import datetime
from utils.datetime_utils import utc_now, utc_isoformat


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

    # CRL revocation sync (#185) — pull the CA's CRL and mark UCM-known certs
    # revoked when they are revoked CA-side. One-way: CA → UCM.
    crl_sync_enabled = db.Column(db.Boolean, default=False)
    crl_url = db.Column(db.Text)
    last_crl_sync_at = db.Column(db.DateTime)
    last_crl_sync_result = db.Column(db.String(500))

    # WinRM admin channel (#185 phase A) — opt-in management operations
    # (revoke/unrevoke/publish CRL/inventory) via certutil over PowerShell
    # remoting. Credentials default to the connection's own; the winrm_*
    # override fields allow a dedicated least-privilege officer account.
    winrm_enabled = db.Column(db.Boolean, default=False)
    winrm_host = db.Column(db.String(500))
    winrm_port = db.Column(db.Integer, default=5986)
    winrm_use_ssl = db.Column(db.Boolean, default=True)
    winrm_verify_ssl = db.Column(db.Boolean, default=True)
    winrm_transport = db.Column(db.String(20), default='kerberos')
    winrm_username = db.Column(db.String(500))
    _winrm_password = db.Column('winrm_password', db.Text)
    ca_config = db.Column(db.String(500))

    # Timestamps
    created_at = db.Column(db.DateTime, default=utc_now)
    updated_at = db.Column(db.DateTime, default=utc_now, onupdate=utc_now)
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
            # Fail-closed: if encryption is broken (missing key, etc.) we
            # MUST NOT silently store the credential in plaintext. Let the
            # exception propagate so the caller sees the failure and the
            # row is never persisted.
            from utils.encryption import encrypt_if_needed
            self._password = encrypt_if_needed(value)
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
            # Fail-closed: never silently store a private key in plaintext
            # if encryption is unavailable.
            from utils.encryption import encrypt_if_needed
            self._client_key_pem = encrypt_if_needed(value)
        else:
            self._client_key_pem = None

    @property
    def winrm_password(self):
        if not self._winrm_password:
            return None
        try:
            from utils.encryption import decrypt_if_needed
            return decrypt_if_needed(self._winrm_password)
        except Exception:
            return self._winrm_password

    @winrm_password.setter
    def winrm_password(self, value):
        if value:
            # Fail-closed: never silently store the credential in plaintext.
            from utils.encryption import encrypt_if_needed
            self._winrm_password = encrypt_if_needed(value)
        else:
            self._winrm_password = None

    # --- WinRM admin channel effective settings -------------------------
    # The admin channel reuses the connection's own credentials unless an
    # override is set. mTLS (certificate) enroll has no reusable WinRM
    # credential, so those connections MUST provide winrm_username/password.

    @property
    def winrm_effective_host(self):
        return self.winrm_host or self.server

    @property
    def winrm_effective_username(self):
        if self.winrm_username:
            return self.winrm_username
        if self.auth_method == 'basic':
            return self.username
        return None

    @property
    def winrm_effective_password(self):
        if self._winrm_password:
            return self.winrm_password
        if self.auth_method == 'basic':
            return self.password
        return None

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
            'last_test_at': utc_isoformat(self.last_test_at),
            'last_test_result': self.last_test_result,
            'crl_sync_enabled': bool(self.crl_sync_enabled),
            'crl_url': self.crl_url or '',
            'last_crl_sync_at': utc_isoformat(self.last_crl_sync_at),
            'last_crl_sync_result': self.last_crl_sync_result,
            'winrm_enabled': bool(self.winrm_enabled),
            'winrm_host': self.winrm_host or '',
            'winrm_port': self.winrm_port or 5986,
            'winrm_use_ssl': bool(self.winrm_use_ssl),
            'winrm_verify_ssl': bool(self.winrm_verify_ssl),
            'winrm_transport': self.winrm_transport or 'kerberos',
            'winrm_username': self.winrm_username or '',
            'winrm_password': '***' if self._winrm_password else None,
            'ca_config': self.ca_config or '',
            'created_at': utc_isoformat(self.created_at),
            'updated_at': utc_isoformat(self.updated_at),
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
    submitted_at = db.Column(db.DateTime, default=utc_now)
    issued_at = db.Column(db.DateTime)
    error_message = db.Column(db.Text)
    cert_pem = db.Column(db.Text)
    submitted_by = db.Column(db.String(80))
    enrollee_name = db.Column(db.String(500))
    enrollee_upn = db.Column(db.String(500))

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
            'submitted_at': utc_isoformat(self.submitted_at),
            'issued_at': utc_isoformat(self.issued_at),
            'error_message': self.error_message,
            'submitted_by': self.submitted_by,
            'enrollee_name': self.enrollee_name,
            'enrollee_upn': self.enrollee_upn,
        }
