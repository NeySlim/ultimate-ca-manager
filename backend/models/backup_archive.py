"""HA backup archives kept in the database, in fixed-size chunks (upgrade step 159)."""
from models import db

_ID = db.BigInteger().with_variant(db.Integer, 'sqlite')


class BackupArchive(db.Model):
    """One encrypted archive every node lists and serves; committed with all its chunks,
    so a row exists only for an archive written whole."""
    __tablename__ = 'backup_archives'

    id = db.Column(_ID, primary_key=True)
    filename = db.Column(db.String(128), nullable=False, unique=True)
    node_id = db.Column(db.String(255), nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, index=True)
    size = db.Column(db.BigInteger, nullable=False)
    sha256 = db.Column(db.String(64), nullable=False)
    chunk_size = db.Column(db.Integer, nullable=False)
    chunk_count = db.Column(db.Integer, nullable=False)


class BackupArchiveChunk(db.Model):
    """Bytes ``seq * chunk_size`` onwards of an archive, as the container wrote them (encrypted)."""
    __tablename__ = 'backup_archive_chunks'

    archive_id = db.Column(_ID, db.ForeignKey('backup_archives.id', ondelete='CASCADE'),
                           primary_key=True)
    seq = db.Column(db.Integer, primary_key=True)
    data = db.Column(db.LargeBinary, nullable=False)
