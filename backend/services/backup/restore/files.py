"""Files a restore writes, staged until the transaction has committed.

The restore wrote the key mirrors and the server's HTTPS pair in the middle
of its database writes, which left two failures with nothing to repair them:
a transaction that rolled back afterwards kept the files of a restore that
never happened, and a file that could not be written left a database already
partly committed.

Content is staged in a private directory while the transaction can still
fail, and no destination is touched before the commit. Publication is then
one atomic replace per file, and what each destination held is kept until
the last one is published: a failure halfway through puts back what the
earlier replaces overwrote, rather than leaving the instance with half of a
restore's files.
"""
import logging
import os
import shutil
import tempfile
from pathlib import Path
from typing import List, Optional

from ..storage import _fsync_directory

logger = logging.getLogger(__name__)

_STAGING_PREFIX = 'ucm_restore_files_'
_PUBLISH_PREFIX = '.ucm_restore_'


def _atomic_replace(destination: Path, data: bytes, mode: int) -> None:
    """Put ``data`` at ``destination`` whole, or leave it as it was.

    The temporary file is written in the destination's own directory, so the
    rename that publishes it stays on one filesystem and cannot degrade into
    a copy; it is fsynced and chmoded before the rename, so the destination
    is never readable in a half-written or world-readable state.
    """
    temp_path = None
    try:
        fd, temp_name = tempfile.mkstemp(
            dir=str(destination.parent), prefix=_PUBLISH_PREFIX, suffix='.tmp')
        temp_path = Path(temp_name)
        with os.fdopen(fd, 'wb') as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temp_path, mode)
        os.replace(temp_path, destination)
        temp_path = None
    finally:
        if temp_path is not None:
            try:
                temp_path.unlink()
            except OSError:
                logger.warning(
                    "Could not remove temporary restore file %s", temp_path)


class _Staged:
    """One destination, its staged content, and what it held before.

    The previous content is read at publication time rather than at staging
    time: between the two, the transaction has run, and only what is on disk
    when the replace happens is what a compensation has to put back.
    """

    __slots__ = ('destination', 'staged_path', 'mode', 'remove',
                 'existed', 'previous_data', 'previous_mode', 'published')

    def __init__(self, destination: Path, staged_path: Optional[Path], mode: int,
                 remove: bool = False):
        self.destination = destination
        self.staged_path = staged_path
        self.mode = mode
        # Published as a removal: the destination goes, and comes back on compensation
        self.remove = remove
        self.existed = False
        self.previous_data = b''
        self.previous_mode = mode
        self.published = False


