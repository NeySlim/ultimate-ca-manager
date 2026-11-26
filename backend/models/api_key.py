"""
API Key Model
Simple and secure API key storage
"""

from datetime import datetime
import json
from utils.datetime_utils import utc_now, utc_isoformat

try:
    from models import db
except ImportError:
    # For testing
    db = None


class APIKey(db.Model if db else object):
    """API Key for automation and external access"""
    
    __tablename__ = 'api_keys'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    
    # Hashed key (SHA256) - NEVER store plaintext!
    key_hash = db.Column(db.String(255), nullable=False, unique=True, index=True)

    # First ~12 chars of the plaintext key (e.g. 'ucm_ak_AbC1') so the
    # list view can identify a key without revealing it. Nullable for keys
    # created before migration 026.
    key_prefix = db.Column(db.String(20), nullable=True)

    # Friendly name
    name = db.Column(db.String(100), nullable=False)
    
    # Permissions as JSON string
    # Example: ["read:cas", "write:certificates", "read:*"]
    permissions = db.Column(db.Text, nullable=False)
    
    # Timestamps
    created_at = db.Column(db.DateTime, default=utc_now)
    expires_at = db.Column(db.DateTime, nullable=True)
    last_used_at = db.Column(db.DateTime, nullable=True)
    
    # Active flag
    is_active = db.Column(db.Boolean, default=True)

    # JSON list of canonical networks the key is used from (upgrade step 177); NULL admits any
    allowed_networks = db.Column(db.Text, nullable=True)
    
    # Relationship to User
    user = db.relationship('User', backref='api_keys')

    @property
    def is_expired(self):
        """Expiry is derived live from expires_at, never persisted - same
        approach as certificate expiry (see Certificate.valid_to)."""
        return bool(self.expires_at and self.expires_at < utc_now())

    @property
    def networks(self) -> list:
        """The source networks; an unreadable list admits nobody rather than everybody."""
        if not self.allowed_networks:
            return []
        try:
            value = json.loads(self.allowed_networks)
        except (TypeError, ValueError):
            return ['invalid']
        return value if isinstance(value, list) else ['invalid']

    def to_dict(self):
        """
        Convert to dict for API response
        NEVER expose key_hash!
        """
        return {
            'id': self.id,
            'name': self.name,
            'key_prefix': self.key_prefix,
            'permissions': json.loads(self.permissions),
            'created_at': utc_isoformat(self.created_at),
            'expires_at': utc_isoformat(self.expires_at),
            'last_used_at': utc_isoformat(self.last_used_at),
            'is_active': self.is_active,
            'is_expired': self.is_expired,
            'allowed_networks': self.networks,
        }
    
    def __repr__(self):
        return f'<APIKey {self.name} (user_id={self.user_id})>'
