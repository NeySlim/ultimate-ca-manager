"""Writing a backup archive to disk, and proving what was written.

Structure cannot prove that an archive is restorable: the header of a
truncated or half-overwritten container still parses, and nothing short of the
backup password can check the payload. What can be proven is that the bytes on
disk are the bytes the service produced, so every archive written here is read
back and recorded with its size and SHA-256. Retention protects the most
recent file that still matches its record.
"""
from contextlib import contextmanager
import errno
import hashlib
import json
import logging
import os
import tempfile
from pathlib import Path
from uuid import uuid4

import werkzeug.utils

from config.settings import Config
from utils.datetime_utils import utc_isoformat, utc_now

from .errors import BackupValidationError

logger = logging.getLogger(__name__)

CATALOG_NAME = '.ucm_backup_catalog.json'
_CATALOG_LOCK_NAME = '.ucm_backup_catalog.lock'
_CATALOG_VERSION = 1
_READ_CHUNK = 1024 * 1024
_UNSUPPORTED_DIRECTORY_FSYNC_ERRNOS = frozenset(filter(None, (
    errno.EINVAL,
    getattr(errno, 'ENOTSUP', None),
    getattr(errno, 'EOPNOTSUPP', None),
)))

# The extensions this service writes, and the only ones it will serve back.
ALLOWED_ARCHIVE_EXTENSIONS = ('.ucmbkp', '.json.enc')

# A name collision means a UUID collided; retrying costs nothing and publishing
# never overwrites, so the loop is bounded rather than infinite.
_NAME_ATTEMPTS = 5


def _fsync_directory(path: Path) -> bool:
    """Sync directory entries when the backing filesystem supports it."""
    flags = os.O_RDONLY | getattr(os, 'O_DIRECTORY', 0)
    fd = None
    try:
        fd = os.open(path, flags)
        os.fsync(fd)
    except OSError as exc:
        if exc.errno not in _UNSUPPORTED_DIRECTORY_FSYNC_ERRNOS:
            raise
        logger.warning(
            "Directory fsync is unsupported for %s; backup crash durability "
            "depends on the backing filesystem", path)
        return False
    finally:
        if fd is not None:
            os.close(fd)
    return True


@contextmanager
def _catalog_lock(backup_dir: Path):
    """Serialize the catalogue read-modify-write across workers."""
    import fcntl

    backup_dir = Path(backup_dir)
    lock_path = backup_dir / _CATALOG_LOCK_NAME
    fd = os.open(lock_path, os.O_CREAT | os.O_RDWR, 0o600)
    locked = False
    try:
        os.chmod(lock_path, 0o600)
        fcntl.flock(fd, fcntl.LOCK_EX)
        locked = True
        yield
    finally:
        if locked:
            fcntl.flock(fd, fcntl.LOCK_UN)
        os.close(fd)


def write_archive_atomically(backup_dir: Path, filename: str, data: bytes) -> Path:
    """Write an archive whole, or not at all.

    The temporary file is fsynced before it is published, and publication uses
    a link, which fails rather than overwrite an existing archive.
    """
    backup_dir = Path(backup_dir)
    backup_dir.mkdir(parents=True, exist_ok=True)

    temp_path = None
    destination = backup_dir / filename
    published = False
    try:
        fd, temp_path = tempfile.mkstemp(
            dir=str(backup_dir), prefix='.ucm_backup_', suffix='.tmp')
        with os.fdopen(fd, 'wb') as temp_file:
            temp_file.write(data)
            temp_file.flush()
            os.fsync(temp_file.fileno())
        os.chmod(temp_path, 0o600)

        os.link(temp_path, destination)
        published = True
        os.unlink(temp_path)
        temp_path = None
        _fsync_directory(backup_dir)
        return destination
    except Exception:
        if published:
            try:
                destination.unlink(missing_ok=True)
                _fsync_directory(backup_dir)
            except OSError:
                logger.exception(
                    "Could not roll back backup publication %s", destination)
        raise
    finally:
        if temp_path:
            try:
                os.unlink(temp_path)
            except OSError:
                logger.warning("Could not remove temporary backup %s", temp_path)