class StagedFiles:
    """The files of a restore, held back until the database says so.

    Used as a context manager, the staging directory is dropped when the
    block raises, so a restore that failed leaves nothing behind. A block
    that succeeds keeps it, because publishing is the caller's decision and
    must follow the commit; ``publish`` and ``discard`` both drop it.
    """

    def __init__(self, base_dir=None, prefix: str = _STAGING_PREFIX):
        self._base_dir = Path(base_dir) if base_dir is not None else None
        self._prefix = prefix
        self._staging_dir: Optional[Path] = None
        self._entries: List[_Staged] = []

    # -- staging ----------------------------------------------------------

    @property
    def staging_dir(self) -> Optional[Path]:
        """Where content is held, or None while nothing has been staged."""
        return self._staging_dir

    @property
    def destinations(self) -> List[Path]:
        """The destinations a publication would write, in staging order."""
        return [entry.destination for entry in self._entries]

    def _staging(self) -> Path:
        """Create the staging directory on first use, readable by nobody else.

        Staged content is the archive's key material in the clear, so the
        directory is created private and checked: a restore that stages
        nothing never creates it at all.
        """
        if self._staging_dir is None:
            if self._base_dir is not None:
                self._base_dir.mkdir(parents=True, exist_ok=True)
            self._staging_dir = Path(tempfile.mkdtemp(
                prefix=self._prefix,
                dir=str(self._base_dir) if self._base_dir else None))
            os.chmod(self._staging_dir, 0o700)
        return self._staging_dir

    def stage(self, destination, data: bytes, *, mode: int = 0o600) -> Path:
        """Hold ``data`` for ``destination`` without touching it yet.

        Staging the same destination twice replaces the earlier content in
        place: publishing both would make the second replace record the
        first one's output as the previous content, and a compensation would
        then restore a file this restore had itself written.
        """
        if isinstance(data, (bytearray, memoryview)):
            data = bytes(data)
        if not isinstance(data, bytes):
            raise TypeError("Staged content must be bytes")

        destination = Path(destination)
        staging = self._staging()

        for entry in self._entries:
            if entry.destination == destination:
                if entry.staged_path is None:
                    entry.staged_path = staging / f"{self._entries.index(entry):04d}_{destination.name}"
                entry.mode, entry.remove = mode, False
                _write_private(entry.staged_path, data, mode)
                return entry.staged_path

        staged_path = staging / f"{len(self._entries):04d}_{destination.name}"
        _write_private(staged_path, data, mode)
        self._entries.append(_Staged(destination, staged_path, mode))
        return staged_path

    def stage_removal(self, destination) -> None:
        """Remove ``destination`` at publication, or leave it if the restore fails.

        Replaces whatever was staged for it: a file the restore no longer wants.
        """
        destination = Path(destination)
        for entry in self._entries:
            if entry.destination == destination:
                entry.remove = True
                return
        self._entries.append(_Staged(destination, None, 0o600, remove=True))

    # -- publication ------------------------------------------------------

    def publish(self) -> List[Path]:
        """Publish every staged file, or leave the destinations as they were.

        Called with the database work done but not yet committed: each
        destination is read before it is replaced, so a failure on any file
        undoes the replaces that already happened, and the caller rolls the
        database back. What the staging holds is kept until `discard()`, so a
        commit that fails afterwards can still call `unpublish()`.
        """
        published: List[Path] = []
        try:
            for entry in self._entries:
                self._capture_previous(entry)
                self._publish(entry)
                published.append(entry.destination)
        except Exception:
            failed = (self._entries[len(published)].destination
                      if len(published) < len(self._entries) else None)
            logger.error(
                "Restore: publishing %s failed after %d file(s); restoring "
                "their previous content", failed, len(published))
            self._compensate()
            raise

        return published

    def _capture_previous(self, entry: _Staged) -> None:
        """Read what the destination holds, before anything overwrites it.

        A destination that cannot be read is a destination that could not be
        put back, so the read failure stops the publication here instead of
        producing a file nothing can undo.
        """
        try:
            entry.previous_data = entry.destination.read_bytes()
        except FileNotFoundError:
            entry.existed = False
            entry.previous_data = b''
            entry.previous_mode = entry.mode
            return
        entry.existed = True
        entry.previous_mode = os.stat(entry.destination).st_mode & 0o777

    def _publish(self, entry: _Staged) -> None:
        directory = entry.destination.parent
        if entry.remove:
            if entry.existed:
                entry.destination.unlink()
                entry.published = True
                _fsync_directory(directory)
            return
        directory.mkdir(parents=True, exist_ok=True)
        data = entry.staged_path.read_bytes()

        _atomic_replace(entry.destination, data, entry.mode)
        # Recorded before the directory fsync: the rename has already taken
        # effect, so a failing fsync must still compensate this file.
        entry.published = True
        _fsync_directory(directory)

    def unpublish(self) -> None:
        """Undo a successful publication.

        The database commit happens after the files are in place, so a commit
        that fails leaves files describing a restore that did not happen. This
        puts the destinations back to what they held.
        """
        self._compensate()

    def _compensate(self) -> None:
        """Put the published destinations back, newest publication first.

        Compensation is best effort by necessity: it runs because something
        on this filesystem already failed. What it cannot put back is logged
        with the path, since at that point only an administrator can.
        """
        for entry in reversed(self._entries):
            if not entry.published:
                continue
            try:
                if entry.existed:
                    _atomic_replace(
                        entry.destination, entry.previous_data,
                        entry.previous_mode)
                else:
                    entry.destination.unlink(missing_ok=True)
                _fsync_directory(entry.destination.parent)
                entry.published = False
            except OSError:
                logger.exception(
                    "Restore: could not restore the previous content of %s",
                    entry.destination)

    # -- disposal ---------------------------------------------------------

    def discard(self) -> None:
        """Drop the staged content without publishing any of it.

        Called when the transaction failed, and after a successful
        publication: staged content is key material in the clear and has no
        reason to outlive either outcome.
        """
        staging, self._staging_dir = self._staging_dir, None
        self._entries = []
        if staging is None:
            return
        try:
            shutil.rmtree(staging)
        except OSError:
            logger.exception("Could not remove staged restore files %s", staging)

    # -- context manager --------------------------------------------------

    def __enter__(self) -> 'StagedFiles':
        return self

    def __exit__(self, exc_type, exc, tb) -> bool:
        if exc_type is not None:
            self.discard()
        return False


def _write_private(path: Path, data: bytes, mode: int) -> None:
    """Write staged content at the mode its destination will carry.

    Staged key material must never be readable more widely than the file it
    will become, not even for the life of a restore.
    """
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, mode)
    try:
        os.fchmod(fd, mode)
        with os.fdopen(fd, 'wb') as handle:
            fd = -1
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
    finally:
        if fd >= 0:
            os.close(fd)
