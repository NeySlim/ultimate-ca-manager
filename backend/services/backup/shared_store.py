"""HA: backup archives kept in PostgreSQL, so every node lists and serves the same set.

PostgreSQL is the one store every node of a cluster shares, so an archive lives there as
fixed-size chunks (``backup_archive_chunks``) under one row (``backup_archives``). The row
and its chunks are written in a single transaction and read back before it commits: an
archive is listed only once it is whole, and an interrupted write leaves nothing behind.
Writing and reading go one chunk at a time on a connection of their own, so memory stays
bounded whatever the archive size. The bytes are the encrypted container, as on disk.
"""
import hashlib
import io
import logging
import time
from datetime import timedelta, timezone

from sqlalchemy import delete, func, insert, select, text, update
from sqlalchemy.exc import IntegrityError

from config.settings import Config
from .locking import BackupBusyError

logger = logging.getLogger(__name__)

CHUNK_SIZE = 1024 * 1024
# Seconds between two attempts at the store lock.
_LOCK_POLL = 0.1
_NAME_ATTEMPTS = 5


def enabled() -> bool:
    """Whether archives go to the database rather than to this node's disk."""
    from utils.ha import ha_enabled
    return ha_enabled()


def _tables():
    from models.backup_archive import BackupArchive, BackupArchiveChunk
    return BackupArchive.__table__, BackupArchiveChunk.__table__


def _now(conn):
    # Every node writes and compares archive times on the server's clock, never its own
    from services.scheduler_leader import cluster_utc_now
    return cluster_utc_now(conn)


def _engine():
    from models import db
    return db.engine


def _rechunk(chunks):
    """The stream as CHUNK_SIZE pieces (the last one shorter), whatever sizes it came in."""
    if isinstance(chunks, (bytes, bytearray)):
        chunks = (chunks,)
    buffer = bytearray()
    for chunk in chunks:
        buffer += chunk
        while len(buffer) >= CHUNK_SIZE:
            yield bytes(buffer[:CHUNK_SIZE])
            del buffer[:CHUNK_SIZE]
    if buffer:
        yield bytes(buffer)


def _read_chunks(conn, archive_id, count):
    chunks = _tables()[1]
    for seq in range(count):
        data = conn.execute(select(chunks.c.data).where(
            chunks.c.archive_id == archive_id, chunks.c.seq == seq)).scalar()
        if data is None:
            raise IOError(f'chunk {seq} of archive {archive_id} is missing')
        yield bytes(data)


def store_archive(data, filename_factory) -> tuple:
    """Write an archive (bytes, or an iterable of bytes) to the store. Returns ``(filename, size, sha256)``.

    The new name is inserted first, so a collision retries before the stream is consumed;
    everything else becomes visible at the single commit.
    """
    from .errors import BackupValidationError

    archives, chunks = _tables()
    with _engine().connect() as conn:
        _long_transaction(conn)
        for _ in range(_NAME_ATTEMPTS):
            filename = filename_factory()
            try:
                with conn.begin_nested():
                    archive_id = conn.execute(insert(archives).values(
                        filename=filename, node_id=Config.NODE_ID, created_at=_now(conn),
                        size=0, sha256='', chunk_size=CHUNK_SIZE, chunk_count=0,
                    ).returning(archives.c.id)).scalar_one()
                break
            except IntegrityError:
                continue
        else:
            conn.rollback()
            raise FileExistsError("Could not allocate a unique backup filename")

        digest, size, count = hashlib.sha256(), 0, 0
        for piece in _rechunk(data):
            conn.execute(insert(chunks).values(archive_id=archive_id, seq=count, data=piece))
            digest.update(piece)
            size += len(piece)
            count += 1
        sha256 = digest.hexdigest()

        # Read back before the commit, as an archive on disk is: what is stored is what was produced
        check, checked = hashlib.sha256(), 0
        for piece in _read_chunks(conn, archive_id, count):
            check.update(piece)
            checked += len(piece)
        if checked != size or check.hexdigest() != sha256:
            conn.rollback()
            raise BackupValidationError(
                f"The backup {filename} did not read back as it was written "
                f"({checked} bytes stored for {size} written)")

        conn.execute(update(archives).where(archives.c.id == archive_id).values(
            size=size, sha256=sha256, chunk_count=count, created_at=_now(conn)))
        conn.commit()
    logger.info("Backup %s stored in the database (%d bytes, %d chunks)", filename, size, count)
    return filename, size, sha256


def _as_dict(row) -> dict:
    return {
        'filename': row.filename,
        'node': row.node_id,
        'created_at': row.created_at,
        'size': int(row.size),
        'sha256': row.sha256,
    }


def age_seconds(created_at) -> int:
    """Seconds since a stored creation time, on the server's clock."""
    with _engine().connect() as conn:
        return max(0, int((_now(conn) - created_at).total_seconds()))


