"""DNS UPDATE (RFC 2136) listener models.

``AcmeDnsUpdateKey`` holds TSIG keys (RFC 8945) bound to an ACME proxy
account. ``AcmeProxyDnsChallenge`` holds the TXT values that a client may
publish through the listener.
"""
import base64
import re

from models import db
from utils.datetime_utils import utc_now, utc_isoformat


# Key name labels: letters, digits, "_" and "-" (not first or last). DNS allows any
# octet, but the name goes into shell, PowerShell and YAML snippets of the clients.
_KEY_LABEL = re.compile(r'^[a-z0-9_](?:[a-z0-9_-]*[a-z0-9_])?$')


class AcmeDnsUpdateKey(db.Model):
    """TSIG key for the DNS UPDATE listener."""
    __tablename__ = 'acme_dns_update_keys'

    ALGORITHMS = ('hmac-sha256', 'hmac-sha384', 'hmac-sha512')
    STATUSES = ('active', 'revoked')

    id = db.Column(db.Integer, primary_key=True)
    acme_client_account_id = db.Column(
        db.Integer,
        db.ForeignKey('acme_client_accounts.id', ondelete='CASCADE'),
        nullable=False, index=True,
    )
    eab_credential_id = db.Column(
        db.Integer,
        db.ForeignKey('acme_eab_credentials.id', ondelete='CASCADE'),
        nullable=True, index=True,
    )
    # Stays True when the credential reference is lost (restore, orphan):
    # the key then matches nothing instead of the whole proxy account.
    eab_bound = db.Column(db.Boolean, nullable=False, default=False)
    # Absolute DNS name, lowercase, trailing dot (RFC 8945 §4.2).
    name = db.Column(db.String(255), unique=True, nullable=False)
    algorithm = db.Column(db.String(32), default='hmac-sha256', nullable=False)
    # Standard base64 text (BIND key file format), encrypted at rest.
    _secret = db.Column('secret', db.Text, nullable=False)
    status = db.Column(db.String(16), default='active', nullable=False, index=True)
    created_at = db.Column(db.DateTime, default=utc_now)
    created_by_user_id = db.Column(db.Integer, nullable=True)
    last_used_at = db.Column(db.DateTime, nullable=True)
    revoked_at = db.Column(db.DateTime, nullable=True)
    notes = db.Column(db.Text, nullable=True)

    @property
    def secret(self):
        """Decrypted base64 secret, or None.

        Fail-closed: an empty value or a value that cannot be decrypted is
        None. The stored ciphertext and the raw value are never returned.
        """
        if not self._secret:
            return None
        try:
            from utils.encryption import is_encrypted, decrypt_value
            if not is_encrypted(self._secret):
                return None
            return decrypt_value(self._secret) or None
        except Exception:
            return None

    @secret.setter
    def secret(self, value):
        if not value:
            raise ValueError('TSIG secret must not be empty')
        from utils.encryption import encrypt_if_needed
        self._secret = encrypt_if_needed(value)

    @staticmethod
    def secret_from_bytes(raw: bytes) -> str:
        """Standard base64 text of a raw key, as stored and as in BIND files."""
        return base64.b64encode(raw).decode('ascii')

    @staticmethod
    def normalize_name(name: str) -> str:
        """Absolute, lowercase DNS name with a trailing dot, or ValueError."""
        import dns.name
        import dns.exception
        if not isinstance(name, str) or not name.strip():
            raise ValueError('Key name is required')
        text = name.strip().lower()
        if not text.endswith('.'):
            text += '.'
        if text == '.':
            raise ValueError('Key name must not be the root name')
        if text.startswith('.') or '..' in text:
            raise ValueError('Key name must not contain empty labels')
        try:
            parsed = dns.name.from_text(text)
            wire = parsed.to_wire()
        except (dns.exception.DNSException, UnicodeError) as e:
            raise ValueError(f'Invalid key name: {e}')
        if len(wire) > 255:
            raise ValueError('Key name is longer than 255 bytes')
        if any(len(label) > 63 for label in parsed.labels):
            raise ValueError('Key name has a label longer than 63 bytes')
        if len(parsed.labels) < 2:
            raise ValueError('Key name must not be the root name')
        for label in parsed.labels[:-1]:
            if not _KEY_LABEL.match(label.decode('ascii', 'replace')):
                raise ValueError('Key name labels may contain only letters, digits, '
                                 '"_" and "-" (not as the first or last character)')
        return parsed.to_text().lower()

    def to_dict(self):
        """Metadata only. The secret is never part of it."""
        return {
            'id': self.id,
            'acme_client_account_id': self.acme_client_account_id,
            'eab_credential_id': self.eab_credential_id,
            'eab_bound': bool(self.eab_bound),
            'name': self.name,
            'algorithm': self.algorithm,
            'status': self.status,
            'created_at': utc_isoformat(self.created_at) if self.created_at else None,
            'created_by_user_id': self.created_by_user_id,
            'last_used_at': utc_isoformat(self.last_used_at) if self.last_used_at else None,
            'revoked_at': utc_isoformat(self.revoked_at) if self.revoked_at else None,
            'notes': self.notes,
        }

    def __repr__(self):
        return f'<AcmeDnsUpdateKey {self.name} status={self.status}>'


class AcmeProxyDnsChallenge(db.Model):
    """Expected TXT value for a proxy order (what the listener may accept)."""
    __tablename__ = 'acme_proxy_dns_challenges'
    __table_args__ = (
        db.UniqueConstraint('order_id', 'record_name', 'txt_value',
                            name='uq_acme_proxy_dns_challenge'),
        db.Index('idx_acme_proxy_dns_status_expires', 'status', 'expires_at'),
        db.Index('idx_acme_proxy_dns_expires', 'expires_at'),
    )

    id = db.Column(db.Integer, primary_key=True)
    order_id = db.Column(
        db.Integer,
        db.ForeignKey('acme_client_orders.id', ondelete='CASCADE'),
        nullable=False, index=True,
    )
    # Proxy account of the order (acme_client_accounts.id).
    acme_client_account_id = db.Column(db.Integer, nullable=True, index=True)
    # Local AcmeAccount.account_id of the client.
    account_id = db.Column(db.String(64), nullable=True)
    client_jwk_thumbprint = db.Column(db.String(128), nullable=False)
    identifier = db.Column(db.String(255), nullable=False)
    record_name = db.Column(db.String(255), nullable=False, index=True)
    txt_value = db.Column(db.String(64), nullable=False)
    # Apex D of the ACME Domains entry covering the identifier: absolute,
    # lowercase, trailing dot. Set when the row is written, so the listener
    # answers SOA without querying ACME Domains.
    zone_name = db.Column(db.String(255), nullable=False, index=True)
    upstream_challenge_url = db.Column(db.Text, nullable=True)
    status = db.Column(db.String(16), default='pending', nullable=False)
    created_at = db.Column(db.DateTime, default=utc_now)
    expires_at = db.Column(db.DateTime, nullable=False)
    # Time of the last accepted DNS UPDATE for this row. Diagnostics only: no
    # code reads it, the listener never decides on it.
    client_confirmed_at = db.Column(db.DateTime, nullable=True)

    def __repr__(self):
        return f'<AcmeProxyDnsChallenge {self.record_name} order={self.order_id}>'
