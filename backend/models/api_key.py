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
    
    # Relationship to User
    user = db.relationship('User', backref='api_keys')
    
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
            'is_active': self.is_active
        }
    
    def __repr__(self):
        return f'<APIKey {self.name} (user_id={self.user_id})>'
