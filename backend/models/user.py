"""
User and UserSession Models
"""
from werkzeug.security import generate_password_hash, check_password_hash
from models import db
from utils.datetime_utils import utc_now, utc_isoformat


class UserSession(db.Model):
    """Track active user sessions for session management"""
    __tablename__ = "user_sessions"
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    session_id = db.Column(db.String(255), unique=True, nullable=False, index=True)
    ip_address = db.Column(db.String(45))  # IPv6-compatible
    user_agent = db.Column(db.String(500))
    auth_method = db.Column(db.String(50), default='password')  # password, webauthn, mtls
    created_at = db.Column(db.DateTime, default=utc_now)
    last_activity = db.Column(db.DateTime, default=utc_now)
    expires_at = db.Column(db.DateTime)
    
    def to_dict(self):
        return {
            'id': self.id,
            'ip_address': self.ip_address,
            'user_agent': self.user_agent,
            'auth_method': self.auth_method,
            'created_at': utc_isoformat(self.created_at),
            'last_activity': utc_isoformat(self.last_activity),
            'expires_at': utc_isoformat(self.expires_at)
        }


class User(db.Model):
    """User model for authentication"""
    __tablename__ = "users"
    
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False, index=True)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    full_name = db.Column(db.String(255))  # Full name for WebAuthn/certificates
    role = db.Column(db.String(20), nullable=False, default="viewer")  # admin, operator, viewer
    custom_role_id = db.Column(db.Integer, db.ForeignKey('pro_custom_roles.id', ondelete='SET NULL'), nullable=True)
    active = db.Column(db.Boolean, default=True)
    mfa_enabled = db.Column(db.Boolean, default=False)  # MFA enabled for this user
    
    # 2FA/TOTP fields
    totp_secret = db.Column(db.String(32))  # Base32-encoded TOTP secret
    totp_confirmed = db.Column(db.Boolean, default=False)  # TOTP setup confirmed
    backup_codes = db.Column(db.Text)  # JSON array of backup codes (hashed)
    
    # Password management
    force_password_change = db.Column(db.Boolean, default=False)  # Must change on next login
    password_reset_token = db.Column(db.String(128), nullable=True)  # For forgot password
    password_reset_expires = db.Column(db.DateTime, nullable=True)  # Token expiry
    
    # Login tracking
    created_at = db.Column(db.DateTime, default=utc_now)
    last_login = db.Column(db.DateTime)
    login_count = db.Column(db.Integer, default=0)  # Total successful logins
    failed_logins = db.Column(db.Integer, default=0)  # Failed login attempts
    locked_until = db.Column(db.DateTime, nullable=True)  # Account lockout timestamp

    # User preferences (JSON-encoded; language, theme, density, etc.)
    # Persisted server-side so they follow the user across browsers/devices.
    preferences = db.Column(db.Text, nullable=True)

    # Authentication source — distinguishes locally-managed users from those
    # provisioned by an SSO provider. Values: 'local', 'ldap', 'oauth2', 'saml'.
    # `sso_provider_id` links to the originating provider when applicable.
    auth_source = db.Column(db.String(20), nullable=False, default='local')
    sso_provider_id = db.Column(
        db.Integer,
        db.ForeignKey('pro_sso_providers.id', ondelete='SET NULL'),
        nullable=True,
    )

    # Relationships
    custom_role = db.relationship('CustomRole', foreign_keys=[custom_role_id], lazy='select')
    sso_provider = db.relationship('SSOProvider', foreign_keys=[sso_provider_id], lazy='select')
    
    @property
    def groups(self):
        """Get groups this user belongs to via GroupMember"""
        from models.group import GroupMember, Group
        memberships = GroupMember.query.filter_by(user_id=self.id).all()
        return [Group.query.get(m.group_id) for m in memberships if Group.query.get(m.group_id)]
    
    def set_password(self, password: str):
        """Hash and set password"""
        self.password_hash = generate_password_hash(password)
    
    def check_password(self, password: str) -> bool:
        """Verify password"""
        return check_password_hash(self.password_hash, password)

    def get_preferences(self) -> dict:
        """Return the user's preferences as a dict (empty if unset/invalid)."""
        import json
        if not self.preferences:
            return {}
        try:
            data = json.loads(self.preferences)
            return data if isinstance(data, dict) else {}
        except (ValueError, TypeError):
            return {}

    def set_preferences(self, value: dict) -> None:
        """Persist preferences dict as JSON."""
        import json
        self.preferences = json.dumps(value or {}, separators=(',', ':'))
    
    def to_dict(self):
        """Convert to dictionary"""
        result = {
            "id": self.id,
            "username": self.username,
            "email": self.email,
            "full_name": self.full_name,
            "role": self.role,
            "custom_role_id": self.custom_role_id,
            "active": self.active,
            "mfa_enabled": self.mfa_enabled,
            "totp_enabled": self.totp_confirmed,
            "two_factor_enabled": self.totp_confirmed,
            "force_password_change": self.force_password_change or False,
            "created_at": utc_isoformat(self.created_at),
            "last_login": utc_isoformat(self.last_login),
            "login_count": self.login_count or 0,
            "failed_logins": self.failed_logins or 0,
            "auth_source": self.auth_source or 'local',
            "sso_provider_id": self.sso_provider_id,
        }
        try:
            if self.custom_role_id and self.custom_role:
                result["custom_role_name"] = self.custom_role.name
        except Exception:
            pass
        try:
            if self.sso_provider_id and self.sso_provider:
                result["sso_provider_name"] = self.sso_provider.name
                result["sso_provider_type"] = self.sso_provider.provider_type
        except Exception:
            pass
        return result
