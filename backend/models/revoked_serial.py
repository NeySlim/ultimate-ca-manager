"""Persistent revocation records.

One row per serial a CA has revoked. It outlives the certificate row, so the
CRL and the OCSP responder keep answering "revoked" once the certificate is
deleted. Deleting the CA purges its rows (services/deletion_blockers.py).
"""
from sqlalchemy.orm import validates

from models import db
from utils.datetime_utils import utc_now, utc_isoformat


class RevokedSerial(db.Model):
    __tablename__ = 'revoked_serials'
    # Same keyword as migration 078: a row id is never reused
    __table_args__ = {'sqlite_autoincrement': True}

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    caref = db.Column(db.String(36), db.ForeignKey('certificate_authorities.refid'),
                      nullable=False, index=True)
    serial_number = db.Column(db.String(100), nullable=False, index=True)
    revoked_at = db.Column(db.DateTime, nullable=False, default=utc_now)
    revoke_reason = db.Column(db.String(100))
    invalidity_at = db.Column(db.DateTime)
    # The CRL keeps the entry until this date
    valid_to = db.Column(db.DateTime, nullable=False)
    created_at = db.Column(db.DateTime, default=utc_now,
                           server_default=db.text('CURRENT_TIMESTAMP'))
    # Application link only: no FK, the row must survive the certificate
    certificate_id = db.Column(db.Integer, index=True)
    # SHA-256 of the revoked key's SubjectPublicKeyInfo: a compromise outlives the certificate row
    public_key_sha256 = db.Column(db.String(64), index=True)

    @validates('serial_number')
    def _canonical_serial_number(self, key, value):
        # Same spelling as certificates.serial_number, which revocations are matched against
        from utils.serial_format import canonical_serial
        return canonical_serial(value)

    def to_dict(self):
        return {
            'id': self.id,
            'caref': self.caref,
            'serial_number': self.serial_number,
            'revoked_at': utc_isoformat(self.revoked_at),
            'revoke_reason': self.revoke_reason,
            'invalidity_at': utc_isoformat(self.invalidity_at),
            'valid_to': utc_isoformat(self.valid_to),
            'certificate_id': self.certificate_id,
            'public_key_sha256': self.public_key_sha256,
            'created_at': utc_isoformat(self.created_at),
        }

    def __repr__(self):
        return f'<RevokedSerial {self.caref}:{self.serial_number}>'
