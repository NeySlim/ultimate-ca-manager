"""
RevokedSerial Model - Persistent revocation entries that survive certificate deletion.

When a certificate is revoked and later deleted (e.g. after renewal), the
revocation must still appear in CRLs and OCSP responses until the original
certificate's notAfter has passed. This table holds the minimal data needed
to generate those revocation entries independently of the certificates table.
"""
from models import db
from utils.datetime_utils import utc_now


class RevokedSerial(db.Model):
    """Persistent revocation record — survives deletion of the certificate row."""
    __tablename__ = "revoked_serials"

    id = db.Column(db.Integer, primary_key=True)

    # CA linkage (caref, not ca_id, to match Certificate.caref)
    caref = db.Column(db.String(36), db.ForeignKey("certificate_authorities.refid"),
                      nullable=False, index=True)

    # Serial number as stored on the certificate (hex string, lowercase)
    serial_number = db.Column(db.String(100), nullable=False, index=True)

    # Revocation metadata (mirrors Certificate fields)
    revoked_at = db.Column(db.DateTime, nullable=False, default=utc_now)
    revoke_reason = db.Column(db.String(100))
    invalidity_at = db.Column(db.DateTime)

    # Certificate's original validity end — once this passes, the entry is
    # stale and can be purged (the cert is expired, CRL/OCSP no longer needs it)
    valid_to = db.Column(db.DateTime, nullable=False)

    # Audit
    created_at = db.Column(db.DateTime, default=utc_now)

    # Optional: link back to the certificate row if it still exists
    certificate_id = db.Column(db.Integer, nullable=True)

    def to_dict(self):
        return {
            "id": self.id,
            "caref": self.caref,
            "serial_number": self.serial_number,
            "revoked_at": self.revoked_at.isoformat() if self.revoked_at else None,
            "revoke_reason": self.revoke_reason,
            "invalidity_at": self.invalidity_at.isoformat() if self.invalidity_at else None,
            "valid_to": self.valid_to.isoformat() if self.valid_to else None,
            "certificate_id": self.certificate_id,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
