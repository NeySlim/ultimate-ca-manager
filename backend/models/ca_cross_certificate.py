"""A certificate that re-certifies a CA's key under another issuer (a cross-certificate).

The CA keeps its own certificate in ``CA.crt``; its cross-certificates live here.
At most one per CA is ``served`` (see services/ca/cross_certs.py).
"""
from models import db
from utils.datetime_utils import utc_now, utc_isoformat


class CACrossCertificate(db.Model):
    __tablename__ = 'ca_cross_certificates'

    id = db.Column(db.Integer, primary_key=True)
    ca_id = db.Column(db.Integer, db.ForeignKey('certificate_authorities.id', ondelete='CASCADE'),
                      nullable=False, index=True)
    # Base64 of the PEM, as CA.crt
    crt = db.Column(db.Text, nullable=False)
    fingerprint_sha256 = db.Column(db.String(64), nullable=False, unique=True)
    subject = db.Column(db.Text)
    issuer = db.Column(db.Text)
    # refid of the issuing CA when this installation holds it; no FK, it may be deleted
    issuer_caref = db.Column(db.String(36), index=True)
    serial_number = db.Column(db.String(100))
    aki = db.Column(db.String(200))
    valid_from = db.Column(db.DateTime)
    valid_to = db.Column(db.DateTime)
    served = db.Column(db.Boolean, nullable=False, default=False, server_default=db.false())
    revoked = db.Column(db.Boolean, nullable=False, default=False, server_default=db.false())
    revoked_at = db.Column(db.DateTime)
    revoke_reason = db.Column(db.String(100))
    created_at = db.Column(db.DateTime, default=utc_now)
    created_by = db.Column(db.String(80))

    ca = db.relationship('CA', backref=db.backref('cross_certificates', cascade='all, delete-orphan',
                                                  order_by='CACrossCertificate.id'))

    @property
    def expired(self):
        return bool(self.valid_to and self.valid_to <= utc_now())

    @property
    def servable(self):
        """Only a valid, unrevoked cross-certificate may be served or offered."""
        return not self.revoked and not self.expired

    def to_dict(self):
        return {
            'id': self.id,
            'ca_id': self.ca_id,
            'fingerprint_sha256': self.fingerprint_sha256,
            'subject': self.subject,
            'issuer': self.issuer,
            'issuer_caref': self.issuer_caref,
            'serial_number': self.serial_number,
            'aki': self.aki,
            'valid_from': utc_isoformat(self.valid_from),
            'valid_to': utc_isoformat(self.valid_to),
            'served': bool(self.served),
            'revoked': bool(self.revoked),
            'revoked_at': utc_isoformat(self.revoked_at),
            'revoke_reason': self.revoke_reason,
            'expired': self.expired,
            'created_at': utc_isoformat(self.created_at),
            'created_by': self.created_by,
        }
