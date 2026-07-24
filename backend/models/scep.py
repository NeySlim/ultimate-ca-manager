"""
SCEPRequest Model - SCEP enrollment request tracking
ScepProfile Model - named SCEP endpoints (issue #228)
"""
from models import db
from utils.datetime_utils import utc_now, utc_isoformat


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


class SCEPRequest(db.Model):
    """SCEP enrollment request tracking.

    The ``transaction_id`` alone is not unique: per RFC 8894 §3.2.1.1 it is
    derived from the requester's public key, so the same client enrolling
    against two different CAs hosted on the same UCM instance would collide.
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
            "approved_by": self.approved_by,
            "approved_at": utc_isoformat(self.approved_at),
            "rejection_reason": self.rejection_reason,
            "cert_refid": self.cert_refid,
            "created_at": utc_isoformat(self.created_at),
        }