def digest_of(path) -> tuple:
    """Return (size, sha256) read back from disk."""
    digest = hashlib.sha256()
    size = 0
    with open(path, 'rb') as fh:
        while True:
            chunk = fh.read(_READ_CHUNK)
            if not chunk:
                break
            size += len(chunk)
            digest.update(chunk)
    return size, digest.hexdigest()


def catalog_path(backup_dir) -> Path:
    return Path(backup_dir) / CATALOG_NAME


def read_catalog(backup_dir) -> dict:
    """Return the recorded archives, keyed by filename."""
    try:
        with open(catalog_path(backup_dir), 'r', encoding='utf-8') as fh:
            data = json.load(fh)
    except (OSError, ValueError):
        return {}
    archives = data.get('archives') if isinstance(data, dict) else None
    return archives if isinstance(archives, dict) else {}


def _write_catalog(backup_dir, archives: dict) -> None:
    backup_dir = Path(backup_dir)
    payload = json.dumps(
        {'version': _CATALOG_VERSION, 'archives': archives},
        indent=2, sort_keys=True).encode()

    temp_path = None
    try:
        fd, temp_path = tempfile.mkstemp(
            dir=str(backup_dir), prefix='.ucm_catalog_', suffix='.tmp')
        with os.fdopen(fd, 'wb') as fh:
            fh.write(payload)
            fh.flush()
            os.fsync(fh.fileno())
        os.chmod(temp_path, 0o600)
        os.replace(temp_path, catalog_path(backup_dir))
        temp_path = None
        _fsync_directory(backup_dir)
    finally:
        if temp_path:
            try:
                os.unlink(temp_path)
            except OSError:
                pass


def _remove_failed_archive(path: Path) -> None:
    try:
        path.unlink(missing_ok=True)
        _fsync_directory(path.parent)
    except OSError:
        logger.exception("Could not remove failed backup %s", path)


def validate_and_record(path, expected: bytes) -> dict:
    """Read the archive back and record it, or remove it."""
    path = Path(path)
    try:
        size, sha256 = digest_of(path)
        if size != len(expected) or sha256 != hashlib.sha256(expected).hexdigest():
            raise BackupValidationError(
                f"The backup {path.name} did not read back as it was written "
                f"({size} bytes on disk for {len(expected)} written)"
            )

        entry = {
            'size': size,
            'sha256': sha256,
            'recorded_at': utc_isoformat(utc_now()),
        }
        backup_dir = path.parent
        with _catalog_lock(backup_dir):
            archives = read_catalog(backup_dir)
            archives[path.name] = entry
            # Drop records of archives that are gone, so the catalogue cannot
            # grow without bound or vouch for a name a new file might reuse.
            for name in list(archives):
                if not (backup_dir / name).is_file():
                    del archives[name]
            _write_catalog(backup_dir, archives)
        return entry
    except BackupValidationError:
        _remove_failed_archive(path)
        raise
    except OSError as exc:
        _remove_failed_archive(path)
        raise BackupValidationError(
            f"The backup {path.name} could not be validated after writing"
        ) from exc


def publish_validated_archive(
        backup_dir: Path, filename: str, data: bytes) -> Path:
    """Publish an archive only if its bytes can be durably validated."""
    from .locking import backup_operation_lock

    # Safe on its own: the lock is reentrant, so a caller already holding it
    # (the scheduled run, a route creating an archive) pays nothing, and one
    # that forgot is still serialised against retention and deletions.
    with backup_operation_lock(timeout=30, purpose='publishing an archive'):
        return _publish_validated_archive(backup_dir, filename, data)


def _publish_validated_archive(backup_dir, filename: str, data: bytes):
    path = write_archive_atomically(backup_dir, filename, data)
    try:
        validate_and_record(path, data)
    except Exception:
        _remove_failed_archive(path)
        raise
    return path