def list_archives() -> list:
    """Every archive in the store, newest first."""
    archives = _tables()[0]
    with _engine().connect() as conn:
        rows = conn.execute(select(archives).order_by(
            archives.c.created_at.desc(), archives.c.id.desc())).all()
    return [_as_dict(row) for row in rows]


def get_archive(filename: str):
    """One archive's record, or None."""
    archives = _tables()[0]
    with _engine().connect() as conn:
        row = conn.execute(select(archives).where(archives.c.filename == filename)).first()
    return _as_dict(row) if row is not None else None


def timestamp(created_at) -> float:
    """Epoch seconds of a stored (naive UTC) creation time."""
    return created_at.replace(tzinfo=timezone.utc).timestamp()


def _long_transaction(conn):
    """A write or a read that may idle between chunks outlives idle_in_transaction_session_timeout."""
    conn.execute(text("SET LOCAL idle_in_transaction_session_timeout = 0"))
    return conn


def _snapshot(engine):
    # One snapshot for the whole read: a deletion meanwhile cannot cut an archive short
    conn = engine.connect().execution_options(isolation_level='REPEATABLE READ')
    try:
        return _long_transaction(conn)
    except Exception:
        conn.close()
        raise


def iter_archive(filename: str):
    """The archive's bytes, chunk by chunk, or None when it is not in the store.

    The generator holds its own connection, so it can outlive the request that made it.
    """
    archives = _tables()[0]
    engine = _engine()
    conn = _snapshot(engine)
    try:
        row = conn.execute(select(archives.c.id, archives.c.chunk_count).where(
            archives.c.filename == filename)).first()
    except Exception:
        conn.close()
        raise
    if row is None:
        conn.close()
        return None

    def generate():
        try:
            yield from _read_chunks(conn, row.id, row.chunk_count)
        finally:
            conn.close()
    return generate()


class _ArchiveReader(io.RawIOBase):
    """A seekable read-only view of one stored archive, one chunk in memory at a time."""

    def __init__(self, conn, archive_id, size, chunk_size):
        self._conn = conn
        self._id = archive_id
        self._size = size
        self._chunk_size = chunk_size
        self._pos = 0
        self._cached = (None, b'')

    def readable(self):
        return True

    def seekable(self):
        return True

    def tell(self):
        return self._pos

    def seek(self, offset, whence=io.SEEK_SET):
        base = {io.SEEK_SET: 0, io.SEEK_CUR: self._pos, io.SEEK_END: self._size}[whence]
        self._pos = max(0, base + offset)
        return self._pos

    def _chunk(self, seq):
        if self._cached[0] != seq:
            chunks = _tables()[1]
            data = self._conn.execute(select(chunks.c.data).where(
                chunks.c.archive_id == self._id, chunks.c.seq == seq)).scalar()
            if data is None:
                raise IOError(f'chunk {seq} of archive {self._id} is missing')
            self._cached = (seq, bytes(data))
        return self._cached[1]

    def readinto(self, buffer):
        if self._pos >= self._size:
            return 0
        seq, offset = divmod(self._pos, self._chunk_size)
        piece = self._chunk(seq)[offset:offset + len(buffer)]
        buffer[:len(piece)] = piece
        self._pos += len(piece)
        return len(piece)

    def close(self):
        if not self.closed:
            try:
                self._conn.close()
            finally:
                super().close()


def _open(filename: str):
    """(seekable stream, archive row) from one snapshot, or None when it is not in the store."""
    archives = _tables()[0]
    conn = _snapshot(_engine())
    try:
        row = conn.execute(select(archives).where(archives.c.filename == filename)).first()
    except Exception:
        conn.close()
        raise
    if row is None:
        conn.close()
        return None
    reader = io.BufferedReader(_ArchiveReader(conn, row.id, int(row.size), row.chunk_size),
                               buffer_size=row.chunk_size)
    return reader, row


def open_archive(filename: str):
    """A seekable binary stream over a stored archive (what a restore reads), or None."""
    opened = _open(filename)
    return opened[0] if opened is not None else None


def archive_heads(length: int) -> list:
    """(filename, first `length` bytes) of every archive, without reading the rest."""
    archives, chunks = _tables()
    with _engine().connect() as conn:
        rows = conn.execute(
            select(archives.c.filename, func.substring(chunks.c.data, 1, length))
            .join(chunks, chunks.c.archive_id == archives.c.id)
            .where(chunks.c.seq == 0).order_by(archives.c.filename)).all()
    return [(name, bytes(head or b'')) for name, head in rows]


def _take_lock(conn, wait: float, purpose: str) -> None:
    """The store's lock, held until `conn` commits: one deleter at a time across the cluster.

    Keyed by schema, so two installations sharing a database do not wait on each other.
    """
    deadline = time.monotonic() + max(0.0, wait)
    query = text("SELECT pg_try_advisory_xact_lock("
                 "hashtextextended(current_schema() || '.ucm_backup_archives', 0))")
    while True:
        if conn.execute(query).scalar():
            return
        if time.monotonic() >= deadline:
            raise BackupBusyError(
                f'Another backup operation is in progress ({purpose} could not start)')
        time.sleep(_LOCK_POLL)


