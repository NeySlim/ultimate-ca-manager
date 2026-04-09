"""
SSH Certificate Authority Models

SSH CAs are separate from X.509 CAs — they use the OpenSSH certificate format
(PROTOCOL.certkeys) rather than X.509v3. Two models:

- SSHCertificateAuthority: stores CA key pair, type (user/host), serial counter
- SSHCertificate: stores issued SSH certificates with principals, extensions, etc.

Uses `cryptography` library's native SSHCertificateBuilder (v46+).
"""

import json
import uuid
from utils.datetime_utils import utc_now

try:
    from models import db
except ImportError:
    db = None


class SSHCertificateAuthority(db.Model if db else object):
    """SSH Certificate Authority — manages OpenSSH CA key pairs"""

    __tablename__ = 'ssh_cas'

    id = db.Column(db.Integer, primary_key=True)
    refid = db.Column(db.String(36), unique=True, nullable=False, index=True,
                      default=lambda: str(uuid.uuid4()))
    descr = db.Column(db.String(255), nullable=False)

    # CA type: 'user' or 'host'
    ca_type = db.Column(db.String(10), nullable=False, index=True)

    # Key material — public key in OpenSSH format, private key base64-encoded (optionally encrypted)
    public_key = db.Column(db.Text, nullable=False)
    private_key = db.Column(db.Text, nullable=False)

    # Key metadata
    key_type = db.Column(db.String(20), nullable=False)  # ed25519, rsa, ecdsa-p256, ecdsa-p384, ecdsa-p521
    fingerprint = db.Column(db.String(100), nullable=False, index=True)  # SHA256:base64

    # Serial counter — atomically incremented for each issued cert
    serial_counter = db.Column(db.Integer, default=0, nullable=False)

    # Default validity (seconds) — overridable per cert
    default_ttl = db.Column(db.Integer, default=86400)  # 24h for user, 31536000 for host

    # Max allowed validity (seconds) — 0 means unlimited
    max_ttl = db.Column(db.Integer, default=0)

    # Default extensions for user certs (JSON list of extension names)
    default_extensions = db.Column(db.Text)

    # Allowed principals pattern (JSON list of allowed principal patterns, empty = any)
    allowed_principals = db.Column(db.Text)

    # Comment / notes
    comment = db.Column(db.Text)

    # Audit
    created_at = db.Column(db.DateTime, default=utc_now)
    created_by = db.Column(db.String(80))

    # Ownership
    owner_group_id = db.Column(db.Integer, db.ForeignKey('groups.id'), nullable=True)
    owner_group = db.relationship('Group', backref='owned_ssh_cas')

    # Relationships
    certificates = db.relationship('SSHCertificate', backref='ca', lazy='dynamic',
                                   cascade='all, delete-orphan')

    VALID_CA_TYPES = ['user', 'host']
    VALID_KEY_TYPES = ['ed25519', 'rsa', 'ecdsa-p256', 'ecdsa-p384', 'ecdsa-p521']

    # Standard OpenSSH user cert extensions
    STANDARD_EXTENSIONS = [
        'permit-pty',
        'permit-user-rc',
        'permit-agent-forwarding',
        'permit-port-forwarding',
        'permit-X11-forwarding',
    ]

    def get_default_extensions(self):
        """Get default extensions list"""
        if not self.default_extensions:
            return list(self.STANDARD_EXTENSIONS)
        try:
            return json.loads(self.default_extensions)
        except (json.JSONDecodeError, TypeError):
            return list(self.STANDARD_EXTENSIONS)

    def set_default_extensions(self, extensions):
        """Set default extensions from list"""
        self.default_extensions = json.dumps(extensions) if extensions else None

    def get_allowed_principals(self):
        """Get allowed principals list"""
        if not self.allowed_principals:
            return []
        try:
            return json.loads(self.allowed_principals)
        except (json.JSONDecodeError, TypeError):
            return []

    def set_allowed_principals(self, principals):
        """Set allowed principals from list"""
        self.allowed_principals = json.dumps(principals) if principals else None

    def to_dict(self):
        """Convert to dict for API response"""
        cert_count = self.certificates.count() if self.certificates else 0
        revoked_count = self.certificates.filter_by(revoked=True).count() if self.certificates else 0

        return {
            'id': self.id,
            'refid': self.refid,
            'descr': self.descr,
            'name': self.descr,
            'ca_type': self.ca_type,
            'public_key': self.public_key,
            'key_type': self.key_type,
            'fingerprint': self.fingerprint,
            'serial_counter': self.serial_counter,
            'default_ttl': self.default_ttl,
            'max_ttl': self.max_ttl,
            'default_extensions': self.get_default_extensions(),
            'allowed_principals': self.get_allowed_principals(),
            'comment': self.comment,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'created_by': self.created_by,
            'owner_group_id': self.owner_group_id,
            'owner_group_name': self.owner_group.name if self.owner_group else None,
            'cert_count': cert_count,
            'revoked_count': revoked_count,
        }

    def __repr__(self):
        return f'<SSHCertificateAuthority {self.descr} ({self.ca_type})>'