def backup_directory() -> Path:
    """The configured archive directory, resolved.

    Read on every call: the directory is a setting, and a route that captured
    it at import time kept writing to the previous one.
    """
    return Path(Config.BACKUP_DIR).resolve()


def is_archive_name(filename: str) -> bool:
    """Whether a name carries an extension this service writes."""
    return bool(filename) and filename.endswith(ALLOWED_ARCHIVE_EXTENSIONS)


def resolve_archive(raw_filename, backup_dir=None) -> tuple:
    """Resolve a requested archive name to a path in the archive directory.

    The one implementation for every route that takes an archive name. The two
    families of backup routes used to read the same name two ways: one refused
    traversal, an extension it never writes, a name ``secure_filename()`` had
    to change and a symlink; the other took whatever ``secure_filename()``
    turned the request into, as long as the result stayed under the directory.
    Only the strict reading is left.

    Returns ``(resolved path, filename)``. Raises ``ValueError`` when the name
    is not one this service would have written, and ``PermissionError`` when
    it points outside the directory or at a symlink; callers map those to 400
    and 403.
    """
    if not isinstance(raw_filename, str):
        raise ValueError("Invalid backup filename")

    filename = werkzeug.utils.secure_filename(raw_filename)

    # A name secure_filename() had to change is not the name that was asked
    # for. Serving the valid file it happens to produce is how a traversal
    # attempt turns into a successful download.
    if not filename or filename != raw_filename:
        raise ValueError("Invalid backup filename")

    if not is_archive_name(filename):
        raise ValueError("Invalid backup filename")

    directory = (Path(backup_dir).resolve() if backup_dir is not None
                 else backup_directory())
    candidate = directory / filename

    # Backups are normal files written by this service, never symlinks.
    if candidate.is_symlink():
        raise PermissionError("Symlinked backup files are not permitted")

    try:
        resolved = candidate.resolve()
        if not resolved.is_relative_to(directory):
            raise PermissionError("Backup path is outside the backup directory")
    except (ValueError, RuntimeError) as exc:
        raise ValueError("Invalid backup path") from exc

    return resolved, filename


def new_archive_filename() -> str:
    """A collision-resistant name for a new archive.

    Microseconds and a UUID fragment: a name to the second let two backups
    taken in the same second fight over one file.
    """
    return (f"ucm_backup_{utc_now().strftime('%Y%m%d_%H%M%S_%f')}"
            f"_{uuid4().hex[:12]}.ucmbkp")


# Room for the multipart envelope around the archive: the password, the mode
# and the boundaries.
RESTORE_FORM_MARGIN = 1024 * 1024


def restore_upload_limit() -> int:
    """Bytes of archive a restore route accepts (`BACKUP_MAX_UPLOAD_MB`)."""
    return int(Config.BACKUP_MAX_UPLOAD_MB) * 1024 * 1024


def restore_limit_warning(size: int, payload_size: int = 0, containers: int = 0):
    """What to tell whoever created an archive no restore reads, or None.

    Checked against both ceilings: the archive itself, and its decompressed payload.
    """
    from . import container

    limit = restore_upload_limit()
    if size > limit:
        return (f"This archive is {size / (1024 * 1024):.1f} MB, more than the "
                f"{limit // (1024 * 1024)} MB a restore accepts: raise BACKUP_MAX_UPLOAD_MB "
                "on the server that will restore it.")
    ceiling = container.max_plaintext_bytes()
    if payload_size > ceiling:
        return (f"This archive decompresses to {payload_size / (1024 * 1024):.1f} MB, more "
                f"than the {ceiling // (1024 * 1024)} MB a restore reads "
                f"({container.PLAINTEXT_PER_ARCHIVE_BYTE} times BACKUP_MAX_UPLOAD_MB): raise "
                "BACKUP_MAX_UPLOAD_MB on the server that will restore it.")
    objects = container.max_json_containers()
    if containers > objects:
        return (f"This archive holds {containers} JSON objects, more than the {objects} a "
                "restore reads: raise BACKUP_MAX_UPLOAD_MB on the server that will restore it.")
    return None


