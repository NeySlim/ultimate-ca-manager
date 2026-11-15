"""Paths a restore removed from the disk, by files generation (migration 164)."""
from models import db


class FileRemoval(db.Model):
    """One path whose row a restore removed: every node's reconciliation deletes the
    regular file there once. Local to the installation, never exported nor restored."""
    __tablename__ = 'file_removals'

    id = db.Column(db.Integer, primary_key=True)
    generation = db.Column(db.Integer, nullable=False, index=True)
    path = db.Column(db.String(1024), nullable=False, index=True)
