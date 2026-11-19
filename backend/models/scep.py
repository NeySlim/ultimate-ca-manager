"""
SCEPRequest Model - SCEP enrollment request tracking
ScepProfile Model - named SCEP endpoints (issue #228)
"""
from models import db
from utils.datetime_utils import utc_now, utc_isoformat


class IntuneApp(db.Model):
    """One Microsoft Entra app registration, shared by the SCEP profiles that
    validate Intune challenges with it (issue #358). The secret is encrypted
    with utils.encryption, the database key, as the per-profile column was."""

    __tablename__ = "intune_apps"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), unique=True, nullable=False)
    tenant_id = db.Column(db.String(255), nullable=False)
    client_id = db.Column(db.String(255), nullable=False)
    client_secret = db.Column(db.Text, nullable=False)
    last_test_at = db.Column(db.DateTime)
    last_test_result = db.Column(db.String(255))
    created_at = db.Column(db.DateTime, default=utc_now)
    created_by = db.Column(db.String(80))
    updated_at = db.Column(db.DateTime, onupdate=utc_now)
    updated_by = db.Column(db.String(80))

    profiles = db.relationship("ScepProfile", back_populates="intune_app", lazy="select")

    def to_dict(self):
        return {
            "id": self.id,
            "name": self.name,
            "tenant_id": self.tenant_id,
            "client_id": self.client_id,
            "client_secret_set": bool(self.client_secret),
            "last_test_at": utc_isoformat(self.last_test_at),
            "last_test_result": self.last_test_result,
            "profile_count": len(self.profiles),
            "profile_names": sorted(p.name for p in self.profiles),
            "created_at": utc_isoformat(self.created_at),
            "created_by": self.created_by,
            "updated_at": utc_isoformat(self.updated_at),
            "updated_by": self.updated_by,
        }

    def decrypted_secret(self):
        """The client secret, whether or not it was stored encrypted (a restore
        writes the archive's cleartext back through the database layer, an
        older row may predate at-rest encryption)."""
        if not self.client_secret:
            return ''
        from utils.encryption import decrypt_value, is_encrypted
        if not is_encrypted(self.client_secret):
            return self.client_secret
        return decrypt_value(self.client_secret) or ''


class ScepProfile(db.Model):
    """A named SCEP endpoint served at /scep/<url_slug>/pkiclient.exe.

    Each profile binds its own CA, optional certificate template (whose
    KU/EKU/validity govern issuance, consistent with template-governed
    issuance elsewhere), challenge password and approval policy — so device
    certs, user certs, or per-tenant enrollments each get a dedicated URL
    instead of sharing the single global endpoint. The unlabelled endpoints
    keep serving the global SystemConfig-based setup unchanged.
    """

    __tablename__ = "scep_profiles"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), unique=True, nullable=False)
    # URL path segment: /scep/<url_slug>/pkiclient.exe
    url_slug = db.Column(db.String(64), unique=True, nullable=False, index=True)
    description = db.Column(db.String(255))
    enabled = db.Column(db.Boolean, default=True, nullable=False)

    ca_refid = db.Column(
        db.String(36),
        db.ForeignKey("certificate_authorities.refid"),
        nullable=False,
        index=True,
    )
    # Plain integer on purpose (no db.ForeignKey): mirrors Certificate.template_id
    template_id = db.Column(db.Integer, nullable=True)

    # Encrypted at rest (security.encryption.encrypt_text); empty = no challenge
    challenge_password = db.Column(db.Text)
    challenge_generated_at = db.Column(db.DateTime)
    auto_approve = db.Column(db.Boolean, default=False, nullable=False)

    # Microsoft Intune SCEP challenge validation (issue #228 part 2). Mutually
    # exclusive with challenge_password in practice: Intune issues its own
    # per-device encrypted+signed challenge blob instead of a static secret,
    # validated live against Intune's API rather than compared locally.
    intune_enabled = db.Column(db.Boolean, default=False, nullable=False)
    # The app registration the challenge is validated with (issue #358): one
    # row of intune_apps, shared between profiles.
    intune_app_id = db.Column(db.Integer, db.ForeignKey("intune_apps.id"), nullable=True)
    intune_app = db.relationship("IntuneApp", back_populates="profiles", lazy="joined")
    # Frozen since migration 092 moved them to intune_apps: kept for a
    # downgrade, never read, cleared by the migration and by a restore.
    intune_tenant_id = db.Column(db.String(255))
    intune_client_id = db.Column(db.String(255))
    intune_client_secret = db.Column(db.Text)
    intune_last_test_at = db.Column(db.DateTime)
    intune_last_test_result = db.Column(db.String(255))

    created_at = db.Column(db.DateTime, default=utc_now)
    created_by = db.Column(db.String(80))
    updated_at = db.Column(db.DateTime, onupdate=utc_now)
    updated_by = db.Column(db.String(80))

    def to_dict(self, include_challenge=False):
        data = {
            "id": self.id,
            "name": self.name,
            "url_slug": self.url_slug,
            "description": self.description,
            "enabled": self.enabled,
            "ca_refid": self.ca_refid,
            "template_id": self.template_id,
            "auto_approve": self.auto_approve,
            "challenge_set": bool(self.challenge_password),
            "challenge_generated_at": utc_isoformat(self.challenge_generated_at),
            "intune_enabled": self.intune_enabled,
            "intune_app_id": self.intune_app_id,
            "intune_app_name": self.intune_app.name if self.intune_app else None,
            # Echoed from the app for one release: readers of the pre-092 shape
            "intune_tenant_id": self.intune_app.tenant_id if self.intune_app else None,
            "intune_client_id": self.intune_app.client_id if self.intune_app else None,
            "intune_client_secret_set": bool(self.intune_app and self.intune_app.client_secret),
            "intune_last_test_at": utc_isoformat(self.intune_app.last_test_at) if self.intune_app else None,
            "intune_last_test_result": self.intune_app.last_test_result if self.intune_app else None,
            "created_at": utc_isoformat(self.created_at),
            "created_by": self.created_by,
            "updated_at": utc_isoformat(self.updated_at),
            "updated_by": self.updated_by,
        }
        if include_challenge:
            data["challenge_password"] = self.decrypted_challenge()
        return data

    def decrypted_challenge(self):
        if not self.challenge_password:
            return ''
        try:
            from security.encryption import decrypt_text
            return decrypt_text(self.challenge_password)
        except Exception:
            # Legacy/plaintext value (e.g. encryption disabled at write time)
            return self.challenge_password

    def intune_credentials(self):
        """(tenant_id, client_id, client_secret) of the app this profile
        validates with, or ('', '', '') when none is bound."""
        app = self.intune_app
        if app is None:
            return '', '', ''
        return app.tenant_id or '', app.client_id or '', app.decrypted_secret()

    def decrypted_intune_secret(self):
        return self.intune_credentials()[2]