# Seconds a manual backup waits for the backup lock before it is refused.
EXPORT_LOCK_WAIT = 30


def export_archive(service, password: str, *, kdf=None, timeout=None) -> tuple:
    """Export and publish one archive under the backup lock. Returns ``(bytes, path, filename)``.

    The export runs inside the lock too: a restore holds it until it commits, so
    an archive never reads half of a restore.
    """
    from .locking import backup_operation_lock

    wait = EXPORT_LOCK_WAIT if timeout is None else timeout
    with backup_operation_lock(timeout=wait, purpose='creating a backup'):
        data = service.create_backup(password, kdf=kdf)
        path, filename = _create_archive(data)
    return data, path, filename


def create_archive(data: bytes, backup_dir=None) -> tuple:
    """Publish archive bytes under a new name, validated.

    The one implementation behind every "create a backup" route: same
    directory, same naming, same proof that what is on disk is what was
    produced. Returns ``(path, filename)``, and raises ``FileExistsError``
    when no unused name could be allocated.

    Held under the shared backup lock, so a manual backup, the scheduled one
    and retention cannot interleave: they write and delete in the same
    directory, and the catalogue that vouches for them is one file.
    """
    from .locking import backup_operation_lock

    with backup_operation_lock(timeout=30, purpose='creating a backup'):
        return _create_archive(data, backup_dir)


def _create_archive(data: bytes, backup_dir=None) -> tuple:
    directory = Path(backup_dir) if backup_dir is not None else backup_directory()
    for _ in range(_NAME_ATTEMPTS):
        filename = new_archive_filename()
        try:
            return publish_validated_archive(directory, filename, data), filename
        except FileExistsError:
            continue

    logger.error("Could not allocate a unique backup filename in %d attempts",
                 _NAME_ATTEMPTS)
    raise FileExistsError("Could not allocate a unique backup filename")


def matches_record(path, entry: dict) -> bool:
    """Whether the file on disk still is the archive that was recorded."""
    if not isinstance(entry, dict):
        return False
    try:
        if os.path.getsize(path) != entry.get('size'):
            return False
        _size, sha256 = digest_of(path)
    except OSError:
        return False
    return sha256 == entry.get('sha256')


def newest_validated(paths) -> object:
    """Return the most recent archive that still matches its record.

    Files are checked newest first and hashing stops at the first match, so a
    directory of archives is not read end to end on every retention run.
    """
    if not paths:
        return None
    archives = read_catalog(Path(list(paths)[0]).parent)
    if not archives:
        return None
    for path in _newest_first(paths):
        entry = archives.get(Path(path).name)
        if entry and matches_record(path, entry):
            return path
    return None


def tampered(paths) -> list:
    """Archives whose record exists and no longer matches what is on disk.

    Proven to be something other than what was written, so nothing should
    protect them: keeping "the two most recent" is protection against losing a
    restore point, not against losing a file.
    """
    if not paths:
        return []
    archives = read_catalog(Path(list(paths)[0]).parent)
    if not archives:
        return []
    found = []
    for path in paths:
        entry = archives.get(Path(path).name)
        if entry and not matches_record(path, entry):
            found.append(path)
    return found


def unrecorded(paths) -> list:
    """Archives with no validation record, newest first.

    Written before validation records existed, or by a path that does not
    write one. Nothing can be proven about them either way.
    """
    if not paths:
        return []
    archives = read_catalog(Path(list(paths)[0]).parent)
    return [p for p in _newest_first(paths) if Path(p).name not in archives]


def _newest_first(paths) -> list:
    def mtime(path):
        try:
            return os.stat(path).st_mtime
        except OSError:
            return 0.0
    return sorted(paths, key=mtime, reverse=True)
