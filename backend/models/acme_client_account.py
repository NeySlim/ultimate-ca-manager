"""ACME Client Account model (RFC 8555).

Replaces the legacy `acme.client.{staging,production}.account_*` SystemConfig
keys. Each row binds an ACME directory URL to its registration credentials,
making it impossible for label/URL to drift apart.
"""
from datetime import datetime
from models import db


class AcmeClientAccount(db.Model):
    __tablename__ = 'acme_client_accounts'

    # Defaults for per-CA timing (slow authorities need longer polls).
    DEFAULT_ORDER_POLL_TIMEOUT_SEC = 180
    DEFAULT_ORDER_POLL_INTERVAL_SEC = 3
    DEFAULT_HTTP_TIMEOUT_SEC = 60

    id = db.Column(db.Integer, primary_key=True)
    directory_url = db.Column(db.String(500), unique=True, nullable=False, index=True)
    label = db.Column(db.String(100), nullable=False)  # "Let's Encrypt Production", etc.
    email = db.Column(db.String(255), nullable=False)
    account_url = db.Column(db.String(500), nullable=True)  # populated after registration
    account_key = db.Column(db.Text, nullable=True)  # PEM, encrypted at rest (ENC:...)
    account_key_algorithm = db.Column(db.String(20), nullable=False, default='ES256')  # RS256/ES256/ES384
    eab_kid = db.Column(db.String(255), nullable=True)
    eab_hmac_key = db.Column(db.Text, nullable=True)  # encrypted at rest
    is_default = db.Column(db.Boolean, default=False, nullable=False)
    order_poll_timeout_sec = db.Column(
        db.Integer, nullable=False, default=DEFAULT_ORDER_POLL_TIMEOUT_SEC,
    )
    order_poll_interval_sec = db.Column(
        db.Integer, nullable=False, default=DEFAULT_ORDER_POLL_INTERVAL_SEC,
    )
    http_timeout_sec = db.Column(
        db.Integer, nullable=False, default=DEFAULT_HTTP_TIMEOUT_SEC,
    )
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    LE_STAGING_URL = "https://acme-staging-v02.api.letsencrypt.org/directory"
    LE_PRODUCTION_URL = "https://acme-v02.api.letsencrypt.org/directory"

    def is_registered(self) -> bool:
        return bool(self.account_url and self.account_key)

    def derived_environment(self) -> str:
        """Derive 'staging'/'production'/'custom' from directory_url for UI compat."""
        if self.directory_url == self.LE_STAGING_URL:
            return 'staging'
        if self.directory_url == self.LE_PRODUCTION_URL:
            return 'production'
        return 'custom'

    def get_order_poll_timeout_sec(self) -> int:
        val = self.order_poll_timeout_sec
        return val if val is not None else self.DEFAULT_ORDER_POLL_TIMEOUT_SEC

    def get_order_poll_interval_sec(self) -> int:
        val = self.order_poll_interval_sec
        return val if val is not None else self.DEFAULT_ORDER_POLL_INTERVAL_SEC

    def get_http_timeout_sec(self) -> int:
        val = self.http_timeout_sec
        return val if val is not None else self.DEFAULT_HTTP_TIMEOUT_SEC

    def to_dict(self, include_secrets: bool = False) -> dict:
        d = {
            'id': self.id,
            'directory_url': self.directory_url,
            'label': self.label,
            'email': self.email,
            'account_url': self.account_url,
            'account_key_algorithm': self.account_key_algorithm,
            'eab_kid': self.eab_kid,
            'is_default': self.is_default,
            'is_registered': self.is_registered(),
            'environment': self.derived_environment(),
            'order_poll_timeout_sec': self.get_order_poll_timeout_sec(),
            'order_poll_interval_sec': self.get_order_poll_interval_sec(),
            'http_timeout_sec': self.get_http_timeout_sec(),
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
            'eab_hmac_key_set': bool(self.eab_hmac_key),
            'account_key_set': bool(self.account_key),
        }
        if include_secrets:
            d['account_key'] = self.account_key
            d['eab_hmac_key'] = self.eab_hmac_key
        return d