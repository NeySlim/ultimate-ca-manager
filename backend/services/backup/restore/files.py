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

Invariant: a token's publication row is erased only once every kept directory
holding a journal of that token is gone; while a journal exists, the row tells
the truth about whether its restore committed.
"""
import errno
import fcntl
import json
import logging
import os
import re
import shutil
import tempfile
import uuid
from pathlib import Path
from typing import Dict, List, Optional

from ..storage import _fsync_directory

logger = logging.getLogger(__name__)

_STAGING_PREFIX = 'ucm_restore_files_'
_PUBLISH_PREFIX = '.ucm_restore_'
_KEPT_PREFIX = '.ucm_restore_kept_'
_JOURNAL = 'journal.json'
# In a staging created without a lock: who owns it
_OWNER = '.owner'
_PREVIOUS = re.compile(r'previous_[0-9]{6}')
# A system_config row per restore, written in its transaction: present iff it committed
PUBLICATION_PREFIX = 'restore_publication_'


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

    The previous content is kept at publication time rather than at staging
    time: between the two, the transaction has run, and only what is on disk
    when the replace happens is what a compensation has to put back. It is
    kept as a file beside the destination, never in memory.
    """

    __slots__ = ('destination', 'staged_path', 'mode', 'remove',
                 'existed', 'previous_path', 'previous_mode', 'published')

    def __init__(self, destination: Path, staged_path: Optional[Path], mode: int,
                 remove: bool = False):
        self.destination = destination
        self.staged_path = staged_path
        self.mode = mode
        # Published as a removal: the destination goes, and comes back on compensation
        self.remove = remove
        self.existed = False
        self.previous_path: Optional[Path] = None
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
        # Held on the staging directory for its life: a sweep never removes a live one
        self._staging_lock: Optional[int] = None
        self._entries: List[_Staged] = []
        # Destination to its position in _entries: one lookup per staged file
        self._index: Dict[Path, int] = {}
        # Destination directory to its private directory of kept previous contents
        self._kept_dirs: Dict[Path, Path] = {}
        # Names this restore in the journals and in its publication row
        self.token = uuid.uuid4().hex

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
            for _attempt in range(3):
                staging = Path(tempfile.mkdtemp(
                    prefix=self._prefix,
                    dir=str(self._base_dir) if self._base_dir else None))
                os.chmod(staging, 0o700)
                try:
                    fd = os.open(staging, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
                except OSError:
                    shutil.rmtree(staging, ignore_errors=True)
                    raise
                try:
                    fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    # Swept by another instance before the lock was taken: start again
                    if os.fstat(fd).st_nlink > 0:
                        self._staging_dir, self._staging_lock = staging, fd
                        break
                except BlockingIOError:
                    pass
                except OSError as exc:
                    # No lock on this filesystem (ENOLCK): the staging names its live owner instead
                    try:
                        _write_private(staging / _OWNER, json.dumps(_owner_record()).encode(), 0o600)
                    except BaseException:
                        os.close(fd)
                        shutil.rmtree(staging, ignore_errors=True)
                        raise
                    logger.warning("Restore staging %s holds no lock (%s); a sweep removes it "
                                   "only once its owner process is gone", staging, exc)
                    self._staging_dir, self._staging_lock = staging, fd
                    break
                except BaseException:
                    os.close(fd)
                    shutil.rmtree(staging, ignore_errors=True)
                    raise
                os.close(fd)
            else:
                raise OSError(errno.EAGAIN, "Could not hold a restore staging directory")
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

        position = self._index.get(destination)
        if position is not None:
            entry = self._entries[position]
            if entry.staged_path is None:
                entry.staged_path = staging / f"{position:04d}_{destination.name}"
            entry.mode, entry.remove = mode, False
            _write_private(entry.staged_path, data, mode)
            return entry.staged_path

        staged_path = staging / f"{len(self._entries):04d}_{destination.name}"
        _write_private(staged_path, data, mode)
        self._index[destination] = len(self._entries)
        self._entries.append(_Staged(destination, staged_path, mode))
        return staged_path

    def stage_removal(self, destination) -> None:
        """Remove ``destination`` at publication, or leave it if the restore fails.

        Replaces whatever was staged for it: a file the restore no longer wants.
        """
        destination = Path(destination)
        position = self._index.get(destination)
        if position is not None:
            self._entries[position].remove = True
            return
        self._index[destination] = len(self._entries)
        self._entries.append(_Staged(destination, None, 0o600, remove=True))

    # -- publication ------------------------------------------------------

    def publish(self) -> List[Path]:
        """Publish every staged file, or leave the destinations as they were.

        Called with the database work done but not yet committed: each
        destination is kept before it is replaced, so a failure on any file
        undoes the replaces that already happened, and the caller rolls the
        database back. What the staging holds is kept until `discard()`, so a
        commit that fails afterwards can still call `unpublish()`.
        """
        published: List[Path] = []
        directories: Dict[Path, None] = {}
        failed = None
        try:
            # Journal, then every capture, then their directories synced, then the first
            # rename: no destination changes before what it held is durable beside it
            self._write_journals()
            for position, entry in enumerate(self._entries):
                failed = entry.destination
                self._capture_previous(entry, position)
            for kept_dir in self._kept_dirs.values():
                _fsync_directory(kept_dir)
            for entry in self._entries:
                failed = entry.destination
                if self._publish(entry):
                    directories[entry.destination.parent] = None
                published.append(entry.destination)
            failed = None
            # Each directory once, after its renames: none is durable before this returns
            for directory in directories:
                _fsync_directory(directory)
        except Exception:
            logger.error(
                "Restore: publishing %s failed after %d file(s); restoring "
                "their previous content", failed, len(published))
            self._compensate()
            raise

        return published

    def _kept_dir(self, directory: Path) -> Path:
        """A private directory inside ``directory``, for its previous contents.

        Always inside the destination's own directory, where a restart finds it
        and where a hard link never crosses a mount: one that cannot be created
        there stops the publication before anything is replaced.
        """
        kept_dir = self._kept_dirs.get(directory)
        if kept_dir is None:
            directory.mkdir(parents=True, exist_ok=True)
            kept_dir = Path(tempfile.mkdtemp(prefix=_KEPT_PREFIX, dir=str(directory)))
            os.chmod(kept_dir, 0o700)
            self._kept_dirs[directory] = kept_dir
        return kept_dir

    def _write_journals(self) -> None:
        """Before any replace, each directory's kept directory says what it will put back.

        A restore killed before its commit is undone from these at the next start
        (`sweep_kept_previous_contents`); written and synced first, so no
        destination changes that a journal does not name.
        """
        by_directory: Dict[Path, list] = {}
        for position, entry in enumerate(self._entries):
            try:
                info = os.stat(entry.destination)
            except FileNotFoundError:
                info = None
            by_directory.setdefault(entry.destination.parent, []).append({
                'name': entry.destination.name, 'previous': f"previous_{position:06d}",
                'existed': info is not None,
                'mode': (info.st_mode & 0o777) if info is not None else None})
        for directory, entries in by_directory.items():
            kept_dir = self._kept_dir(directory)
            fd = os.open(kept_dir / _JOURNAL, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(fd, 'w') as handle:
                json.dump({'token': self.token, 'entries': entries}, handle)
                handle.flush()
                os.fsync(handle.fileno())
            _fsync_directory(kept_dir)
            _fsync_directory(directory)

    def _capture_previous(self, entry: _Staged, position: int) -> None:
        """Keep what the destination holds, before anything overwrites it.

        A hard link beside the destination, a copy when the file cannot be
        linked. A destination that cannot be kept is a destination that could
        not be put back, so the failure stops the publication here instead of
        producing a file nothing can undo.
        """
        try:
            info = os.stat(entry.destination)
        except FileNotFoundError:
            entry.existed = False
            entry.previous_path = None
            entry.previous_mode = entry.mode
            return
        kept = self._kept_dir(entry.destination.parent) / f"previous_{position:06d}"
        try:
            os.link(entry.destination, kept)
        except OSError:
            _copy_private(entry.destination, kept)
        entry.existed = True
        entry.previous_path = kept
        entry.previous_mode = info.st_mode & 0o777

    def _publish(self, entry: _Staged) -> bool:
        """Replace or remove one destination; whether its directory changed."""
        if entry.remove:
            if entry.existed:
                entry.destination.unlink()
                entry.published = True
                return True
            return False
        entry.destination.parent.mkdir(parents=True, exist_ok=True)
        data = entry.staged_path.read_bytes()

        _atomic_replace(entry.destination, data, entry.mode)
        # Set before the directories are fsynced at the end of publish(): the rename
        # has already taken effect, so a failing fsync must still compensate this file.
        entry.published = True
        return True

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
                    _put_back(entry.previous_path, entry.destination, entry.previous_mode)
                else:
                    entry.destination.unlink(missing_ok=True)
                _fsync_directory(entry.destination.parent)
                entry.published = False
            except OSError:
                logger.exception(
                    "Restore: could not restore the previous content of %s",
                    entry.destination)

    # -- disposal ---------------------------------------------------------

    def discard(self) -> List[Path]:
        """Drop the staged content without publishing any of it; return the kept
        directories still on disk, whose journals still need the publication row.

        Called when the transaction failed, and after a successful
        publication: staged content is key material in the clear and has no
        reason to outlive either outcome.
        """
        staging, self._staging_dir = self._staging_dir, None
        staging_lock, self._staging_lock = self._staging_lock, None
        kept_dirs, self._kept_dirs = self._kept_dirs, {}
        self._entries = []
        self._index = {}
        left: List[Path] = []
        for directory in dict.fromkeys([*kept_dirs.values(), staging]):
            if directory is None:
                continue
            try:
                shutil.rmtree(directory)
            except OSError:
                logger.exception("Could not remove staged restore files %s", directory)
            if directory is not staging and os.path.lexists(directory):
                left.append(directory)
        if staging_lock is not None:
            os.close(staging_lock)
        return left

    # -- context manager --------------------------------------------------

    def __enter__(self) -> 'StagedFiles':
        return self

    def __exit__(self, exc_type, exc, tb) -> bool:
        if exc_type is not None:
            self.discard()
        return False


def _kept_parents() -> List[Path]:
    """The directories a restore publishes into, where its kept directories live."""
    from config.settings import Config
    parents = [Config.CA_DIR, Config.CERT_DIR, Config.PRIVATE_DIR,
               Path(Config.HTTPS_CERT_PATH).parent, Path(Config.HTTPS_KEY_PATH).parent]
    return list(dict.fromkeys(Path(parent) for parent in parents))


def record_publication(token: str) -> None:
    """In the restore's transaction: the row that tells a restart this restore committed."""
    from models import SystemConfig, db
    db.session.add(SystemConfig(key=PUBLICATION_PREFIX + token, value='committed',
                                description='A restore publishing its files'))
    db.session.flush()


def forget_publication(token: str) -> None:
    """Once the restore's kept directories are all gone: its row goes too."""
    from models import SystemConfig, db
    try:
        SystemConfig.query.filter_by(key=PUBLICATION_PREFIX + token).delete()
        db.session.commit()
    except Exception as exc:
        db.session.rollback()
        logger.warning("Restore: its publication record was not removed: %s", exc)


def _read_journal(kept_dir: str) -> Optional[dict]:
    """The journal a kept directory holds, or None when publication never began there."""
    try:
        fd = os.open(os.path.join(kept_dir, _JOURNAL), os.O_RDONLY | getattr(os, 'O_NOFOLLOW', 0))
    except FileNotFoundError:
        return None
    try:
        with os.fdopen(fd, 'r') as handle:
            journal = json.load(handle)
    except ValueError:
        return None    # cut short while written: nothing was replaced after it
    if not (isinstance(journal, dict) and isinstance(journal.get('token'), str)
            and isinstance(journal.get('entries'), list)):
        return None
    return journal


def _committed_tokens(tokens) -> set:
    from models import SystemConfig
    keys = [PUBLICATION_PREFIX + token for token in tokens]
    rows = SystemConfig.query.filter(SystemConfig.key.in_(keys)).all() if keys else []
    return {row.key[len(PUBLICATION_PREFIX):] for row in rows}


def _put_back_journal(kept_dir: str, journal: dict) -> None:
    """Undo an uncommitted publication in the directory that holds `kept_dir`."""
    parent = Path(kept_dir).parent
    for item in journal['entries']:
        name, previous = item.get('name'), item.get('previous')
        # Only a plain name in this very directory, and a kept file this module named
        if (not isinstance(name, str) or not name or name in ('.', '..') or '/' in name
                or name.startswith(_KEPT_PREFIX) or not isinstance(previous, str)
                or not _PREVIOUS.fullmatch(previous)):
            continue
        destination = parent / name
        kept = Path(kept_dir) / previous
        if item.get('existed'):
            if os.path.lexists(kept):    # kept before its replace; absent, it was never touched
                mode = item.get('mode')
                _put_back(kept, destination, mode if isinstance(mode, int) else 0o600)
        else:
            destination.unlink(missing_ok=True)
    _fsync_directory(parent)


class InterruptedRestorePending(RuntimeError):
    """A journal of an earlier restore is still on disk: a new restore would be undone by it."""


UNSETTLED_MESSAGE = ("An interrupted restore could not be settled: nothing was restored. "
                     "See the server log.")


def _find_kept_directories() -> list:
    """Every kept directory with its journal (None when it holds none readable)."""
    found = []
    for parent in _kept_parents():
        if not parent.is_dir():
            continue
        for entry in os.scandir(parent):
            # Never a link: its target's journal would name files elsewhere
            if entry.name.startswith(_KEPT_PREFIX) and entry.is_dir(follow_symlinks=False):
                found.append((entry.path, _read_journal(entry.path)))
    return found


def settle_interrupted_restores() -> None:
    """Before a restore stages anything, under the lock it holds: an earlier journal left
    unsettled would be replayed at the next start over the files this restore publishes,
    so it is settled now, as a start would, or the restore is refused."""
    if not _find_kept_directories():
        return    # the usual case: nothing to settle, nothing touched
    sweep_kept_previous_contents()
    found = [(path, journal) for path, journal in _find_kept_directories() if journal is not None]
    try:
        committed = _committed_tokens({journal['token'] for _, journal in found})
    except Exception:
        committed = set()
    # A committed journal only drops its kept copies: it is never replayed over this restore
    left = [path for path, journal in found if journal['token'] not in committed]
    if left:
        logger.error("Restore refused: interrupted restores could not be settled, remove or "
                     "repair %s and restart", ', '.join(left))
        raise InterruptedRestorePending(UNSETTLED_MESSAGE)


def sweep_kept_previous_contents() -> List[Path]:
    """Settle the kept directories of restores killed before `discard()`; return them.

    Committed (its publication row exists): the kept contents are dropped.
    Not committed: the destinations get them back, matching the rolled-back
    database. A database that cannot be read settles nothing. Closed rule: they
    are created under the backup lock, so only while this thread holds it by
    flock is one known to belong to no live restore.
    """
    from ..locking import BackupBusyError, backup_operation_lock, operation_lock_held
    removed: List[Path] = []
    restored: List[Path] = []
    try:
        with backup_operation_lock(timeout=0, purpose='sweeping interrupted restores',
                                   fail_open=False):
            if not operation_lock_held():
                return []
            try:
                _sweep_stale_stagings()
            except OSError as exc:
                logger.warning("Stagings of interrupted restores not swept: %s", exc)
            found = _find_kept_directories()
            tokens = {journal['token'] for _, journal in found if journal is not None}
            try:
                committed = _committed_tokens(tokens)
            except Exception as exc:
                logger.warning("Interrupted restores not settled, the database could not "
                               "be read: %s", exc)
                return []
            # Tokens a directory still on disk names: their rows stay for the next start
            named = set()
            for path, journal in found:
                if journal is not None and journal['token'] not in committed:
                    try:
                        _put_back_journal(path, journal)
                    except OSError as exc:
                        # Kept with its journal: its files disagree with the database until then
                        logger.warning("Restore: could not put back the previous contents kept "
                                       "in %s, retried at the next start: %s", path, exc)
                        continue
                    restored.append(Path(path))
                shutil.rmtree(path, ignore_errors=True)
                if not os.path.lexists(path):
                    removed.append(Path(path))
                elif journal is not None:
                    named.add(journal['token'])
                    logger.warning("Restore: could not remove %s, settled again at the next "
                                   "start", path)
            for token in committed - named:
                forget_publication(token)
            _forget_lingering_publications(keep=named)
    except BackupBusyError as exc:
        logger.debug("Interrupted restores not swept: %s", exc)
    except OSError as exc:
        logger.info("Interrupted restores not swept: %s", exc)
    if restored:
        logger.warning("Put back the previous contents of restores interrupted before their "
                       "commit: %s", ', '.join(str(path) for path in restored))
    if removed:
        logger.warning("Removed the previous contents kept by interrupted restores: %s",
                       ', '.join(str(path) for path in removed))
    return removed


def _sweep_stale_stagings() -> None:
    """The stagings in the system temporary directory that no live restore holds by flock.

    Only this module's prefix, a real directory of this user, never a link followed."""
    root = tempfile.gettempdir()
    uid = os.geteuid()
    removed = []
    for entry in os.scandir(root):
        if not (entry.name.startswith(_STAGING_PREFIX) and entry.is_dir(follow_symlinks=False)):
            continue
        try:
            fd = os.open(entry.path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        except OSError:
            continue
        try:
            info = os.fstat(fd)
            if info.st_uid != uid:
                continue
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except OSError:
                continue    # a live restore, of this instance or another, or no lock to prove it
            # Created without a lock: removed only once its recorded owner is proven gone
            if os.path.lexists(os.path.join(entry.path, _OWNER)) and not _owner_is_gone(entry.path):
                continue
            current = os.lstat(entry.path)
            if (current.st_dev, current.st_ino) != (info.st_dev, info.st_ino):
                continue
            try:
                shutil.rmtree(entry.path)
                removed.append(entry.path)
            except OSError as exc:
                logger.warning("Could not remove the staging of an interrupted restore %s: %s",
                               entry.path, exc)
        finally:
            os.close(fd)
    if removed:
        logger.warning("Removed the staged files of interrupted restores: %s", ', '.join(removed))


def _proc_start(pid: int) -> str:
    """The start time of process `pid` in this pid namespace (field 22 of its stat)."""
    with open(f'/proc/{pid}/stat') as handle:
        return handle.read().rsplit(')', 1)[1].split()[19]


def _owner_record() -> dict:
    """This process, named so that its death can be proven: boot, pid namespace, pid, start."""
    with open('/proc/sys/kernel/random/boot_id') as handle:
        boot = handle.read().strip()
    pid = os.getpid()
    return {'boot': boot, 'pidns': os.readlink('/proc/self/ns/pid'), 'pid': pid,
            'start': _proc_start(pid)}


def _owner_is_gone(staging: str) -> bool:
    """True only when the recorded owner provably no longer runs: same boot and pid
    namespace as this process, and its pid absent or held by a process started later."""
    try:
        fd = os.open(os.path.join(staging, _OWNER), os.O_RDONLY | os.O_NOFOLLOW)
        with os.fdopen(fd) as handle:
            owner = json.load(handle)
        here = _owner_record()
        if not (isinstance(owner, dict) and isinstance(owner.get('pid'), int)
                and owner.get('boot') == here['boot'] and owner.get('pidns') == here['pidns']):
            return False
        try:
            return _proc_start(owner['pid']) != owner.get('start')
        except FileNotFoundError:
            return True
    except (OSError, ValueError, IndexError):
        return False


def _forget_lingering_publications(keep=()) -> None:
    """Rows of restores killed after `discard()`, but never one a journal in `keep` still names;
    single node only, where every kept directory is this one's (in HA another node's may be)."""
    from flask import has_app_context
    from utils.ha import ha_enabled
    if ha_enabled() or not has_app_context():
        return
    from models import SystemConfig, db
    try:
        # The first start sweeps before the schema exists: no table, no row to forget
        if not db.inspect(db.engine).has_table(SystemConfig.__tablename__):
            return
        query = SystemConfig.query.filter(SystemConfig.key.startswith(PUBLICATION_PREFIX))
        if keep:
            query = query.filter(SystemConfig.key.notin_(
                [PUBLICATION_PREFIX + token for token in keep]))
        query.delete(synchronize_session=False)
        db.session.commit()
    except Exception as exc:
        db.session.rollback()
        logger.info("Restore publication records not removed: %s", exc)


def _write_private(path: Path, data: bytes, mode: int) -> None:
    """Write staged content at the mode its destination will carry.

    Staged key material must never be readable more widely than the file it
    will become, not even for the life of a restore. Not synced: the
    publication copies it and syncs the copy, the staging never outlives the process.
    """
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, mode)
    try:
        os.fchmod(fd, mode)
        with os.fdopen(fd, 'wb') as handle:
            fd = -1
            handle.write(data)
    finally:
        if fd >= 0:
            os.close(fd)


def _copy_private(source: Path, kept: Path) -> None:
    """A private copy of `source`, streamed: the previous content of a destination."""
    fd = os.open(kept, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, 'wb') as out, open(source, 'rb') as handle:
        shutil.copyfileobj(handle, out)
        out.flush()
        os.fsync(out.fileno())


def _put_back(kept: Path, destination: Path, mode: int) -> None:
    """Return the kept previous content to `destination`, atomically."""
    try:
        os.replace(kept, destination)    # the kept link, on the destination's filesystem
        os.chmod(destination, mode)
        return
    except OSError as exc:
        if exc.errno != errno.EXDEV:
            raise
    _atomic_replace(destination, kept.read_bytes(), mode)
