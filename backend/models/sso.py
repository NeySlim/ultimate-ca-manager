"""
SSO Provider Models - UCM Pro
SAML, OAuth2, LDAP/AD integration
Secrets are encrypted at rest using Fernet encryption
"""

from models import db
from datetime import datetime
import json
from utils.datetime_utils import utc_now, utc_isoformat


class SSOProvider(db.Model):
    """SSO Provider configuration"""
    __tablename__ = 'pro_sso_providers'
    
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False, unique=True)
    provider_type = db.Column(db.String(50), nullable=False)  # saml, oauth2, ldap
    enabled = db.Column(db.Boolean, default=False)
    is_default = db.Column(db.Boolean, default=False)
    
    # Common settings
    display_name = db.Column(db.String(200))
    icon = db.Column(db.String(100))  # Icon name for UI
    
    # SAML settings
    saml_metadata_url = db.Column(db.String(500))  # IDP metadata URL for auto-config
    saml_entity_id = db.Column(db.String(500))
    saml_sso_url = db.Column(db.String(500))
    saml_slo_url = db.Column(db.String(500))
    saml_certificate = db.Column(db.Text)  # Public cert, not secret
    saml_sign_requests = db.Column(db.Boolean, default=True)
    saml_sp_cert_source = db.Column(db.String(50), default='https')  # 'https' or cert ID
    saml_verify_ssl = db.Column(db.Boolean, default=True)
    saml_ca_bundle = db.Column(db.Text)  # PEM content
    
    # OAuth2 settings
    oauth2_client_id = db.Column(db.String(500))
    _oauth2_client_secret = db.Column('oauth2_client_secret', db.String(500))  # Encrypted
    oauth2_auth_url = db.Column(db.String(500))
    oauth2_token_url = db.Column(db.String(500))
    oauth2_userinfo_url = db.Column(db.String(500))
    oauth2_scopes = db.Column(db.String(500))  # JSON array
    oauth2_issuer = db.Column(db.String(500))
    oauth2_jwks_uri = db.Column(db.String(500))
    # Explicit compatibility opt-out. OIDC ID tokens are verified by default.
    id_token_verify = db.Column(db.Boolean, default=True, nullable=False)
    oauth2_verify_ssl = db.Column(db.Boolean, default=True)
    oauth2_ca_bundle = db.Column(db.Text)  # PEM content
    
    # LDAP settings
    ldap_server = db.Column(db.String(500))
    ldap_port = db.Column(db.Integer, default=389)
    ldap_use_ssl = db.Column(db.Boolean, default=False)
    ldap_verify_ssl = db.Column(db.Boolean, default=True)
    ldap_ca_bundle = db.Column(db.Text)  # PEM content
    ldap_bind_dn = db.Column(db.String(500))
    _ldap_bind_password = db.Column('ldap_bind_password', db.String(500))  # Encrypted
    ldap_base_dn = db.Column(db.String(500))
    ldap_user_filter = db.Column(db.String(500), default='(uid={username})')
    ldap_group_filter = db.Column(db.String(500))
    ldap_username_attr = db.Column(db.String(100), default='uid')
    ldap_email_attr = db.Column(db.String(100), default='mail')
    ldap_fullname_attr = db.Column(db.String(100), default='cn')
    # Immutable id attribute (entryUUID on OpenLDAP, objectGUID on AD). Empty →
    # auto-detect at login (objectGUID then entryUUID), falling back to the DN.
    ldap_uid_attr = db.Column(db.String(100))
    ldap_group_member_attr = db.Column(db.String(100), default='member')  # member, uniqueMember, or memberOf
    
    # Default-deny: if set, user must belong to at least one of these groups
    # to be allowed to login. Empty/None = no restriction (all authenticated users allowed).
    ldap_required_groups = db.Column(db.Text)  # JSON array of group names
    
    # LDAP account status attribute for detecting disabled accounts.
    # AD: 'userAccountControl' (bit 2 = disabled). OpenLDAP: 'accountStatus'.
    # None = auto-detect based on vendor heuristics.
    account_status_attr = db.Column(db.String(100))
    
    # Attribute mapping (JSON)
    attribute_mapping = db.Column(db.Text)  # {"username": "...", "email": "...", "role": "..."}
    
    # Role mapping (JSON) - map SSO groups to UCM roles
    role_mapping = db.Column(db.Text)  # {"admins": "admin", "users": "viewer"}
    default_role = db.Column(db.String(50), default='viewer')
    
    # Auto-provisioning
    auto_create_users = db.Column(db.Boolean, default=True)
    auto_update_users = db.Column(db.Boolean, default=True)
    # Re-sync role from SSO on every login (#81). Default OFF: role changes
    # made in the UCM UI are preserved across logins. When ON, the role is
    # only updated if `role_mapping` resolves; `default_role` is never
    # applied to existing users.
    sync_role_on_login = db.Column(db.Boolean, default=False, nullable=False)

    # Force TOTP 2FA enrolment for users authenticating through this provider
    # (#141). Independent of the global `enforce_2fa` setting, which only gates
    # local accounts. Default OFF to avoid surprising existing deployments.
    enforce_2fa = db.Column(db.Boolean, default=False, nullable=False)

    # Timestamps
    created_at = db.Column(db.DateTime, default=utc_now)
    updated_at = db.Column(db.DateTime, default=utc_now, onupdate=utc_now)
    last_used_at = db.Column(db.DateTime)
    
    # Encrypted property accessors for secrets
    @property
    def oauth2_client_secret(self):
        """Decrypt OAuth2 client secret"""
        if not self._oauth2_client_secret:
            return None
        try:
            from utils.encryption import decrypt_if_needed
            return decrypt_if_needed(self._oauth2_client_secret)
        except Exception:
            return self._oauth2_client_secret
    
    @oauth2_client_secret.setter
    def oauth2_client_secret(self, value):
        """Encrypt OAuth2 client secret before storing"""
        if value:
            try:
                from utils.encryption import encrypt_if_needed
                self._oauth2_client_secret = encrypt_if_needed(value)
            except Exception:
                self._oauth2_client_secret = value
        else:
            self._oauth2_client_secret = None
    
    @property
    def ldap_bind_password(self):
        """Decrypt LDAP bind password"""
        if not self._ldap_bind_password:
            return None
        try:
            from utils.encryption import decrypt_if_needed
            return decrypt_if_needed(self._ldap_bind_password)
        except Exception:
            return self._ldap_bind_password
    
    @ldap_bind_password.setter
    def ldap_bind_password(self, value):
        """Encrypt LDAP bind password before storing"""
        if value:
            try:
                from utils.encryption import encrypt_if_needed
                self._ldap_bind_password = encrypt_if_needed(value)
            except Exception:
                self._ldap_bind_password = value
        else:
            self._ldap_bind_password = None
    
    def to_dict(self, include_secrets=False):
        """Convert to dictionary"""
        data = {
            'id': self.id,
            'name': self.name,
            'provider_type': self.provider_type,
            'enabled': self.enabled,
            'is_default': self.is_default,
            'display_name': self.display_name or self.name,
            'icon': self.icon,
            'default_role': self.default_role,
            'auto_create_users': self.auto_create_users,
            'auto_update_users': self.auto_update_users,
            'sync_role_on_login': bool(self.sync_role_on_login),
            'enforce_2fa': bool(self.enforce_2fa),
            'created_at': utc_isoformat(self.created_at),
            'updated_at': utc_isoformat(self.updated_at),
            'last_used_at': utc_isoformat(self.last_used_at),
        }
        
        # Type-specific fields
        if self.provider_type == 'saml':
            data.update({
                'saml_metadata_url': self.saml_metadata_url,
                'saml_entity_id': self.saml_entity_id,
                'saml_sso_url': self.saml_sso_url,
                'saml_slo_url': self.saml_slo_url,
                'saml_sign_requests': self.saml_sign_requests,
                'saml_sp_cert_source': self.saml_sp_cert_source or 'https',
                'saml_certificate': self.saml_certificate,
                'saml_verify_ssl': self.saml_verify_ssl if self.saml_verify_ssl is not None else True,
                'saml_ca_bundle': self.saml_ca_bundle or '',
            })
        elif self.provider_type == 'oauth2':
            data.update({
                'oauth2_client_id': self.oauth2_client_id,
                'oauth2_auth_url': self.oauth2_auth_url,
                'oauth2_token_url': self.oauth2_token_url,
                'oauth2_userinfo_url': self.oauth2_userinfo_url,
                'oauth2_scopes': json.loads(self.oauth2_scopes) if self.oauth2_scopes else [],
                'oauth2_issuer': self.oauth2_issuer,
                'oauth2_jwks_uri': self.oauth2_jwks_uri,
                # Set false only for legacy providers that cannot publish JWKS.
                'id_token_verify': self.id_token_verify is not False,
                'oauth2_client_secret': '***' if self.oauth2_client_secret else None,
                'oauth2_verify_ssl': self.oauth2_verify_ssl if self.oauth2_verify_ssl is not None else True,
                'oauth2_ca_bundle': self.oauth2_ca_bundle or '',
            })
            if include_secrets:
                data['oauth2_client_secret'] = self.oauth2_client_secret
        elif self.provider_type == 'ldap':
            data.update({
                'ldap_server': self.ldap_server,
                'ldap_port': self.ldap_port,
                'ldap_use_ssl': self.ldap_use_ssl,
                'ldap_verify_ssl': self.ldap_verify_ssl if self.ldap_verify_ssl is not None else True,
                'ldap_ca_bundle': self.ldap_ca_bundle or '',
                'ldap_bind_dn': self.ldap_bind_dn,
                'ldap_base_dn': self.ldap_base_dn,
                'ldap_user_filter': self.ldap_user_filter,
                'ldap_group_filter': self.ldap_group_filter,
                'ldap_group_member_attr': self.ldap_group_member_attr or 'member',
                'ldap_username_attr': self.ldap_username_attr,
                'ldap_email_attr': self.ldap_email_attr,
                'ldap_fullname_attr': self.ldap_fullname_attr,
                'ldap_uid_attr': self.ldap_uid_attr,
                'ldap_bind_password': '***' if self.ldap_bind_password else None,
                'ldap_required_groups': self.ldap_required_groups or '',
                'account_status_attr': self.account_status_attr,
            })
            if include_secrets:
                data['ldap_bind_password'] = self.ldap_bind_password
        
        # Parse JSON fields
        try:
            data['attribute_mapping'] = json.loads(self.attribute_mapping) if self.attribute_mapping else {}
        except Exception:
            data['attribute_mapping'] = {}
        
        try:
            data['role_mapping'] = json.loads(self.role_mapping) if self.role_mapping else {}
        except Exception:
            data['role_mapping'] = {}
        
        return data


class SSOSession(db.Model):
    """Track SSO login sessions for audit and logout"""
    __tablename__ = 'pro_sso_sessions'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    provider_id = db.Column(db.Integer, db.ForeignKey('pro_sso_providers.id'), nullable=False)
    session_id = db.Column(db.String(500), unique=True)  # SSO session identifier
    sso_name_id = db.Column(db.String(500))  # SAML NameID or OAuth subject
    created_at = db.Column(db.DateTime, default=utc_now)
    expires_at = db.Column(db.DateTime)
    
    # Relationships
    user = db.relationship('User', backref='sso_sessions')
    provider = db.relationship('SSOProvider', backref='sessions')
    
    def to_dict(self):
        return {
            'id': self.id,
            'user_id': self.user_id,
            'provider_id': self.provider_id,
            'provider_name': self.provider.name if self.provider else None,
            'created_at': utc_isoformat(self.created_at),
            'expires_at': utc_isoformat(self.expires_at),
        }
