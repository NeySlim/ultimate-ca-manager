"""Data-encryption keys wrapped by the key-encryption key (migration 153)."""
from models import db


class EncryptionKey(db.Model):
    """One DEK version; ``wrapped`` is NULL for the KEK material itself and for the disabled marker."""
    __tablename__ = 'encryption_keys'

    version = db.Column(db.Integer, primary_key=True, autoincrement=False)
    state = db.Column(db.String(16), nullable=False)
    kek_id = db.Column(db.String(16), nullable=False)
    wrapped = db.Column(db.Text)
    created_at = db.Column(db.DateTime, nullable=False)
    # Set once the DEK only decrypts: kept for reading until then (security.dek_rotation)
    retire_after = db.Column(db.DateTime)
