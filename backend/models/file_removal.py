"""Paths a restore removed from the disk, by files generation (migration 164)."""
from models import db


class FileRemoval(db.Model):
    """One path whose row a restore removed: a full reconciliation deletes the regular file
    there. Outside HA the node's complete pass then drops the rows of its generation; in HA
    they stay (any node may still be behind), are replayed by every full pass, and grow with
    each restore. Local to the installation, never exported nor restored."""
    __tablename__ = 'file_removals'

    id = db.Column(db.Integer, primary_key=True)
    generation = db.Column(db.Integer, nullable=False, index=True)
    path = db.Column(db.String(1024), nullable=False, index=True)
