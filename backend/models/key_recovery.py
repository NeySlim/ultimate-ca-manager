"""Key recovery (escrow) request model.

A controlled, dual-control workflow to recover an archived private key. UCM
already stores server-generated private keys encrypted at rest; recovering one
(re-exporting the key material) is the single most sensitive operation in the
product, so it goes through request → approve (four-eyes) → recover, with every
step audited. End-entity certificate keys only.
"""
from datetime import datetime

from models import db
from utils.datetime_utils import utc_now

STATUS_PENDING = 'pending'
STATUS_APPROVED = 'approved'
STATUS_REJECTED = 'rejected'
STATUS_RECOVERED = 'recovered'
STATUS_CANCELLED = 'cancelled'


class KeyRecoveryRequest(db.Model):
    __tablename__ = 'key_recovery_requests'

    id = db.Column(db.Integer, primary_key=True)
    # Certificate whose archived private key is being recovered. Denormalized
    # refid/cn are kept for audit even if the certificate is later deleted.
    cert_id = db.Column(db.Integer, nullable=False, index=True)
    cert_refid = db.Column(db.String(64))
    cert_cn = db.Column(db.String(255))

    reason = db.Column(db.Text, nullable=False)
    status = db.Column(db.String(16), nullable=False, default=STATUS_PENDING, index=True)

    requested_by = db.Column(db.String(120), nullable=False)
    requested_at = db.Column(db.DateTime, default=utc_now, nullable=False)

    decided_by = db.Column(db.String(120))
    decided_at = db.Column(db.DateTime)
    decision_note = db.Column(db.Text)

    recovered_by = db.Column(db.String(120))
    recovered_at = db.Column(db.DateTime)

    def to_dict(self):
        def _iso(dt):
            return dt.isoformat() if isinstance(dt, datetime) else None
        return {
            'id': self.id,
            'cert_id': self.cert_id,
            'cert_refid': self.cert_refid,
            'cert_cn': self.cert_cn,
            'reason': self.reason,
            'status': self.status,
            'requested_by': self.requested_by,
            'requested_at': _iso(self.requested_at),
            'decided_by': self.decided_by,
            'decided_at': _iso(self.decided_at),
            'decision_note': self.decision_note,
            'recovered_by': self.recovered_by,
            'recovered_at': _iso(self.recovered_at),
        }
