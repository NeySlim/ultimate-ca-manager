"""Windows enrollment profiles: one realm each, served by XCEP, WSTEP and Kerberos.

Migration 155 turns a 2.x installation's single configuration into the profile ``is_default``.
"""
from models import db
from utils.datetime_utils import utc_now
from utils.policy_identity import random_oid_root, random_policy_id, template_oid


class WindowsEnrollmentProfile(db.Model):
    __tablename__ = 'windows_enrollment_profiles'
    __table_args__ = (
        # At most one default, enforced by the database on both backends
        db.Index('uq_windows_enrollment_profiles_default', 'is_default', unique=True,
                 sqlite_where=db.text('is_default'), postgresql_where=db.text('is_default')),
        # A deleted profile's id is never handed out again, as step 155 creates the table
        {'sqlite_autoincrement': True},
    )

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), unique=True, nullable=False)
    # Compared exactly (RFC 4120 §6.1); NULL: not determined yet, Kerberos is refused
    realm = db.Column(db.String(255), unique=True, nullable=True)
    is_default = db.Column(db.Boolean, nullable=False, default=False)
    enabled = db.Column(db.Boolean, nullable=False, default=True)
    # No route deletes a connector; a replacing restore refuses to remove one a profile names
    # (connector_deletion_blockers). SET NULL holds on PostgreSQL only: SQLite enforces no key
    connector_id = db.Column(db.Integer, db.ForeignKey('ad_connector_config.id', ondelete='SET NULL'),
                             nullable=True)
    # Refids as the 2.x settings held them; deletion_blockers keeps a used CA in place
    issuing_ca_refid = db.Column(db.String(36), index=True)
    # NULL: the issuing CA, whose templates XCEP announces
    policy_ca_refid = db.Column(db.String(36), index=True)
    # JSON list of former issuing CA refids whose certificates still renew under this profile;
    # the operator's list, fed by a change of issuing CA (never read by XCEP or for new issuance)
    renewal_ca_refids = db.Column(db.Text, default='[]')
    # The policy's identity (MS-XCEP policyID, template OID root): fixed once, no route writes
    # it and no CA change moves it, so enrolled clients keep the policy server they registered
    policy_id = db.Column(db.String(36), nullable=False, default=random_policy_id)
    policy_oid_root = db.Column(db.String(100), nullable=False, default=random_oid_root)
    validity_days = db.Column(db.Integer, nullable=False, default=365)
    # Shared UsernamePassword accounts; the passwords are hashes (utils.password_hash)
    xcep_username = db.Column(db.Text)
    xcep_password = db.Column(db.Text)
    wstep_username = db.Column(db.Text)
    wstep_password = db.Column(db.Text)
    # When set, replace the template's for every issuance of the profile
    allowed_ad_group = db.Column(db.String(255))
    pinned_subject_fields = db.Column(db.Text)
    # Base64 of the keytab under the master key (security.encryption.encrypt_text)
    keytab = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=utc_now)
    created_by = db.Column(db.String(80))
    updated_at = db.Column(db.DateTime, default=utc_now, onupdate=utc_now)
    updated_by = db.Column(db.String(80))

    @property
    def policy_refid(self):
        """The refid of the CA XCEP announces."""
        return self.policy_ca_refid or self.issuing_ca_refid

    def template_oid(self, template_id):
        """The OID XCEP announces for the template of *template_id* in this profile's policy."""
        return template_oid(self.policy_oid_root, template_id)

    def keytab_bytes(self):
        """The keytab, or None. Raises ValueError when it cannot be decrypted here."""
        if not self.keytab:
            return None
        import base64
        from security.encryption import decrypt_text
        return base64.b64decode(decrypt_text(self.keytab))

    def set_keytab(self, data):
        import base64
        from security.encryption import encrypt_text
        self.keytab = encrypt_text(base64.b64encode(data).decode('ascii')) if data else None


class WindowsProfileTemplate(db.Model):
    """The templates a profile offers; none listed: the templates of its CA."""
    __tablename__ = 'windows_profile_templates'
    __table_args__ = (db.UniqueConstraint('profile_id', 'template_id',
                                          name='uq_windows_profile_templates'),
                      {'sqlite_autoincrement': True})

    id = db.Column(db.Integer, primary_key=True)
    profile_id = db.Column(db.Integer, db.ForeignKey('windows_enrollment_profiles.id', ondelete='CASCADE'),
                           nullable=False, index=True)
    template_id = db.Column(db.Integer, db.ForeignKey('certificate_templates.id'), nullable=False, index=True)


def profile_names_of(certs):
    """Id to name of the profiles behind ``certs``, in one query, for ``Certificate.to_dict``"""
    ids = {c.windows_profile_id for c in certs if c.windows_profile_id is not None}
    if not ids:
        return {}
    return dict(db.session.query(WindowsEnrollmentProfile.id, WindowsEnrollmentProfile.name)
                .filter(WindowsEnrollmentProfile.id.in_(ids)).all())