class SCEPRequest(db.Model):
    """SCEP enrollment request tracking.

    The ``transaction_id`` alone is not unique: RFC 8894 §3.2.1.1 only asks
    the client for a unique value, often derived from its public key, so the
    same client enrolling against two CAs hosted here would collide.
    The natural key is therefore ``(transaction_id, ca_refid)``.
    """

    __tablename__ = "scep_requests"
    __table_args__ = (
        db.UniqueConstraint("transaction_id", "ca_refid",
                            name="uq_scep_request_txn_ca"),
    )

    id = db.Column(db.Integer, primary_key=True)
    transaction_id = db.Column(db.String(100), nullable=False, index=True)
    ca_refid = db.Column(
        db.String(36),
        db.ForeignKey("certificate_authorities.refid"),
        nullable=True,   # nullable for backfill compatibility; new rows always set
        index=True,
    )
    csr = db.Column(db.Text, nullable=False)  # Base64 encoded
    status = db.Column(db.String(20), default="pending")  # pending, approved, rejected
    approved_by = db.Column(db.String(80))
    approved_at = db.Column(db.DateTime)
    rejection_reason = db.Column(db.String(255))

    # Generated certificate
    cert_refid = db.Column(db.String(36))

    # Request details
    subject = db.Column(db.Text)
    client_ip = db.Column(db.String(45))
    # The profile the request came through (plain integer, as
    # ScepProfile.template_id): its template governs the certificate when
    # the request is approved by hand, as it does on auto-approval. NULL for
    # the global endpoint and for rows older than migration 085.
    profile_id = db.Column(db.Integer, nullable=True)
    # The certificate a RenewalReq was signed with (base64 PEM), so that a
    # manual approval renews it (archives it) as auto-approval does. NULL
    # for an initial enrolment and for rows older than migration 086.
    renewal_of = db.Column(db.Text, nullable=True)

    created_at = db.Column(db.DateTime, default=utc_now)

    def to_dict(self):
        """Convert to dictionary"""
        return {
            "id": self.id,
            "transaction_id": self.transaction_id,
            "ca_refid": self.ca_refid,
            "status": self.status,
            "subject": self.subject,
            "client_ip": self.client_ip,
            "profile_id": self.profile_id,
            "renewal": bool(self.renewal_of),
            "approved_by": self.approved_by,
            "approved_at": utc_isoformat(self.approved_at),
            "rejection_reason": self.rejection_reason,
            "cert_refid": self.cert_refid,
            "created_at": utc_isoformat(self.created_at),
        }
