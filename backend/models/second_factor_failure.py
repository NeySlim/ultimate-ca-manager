"""Failed second-factor and WebAuthn attempts, shared by every node (upgrade step 159)."""
from models import db


class SecondFactorFailure(db.Model):
    """One counter per target: ``kind`` '2fa' keys a pending login's user id, 'webauthn' a
    username. ``locked_until`` set means the target is refused until then."""
    __tablename__ = 'second_factor_failures'
    # Serves the purge run before each reservation: an expired lock, or an idle count
    __table_args__ = (db.Index('ix_second_factor_failures_purge', 'locked_until', 'updated_at'),)

    kind = db.Column(db.String(16), primary_key=True)
    target = db.Column(db.String(255), primary_key=True)
    failures = db.Column(db.Integer, nullable=False)
    locked_until = db.Column(db.DateTime)
    updated_at = db.Column(db.DateTime, nullable=False)