class SSHCertificate(db.Model if db else object):
    """SSH Certificate — issued by an SSH CA"""

    __tablename__ = 'ssh_certificates'

    id = db.Column(db.Integer, primary_key=True)
    refid = db.Column(db.String(36), unique=True, nullable=False, index=True,
                      default=lambda: str(uuid.uuid4()))
    descr = db.Column(db.String(255))

    # FK to SSH CA
    ssh_ca_id = db.Column(db.Integer, db.ForeignKey('ssh_cas.id'), nullable=False, index=True)

    # Certificate type: 'user' (1) or 'host' (2)
    cert_type = db.Column(db.String(10), nullable=False, index=True)

    # OpenSSH certificate key_id field
    key_id = db.Column(db.String(255), nullable=False)

    # The subject's public key (OpenSSH format)
    public_key = db.Column(db.Text, nullable=False)

    # The signed certificate (OpenSSH format: "ssh-...-cert-v01@openssh.com AAAA...")
    certificate = db.Column(db.Text, nullable=False)

    # Principals (JSON array of strings)
    principals = db.Column(db.Text, nullable=False)

    # Serial number assigned by the CA
    serial = db.Column(db.Integer, nullable=False, index=True)

    # Validity window (stored as UTC datetime for easy querying)
    valid_from = db.Column(db.DateTime, nullable=False)
    valid_to = db.Column(db.DateTime, nullable=False, index=True)

    # Key metadata
    key_type = db.Column(db.String(20), nullable=False)  # ed25519, rsa, ecdsa-p256, etc.
    fingerprint = db.Column(db.String(100), nullable=False, index=True)  # Subject key fingerprint

    # Extensions and critical options (JSON dicts)
    extensions = db.Column(db.Text)
    critical_options = db.Column(db.Text)

    # Revocation
    revoked = db.Column(db.Boolean, default=False, index=True)
    revoked_at = db.Column(db.DateTime)
    revoke_reason = db.Column(db.String(255))

    # Source: 'web', 'api', 'auto'
    source = db.Column(db.String(20), default='web')

    # Audit
    created_at = db.Column(db.DateTime, default=utc_now)
    created_by = db.Column(db.String(80))

    # Ownership
    owner_group_id = db.Column(db.Integer, db.ForeignKey('groups.id'), nullable=True)
    owner_group = db.relationship('Group', backref='owned_ssh_certificates')

    VALID_CERT_TYPES = ['user', 'host']

    def get_principals(self):
        """Get principals as list"""
        if not self.principals:
            return []
        try:
            return json.loads(self.principals)
        except (json.JSONDecodeError, TypeError):
            return []

    def set_principals(self, principals):
        """Set principals from list"""
        self.principals = json.dumps(principals)

    def get_extensions(self):
        """Get extensions as dict"""
        if not self.extensions:
            return {}
        try:
            return json.loads(self.extensions)
        except (json.JSONDecodeError, TypeError):
            return {}

    def set_extensions(self, extensions):
        """Set extensions from dict"""
        self.extensions = json.dumps(extensions) if extensions else None

    def get_critical_options(self):
        """Get critical options as dict"""
        if not self.critical_options:
            return {}
        try:
            return json.loads(self.critical_options)
        except (json.JSONDecodeError, TypeError):
            return {}

    def set_critical_options(self, options):
        """Set critical options from dict"""
        self.critical_options = json.dumps(options) if options else None

    @property
    def is_expired(self):
        """Check if certificate has expired"""
        if not self.valid_to:
            return False
        return self.valid_to < utc_now()

    @property
    def status(self):
        """Compute certificate status"""
        if self.revoked:
            return 'revoked'
        if self.is_expired:
            return 'expired'
        return 'valid'

    def to_dict(self):
        """Convert to dict for API response"""
        return {
            'id': self.id,
            'refid': self.refid,
            'descr': self.descr,
            'ssh_ca_id': self.ssh_ca_id,
            'ca_name': self.ca.descr if self.ca else None,
            'cert_type': self.cert_type,
            'key_id': self.key_id,
            'public_key': self.public_key,
            'certificate': self.certificate,
            'principals': self.get_principals(),
            'serial': self.serial,
            'valid_from': self.valid_from.isoformat() if self.valid_from else None,
            'valid_to': self.valid_to.isoformat() if self.valid_to else None,
            'key_type': self.key_type,
            'fingerprint': self.fingerprint,
            'extensions': self.get_extensions(),
            'critical_options': self.get_critical_options(),
            'revoked': self.revoked,
            'revoked_at': self.revoked_at.isoformat() if self.revoked_at else None,
            'revoke_reason': self.revoke_reason,
            'source': self.source,
            'status': self.status,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'created_by': self.created_by,
            'owner_group_id': self.owner_group_id,
            'owner_group_name': self.owner_group.name if self.owner_group else None,
        }

    def __repr__(self):
        return f'<SSHCertificate {self.key_id} ({self.cert_type})>'