def delete_archives(filenames, *, wait: float = 0, purpose: str = 'deleting backups') -> list:
    """Delete the named archives with their chunks; returns the names that were there."""
    archives, chunks = _tables()
    names = list(dict.fromkeys(filenames))
    with _engine().connect() as conn:
        _take_lock(conn, wait, purpose)
        deleted = _delete(conn, archives, chunks, archives.c.filename.in_(names)) if names else []
        conn.commit()
    return deleted


def _delete(conn, archives, chunks, condition) -> list:
    rows = conn.execute(select(archives.c.id, archives.c.filename).where(condition)).all()
    if not rows:
        return []
    ids = [row.id for row in rows]
    conn.execute(delete(chunks).where(chunks.c.archive_id.in_(ids)))
    gone = conn.execute(delete(archives).where(archives.c.id.in_(ids))
                        .returning(archives.c.filename)).scalars().all()
    return list(gone)


def _before_deleting(victims):
    """Test seam: called once retention has chosen what to delete, before it deletes."""


def apply_retention(retention_days: int, *, min_keep: int, max_total_bytes: int,
                    wait: float = 0) -> int:
    """The retention rule of the disk, applied once to the whole store. Returns the count removed.

    Kept whatever their age: the newest archive (each one is proven when it is committed, so
    the newest is the last provable restore point) and the `min_keep` newest. Then the
    oldest go until the store fits `max_total_bytes` (0: no ceiling), the kept ones never.
    """
    if not retention_days or retention_days < 1:
        return 0
    archives, chunks = _tables()
    with _engine().connect() as conn:
        _take_lock(conn, wait, 'backup retention')
        cutoff = _now(conn) - timedelta(days=retention_days)
        rows = conn.execute(select(archives.c.id, archives.c.created_at, archives.c.size)
                            .order_by(archives.c.created_at.desc(), archives.c.id.desc())).all()
        keep = {row.id for row in rows[:max(1, min_keep)]}
        oldest_first = list(reversed(rows))
        victims = [row.id for row in oldest_first
                   if row.id not in keep and row.created_at < cutoff]
        remaining = [row for row in oldest_first if row.id not in set(victims)]
        if max_total_bytes > 0:
            total = sum(int(row.size) for row in remaining)
            for row in remaining:
                if total <= max_total_bytes:
                    break
                if row.id in keep:
                    continue
                victims.append(row.id)
                total -= int(row.size)
            if total > max_total_bytes:
                logger.warning(
                    "Backup retention: the stored archives still take %d MiB, above the %d MiB "
                    "ceiling, because what remains is the last restore point",
                    total // (1024 * 1024), max_total_bytes // (1024 * 1024))
        _before_deleting(victims)
        removed = len(_delete(conn, archives, chunks, archives.c.id.in_(victims))) if victims else 0
        conn.commit()
    if removed:
        logger.info("Backup retention removed %d archive(s) from the database", removed)
    return removed


def _single_byte_range(environ) -> dict:
    """The environ to answer from: a Range other than one byte range is ignored (RFC 9110, 14.2)."""
    from werkzeug.http import parse_range_header

    value = environ.get('HTTP_RANGE')
    if value is None:
        return environ
    parsed = parse_range_header(value)
    if parsed is not None and parsed.units == 'bytes' and len(parsed.ranges) == 1:
        return environ
    return {k: v for k, v in environ.items() if k != 'HTTP_RANGE'}


def download_response(filename: str):
    """A streamed attachment of a stored archive, or None when it is not in the store.

    As on disk: Range (one byte range, 206 or 416), a strong ETag (the SHA-256),
    If-None-Match and If-Range. The body is a file, so closing the response closes its
    connection, iterated or not. ``Repr-Digest`` (RFC 9530) names the whole archive.
    """
    import base64

    from flask import Response, request
    from werkzeug.exceptions import RequestedRangeNotSatisfiable
    from werkzeug.wsgi import wrap_file

    opened = _open(filename)
    if opened is None:
        return None
    reader, row = opened
    size = int(row.size)
    try:
        digest = base64.b64encode(bytes.fromhex(row.sha256)).decode()
        response = Response(
            wrap_file(request.environ, reader, buffer_size=row.chunk_size),
            mimetype='application/octet-stream', direct_passthrough=True, headers={
                'Content-Disposition': f'attachment; filename={filename}',
                'Repr-Digest': f'sha-256=:{digest}:',
            })
        response.content_length = size
        response.last_modified = row.created_at.replace(tzinfo=timezone.utc)
        response.cache_control.no_cache = True
        response.set_etag(row.sha256)
        try:
            return response.make_conditional(_single_byte_range(request.environ),
                                             accept_ranges=True, complete_length=size)
        except RequestedRangeNotSatisfiable:
            reader.close()
            return Response(status=416, headers={'Content-Range': f'bytes */{size}',
                                                 'Accept-Ranges': 'bytes'})
    except Exception:
        reader.close()
        raise
