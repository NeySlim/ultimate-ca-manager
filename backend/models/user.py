"""
User and UserSession Models
"""
from sqlalchemy import func, select, update
from sqlalchemy.orm.attributes import set_committed_value

from utils.password_hash import hash_password, needs_rehash, verify_password
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
    __table_args__ = (
        # A deleted account's id is never handed out again (migration 150 on upgrades)
        {'sqlite_autoincrement': True},
    )

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False, index=True)
    # Not globally UNIQUE — see __table_args__ (unique per local account only).
    email = db.Column(db.String(120), nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    full_name = db.Column(db.String(255))  # Full name for WebAuthn/certificates
    role = db.Column(db.String(20), nullable=False, default="viewer")  # see auth.permissions.BUILTIN_ROLES
    custom_role_id = db.Column(db.Integer, db.ForeignKey('pro_custom_roles.id', ondelete='SET NULL'), nullable=True)
    custom_role_source = db.Column(db.String(16), nullable=True)  # 'sso' = from the SSO role mapping; NULL = by hand
    active = db.Column(db.Boolean, default=True)
    # Never set by anything: the 2FA state is totp_confirmed. Kept for older databases.
    mfa_enabled = db.Column(db.Boolean, default=False)
    
    # 2FA/TOTP fields
    totp_secret = db.Column(db.String(32))  # Base32-encoded TOTP secret
    totp_confirmed = db.Column(db.Boolean, default=False)  # TOTP setup confirmed
    backup_codes = db.Column(db.Text)  # JSON array of backup codes (hashed)
    # Last TOTP time step accepted: a code is good once (RFC 6238 §5.2).
    totp_last_step = db.Column(db.BigInteger, nullable=True)
    # Per-user opt-out from forced 2FA enrolment (#141). Set on the initial
    # admin so global enforcement can never lock out the bootstrap account.
    totp_exempt = db.Column(db.Boolean, default=False)
    # A security key turned on as this account's second factor (password logins).
    webauthn_2fa = db.Column(db.Boolean, nullable=False, default=False, server_default=db.false())
    
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
    # Copied into each session at login; bumped to close every session of the account.
    session_version = db.Column(db.Integer, nullable=False, default=0, server_default='0')

    # User preferences (JSON-encoded; language, theme, density, etc.)
    # Persisted server-side so they follow the user across browsers/devices.
    preferences = db.Column(db.Text, nullable=True)

    # Relationships
    custom_role = db.relationship('CustomRole', foreign_keys=[custom_role_id], lazy='select')
    # The providers that open this account, one row each (UserSSOIdentity)
    sso_identities = db.relationship('UserSSOIdentity', back_populates='user', lazy='selectin',
                                     cascade='all, delete-orphan', passive_deletes=True,
                                     order_by='UserSSOIdentity.id')

    @property
    def is_local(self):
        """No provider opens this account, nor did a deleted one: its e-mail is unique
        among local accounts (#136)."""
        return not self.sso_identities

    @property
    def auth_source(self):
        """'local', or 'sso' for an account with at least one identity row."""
        return 'local' if self.is_local else 'sso'
    
    @property
    def groups(self):
        """Get groups this user belongs to via GroupMember"""
        from models.group import GroupMember, Group
        memberships = GroupMember.query.filter_by(user_id=self.id).all()
        return [db.session.get(Group, m.group_id) for m in memberships if db.session.get(Group, m.group_id)]
    
    def set_password(self, password: str):
        """Hash and set password, with the method pinned in utils.password_hash.

        Every session opened with the old password ends with it, and so does a
        generated initial password file (auth.initial_admin)."""
        self.password_hash = hash_password(password)
        self.end_sessions()
        if self.id is not None:
            from auth.initial_admin import forget_generated
            forget_generated(self)

    def end_sessions(self):
        """Invalidate every session of this account; the caller commits.

        Incremented in SQL so that concurrent bumps add up; ``_sessions_bump`` keeps
        (replaced, new) for keep_current_session()."""
        if self.id is None:
            return  # not saved yet: no session to end
        db.session.execute(
            update(User).where(User.id == self.id)
            .values(session_version=func.coalesce(User.session_version, 0) + 1)
            .execution_options(synchronize_session=False))
        new = db.session.execute(select(User.session_version).where(User.id == self.id)).scalar_one()
        set_committed_value(self, 'session_version', new)
        self._sessions_bump = (new - 1, new)

    def reserve_login_attempt(self, max_attempts: int, lockout_seconds: int):
        """Count one login attempt before its secret is checked: ``(rank, armed)``, rank
        None when the attempt is refused unchecked, armed the stored ``locked_until`` for
        the one attempt whose count armed the lock, else None. The caller commits before
        checking the secret.

        One UPDATE decides on every node: at most ``max_attempts`` attempts get a rank,
        the one reaching it (or, past a lowered threshold, the next one) arms the lock,
        and an expired lock restarts the count at 1."""
        from datetime import timedelta
        from sqlalchemy import and_, case, or_
        now = utc_now()
        expired = and_(User.locked_until.is_not(None), User.locked_until <= now)
        count = case((expired, 1), else_=func.coalesce(User.failed_logins, 0) + 1)
        stmt = (update(User)
                .where(User.id == self.id,
                       or_(User.locked_until.is_(None), User.locked_until <= now))
                .values(failed_logins=count,
                        locked_until=case((count >= max_attempts,
                                           now + timedelta(seconds=lockout_seconds)), else_=None))
                .execution_options(synchronize_session=False))
        columns = (User.failed_logins, User.locked_until)
        if db.session.get_bind().dialect.update_returning:
            row = db.session.execute(stmt.returning(*columns)).one_or_none()
        else:
            # No RETURNING: the UPDATE holds the write lock until the commit, so the read
            # sees this attempt's count. No row changed = account locked.
            row = None
            if db.session.execute(stmt.execution_options(preserve_rowcount=True)).rowcount:
                row = db.session.execute(select(*columns).where(User.id == self.id)).one()
        if row is None:
            return None, None
        set_committed_value(self, 'failed_logins', row[0])
        set_committed_value(self, 'locked_until', row[1])
        # Only an unlocked row is updated, so an attempt whose count reaches max armed it.
        return (row[0] if row[0] <= max_attempts else None), \
            (row[1] if row[0] >= max_attempts else None)

    def release_login_attempt(self, armed):
        """Give back a reserved attempt whose secret was proved but opened no session.

        Only the attempt that armed the lock can show its window is still open: the stored
        lock is the one it wrote (``armed``) and still runs. It then lifts that lock and
        gives its unit back. Any other stays counted, so no window gets back a unit taken in
        another and each window checks at most ``max_attempts`` wrong secrets. The caller commits."""
        if armed:
            db.session.execute(
                update(User).where(User.id == self.id, User.locked_until == armed,
                                   User.locked_until > utc_now())
                .values(failed_logins=func.coalesce(User.failed_logins, 0) - 1,
                        locked_until=None)
                .execution_options(synchronize_session=False))
        self._reload_lockout()

    def clear_failed_logins(self) -> bool:
        """Reset the stored count and lock, whatever this copy holds: True when the row
        held either. The caller commits."""
        from sqlalchemy import or_
        result = db.session.execute(
            update(User).where(User.id == self.id,
                               or_(func.coalesce(User.failed_logins, 0) != 0,
                                   User.locked_until.is_not(None)))
            .values(failed_logins=0, locked_until=None)
            .execution_options(synchronize_session=False, preserve_rowcount=True))
        set_committed_value(self, 'failed_logins', 0)
        set_committed_value(self, 'locked_until', None)
        return bool(result.rowcount)

    def _reload_lockout(self):
        row = db.session.execute(
            select(User.failed_logins, User.locked_until).where(User.id == self.id)).one()
        set_committed_value(self, 'failed_logins', row[0])
        set_committed_value(self, 'locked_until', row[1])

    def check_password(self, password: str) -> bool:
        """Verify password; a hash of an older method is replaced on success
        and saved by the caller's next commit."""
        if not verify_password(self.password_hash, password):
            return False
        if needs_rehash(self.password_hash):
            self.password_hash = hash_password(password)
        return True

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
    
    def second_factor_required(self):
        """Whether a password login asks this user for TOTP or a security key."""
        from auth.twofa_enforcement import second_factor_methods  # circular at import
        return bool(self.totp_confirmed) or bool(second_factor_methods(self))

    def to_dict(self):
        """Convert to dictionary"""
        result = {
            "id": self.id,
            "username": self.username,
            "email": self.email,
            "full_name": self.full_name,
            "role": self.role,
            "custom_role_id": self.custom_role_id,
            "custom_role_source": self.custom_role_source,
            "active": self.active,
            "totp_enabled": self.totp_confirmed,
            "two_factor_enabled": self.second_factor_required(),
            "totp_exempt": bool(self.totp_exempt),
            "webauthn_2fa": bool(self.webauthn_2fa),
            "force_password_change": self.force_password_change or False,
            "created_at": utc_isoformat(self.created_at),
            "last_login": utc_isoformat(self.last_login),
            "login_count": self.login_count or 0,
            "failed_logins": self.failed_logins or 0,
            "auth_source": self.auth_source,
            "sso_identities": [row.to_dict() for row in self.sso_identities],
        }
        try:
            if self.custom_role_id and self.custom_role:
                result["custom_role_name"] = self.custom_role.name
        except Exception:
            pass
        return result


def local_email_holder(email, other_than=None):
    """A local account (no identity row) holding ``email``: e-mail is unique among local
    accounts only (#136), which every path making an account local checks here."""
    query = User.query.filter(User.email == email, ~User.sso_identities.any())
    if other_than is not None:
        query = query.filter(User.id != other_than)
    return query.order_by(User.id).first()


class UserSSOIdentity(db.Model):
    """One provider that opens an account, and the stable identity it does so with.

    ``external_id`` NULL: attached, not bound yet (the first sign-in binds it). ``provider_id``
    NULL: its provider was deleted; ``orphan_of`` keeps that provider's IdP key, and only a
    provider for that exact key takes it back (OIDC Core §5.7: iss and sub together identify).
    """
    __tablename__ = 'user_sso_identities'
    __table_args__ = (
        # One account per stable identity of a provider; one attachment per provider per account
        db.UniqueConstraint('provider_id', 'external_id', name='uq_user_sso_identities_provider_identity'),
        db.UniqueConstraint('user_id', 'provider_id', name='uq_user_sso_identities_user_provider'),
        db.Index('ix_user_sso_identities_orphan', 'orphan_of', 'external_id'),
    )

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='CASCADE'),
                        nullable=False, index=True)
    provider_id = db.Column(db.Integer, db.ForeignKey('pro_sso_providers.id', ondelete='SET NULL'),
                            nullable=True)
    orphan_of = db.Column(db.String(600), nullable=True)
    # OIDC `sub`, SAML persistent NameID, LDAP entryUUID/objectGUID (or the DN fallback)
    external_id = db.Column(db.String(255), nullable=True)
    created_at = db.Column(db.DateTime, default=utc_now)
    bound_at = db.Column(db.DateTime, nullable=True)
    # The administrator who attached the provider; NULL when a sign-in or an upgrade made the row
    created_by = db.Column(db.String(80), nullable=True)

    user = db.relationship('User', back_populates='sso_identities')
    # A provider deleted through the session leaves its rows orphans of an unknown IdP (SQLite
    # applies no ON DELETE SET NULL); the provider routes record the IdP key first.
    provider = db.relationship('SSOProvider', foreign_keys=[provider_id], lazy='joined',
                               backref=db.backref('identities', lazy='select'))

    @property
    def provider_type(self):
        if self.provider is not None:
            return self.provider.provider_type
        return self.orphan_of.split(':', 1)[0] if self.orphan_of else None

    @property
    def state(self):
        if self.provider_id is None:
            return 'orphan'
        return 'bound' if self.external_id else 'pending'

    def bind(self, external_id):
        self.external_id = external_id
        self.bound_at = utc_now() if external_id else None

    def to_dict(self):
        return {
            'id': self.id,
            'provider_id': self.provider_id,
            'provider_name': self.provider.name if self.provider is not None else None,
            'provider_type': self.provider_type,
            'orphan_of': self.orphan_of,
            'external_id': self.external_id,
            'state': self.state,
            'created_at': utc_isoformat(self.created_at),
            'bound_at': utc_isoformat(self.bound_at),
            'created_by': self.created_by,
        }
