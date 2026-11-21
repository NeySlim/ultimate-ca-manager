"""Files every node writes from the database (migration 152)."""
from models import db


class SharedFile(db.Model):
    """One node-local file kept in the database; ``content`` is its bytes as
    ``utils.key_codec.store_pem_bytes`` stores them (under the master key)."""
    __tablename__ = 'shared_files'

    name = db.Column(db.String(64), primary_key=True)
    content = db.Column(db.Text, nullable=False)
    updated_at = db.Column(db.DateTime)
    updated_by = db.Column(db.String(255))
