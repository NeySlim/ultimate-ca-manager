"""One operation at a time, across every worker process.

UCM runs under gunicorn with several workers, so an in-memory lock only ever
serialises the threads of one of them. Operations that must not overlap —
writing a backup archive, migrating the database to another backend — need an
exclusion that lives in the filesystem, which is the one thing every worker
shares.

The lock is advisory (``flock``), held for the whole operation, and keyed by
the file that carries it: a thread already holding one lock must still be
able to take a different one, so the nesting depth is counted per path and
not once for the process.
"""
from contextlib import contextmanager
from pathlib import Path
import errno
import logging
import os
import threading
import time

try:
    import fcntl
except ImportError:  # pragma: no cover - UCM targets POSIX hosts
    fcntl = None

logger = logging.getLogger(__name__)

# errno values flock uses to say "someone else holds it"; anything else is a
# system failure, which is handled very differently below.
_BUSY_ERRNOS = frozenset(filter(None, (
    errno.EACCES,
    errno.EAGAIN,
    getattr(errno, 'EWOULDBLOCK', None),
)))

# flock has no timed variant, so waiting is polling. The interval is short
# enough that an operation queued behind another feels immediate, and long
# enough not to spin a worker while a multi-second export finishes.
_POLL_INTERVAL = 0.05

_local = threading.local()


class LockBusyError(RuntimeError):
    """Another process holds the lock.

    Raised instead of waiting, so a caller can report plainly that nothing was
    started rather than queueing work nobody asked for. The message names no
    path and no host, and is safe to return to the caller.
    """


def _depths() -> dict:
    """Return this thread's nesting depth per lock file.

    flock ownership belongs to the file descriptor, not to the caller: a
    process that already holds a lock and re-locks the same file simply
    succeeds, and the first release would then drop a lock the outer caller
    still believes it holds. So the depth is counted here, per thread —
    because two threads of one worker are two callers — per process, because
    ``fork()`` copies this thread's counter into a child that owns no
    descriptor of its own, and per path, because holding the backup lock says
    nothing about the migration lock.
    """
    state = getattr(_local, 'state', None)
    if state is None or state['pid'] != os.getpid():
        state = {'pid': os.getpid(), 'depth': {}, 'held': set()}
        _local.state = state
    return state['depth']


def _held() -> set:
    _depths()
    return _local.state.setdefault('held', set())


def lock_depth(path) -> int:
    """How many nested blocks of this thread currently hold ``path``."""
    return _depths().get(str(path), 0)


def lock_held(path) -> bool:
    """Whether this thread holds ``path`` by flock, not merely runs fail-open."""
    return str(path) in _held()


def _open_lock_file(path: Path) -> int:
    """Open (creating if needed) the lock file, private to the service."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(path, os.O_CREAT | os.O_RDWR, 0o600)
    try:
        # The file survives restarts, so a first creation under a wider umask
        # would keep its mode forever.
        os.fchmod(fd, 0o600)
    except OSError:
        logger.warning("Could not set 0600 on the lock file %s", path)
    return fd


def busy_message(subject: str, timeout: float, purpose: str) -> str:
    """The one sentence a refused caller is given."""
    if timeout > 0:
        return (f"Another {subject} is still in progress after "
                f"{timeout:g}s; {purpose} was not started.")
    return (f"Another {subject} is already in progress; "
            f"{purpose} was not started.")


def _acquire(fd: int, timeout: float, message: str, busy_error) -> None:
    """Take the exclusive lock, waiting at most ``timeout`` seconds."""
    deadline = time.monotonic() + max(timeout, 0.0)
    while True:
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            return
        except OSError as exc:
            if exc.errno not in _BUSY_ERRNOS:
                raise  # a system failure, not a busy lock

        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise busy_error(message)
        time.sleep(min(_POLL_INTERVAL, remaining))


@contextmanager
def process_lock(path, *, timeout: float = 0, purpose: str = 'the operation',
                 subject: str = 'operation', busy_error=LockBusyError,
                 fail_open: bool = True):
    """Hold the lock at ``path`` for the duration of the block.

    ``timeout=0`` (the default) does not wait: if another process holds the
    lock, ``busy_error`` is raised and the caller reports that nothing was
    started. A positive ``timeout`` waits that many seconds before raising.
    ``purpose`` and ``subject`` only name the caller in the message and in the
    logs.

    Re-entering the same lock from the same thread is free: the nested block
    does not re-lock, and the descriptor is released once the outermost block
    exits — a route that holds the lock and calls a helper which takes it
    again must not deadlock against itself.

    ``fail_open`` decides what happens when the lock cannot be taken for a
    *system* reason — no permission on the file, or a filesystem without
    flock (NFS without lockd, some SMB mounts). Open, the operation is logged
    as unprotected and allowed through, which is the right trade-off for a
    backup: an installation that can never take one again is a worse failure
    than two overlapping runs. Closed, the operation is refused, which is the
    right trade-off wherever a concurrent run would destroy something — two
    migrations filling the same target, each writing its own answer into the
    configuration file.
    """
    path = Path(path)
    key = str(path)
    depths = _depths()
    if depths.get(key, 0) > 0:
        # Already held by this thread: count the nesting, lock nothing.
        depths[key] += 1
        try:
            yield
        finally:
            depths[key] -= 1
        return

    fd = None
    held = False
    try:
        if fcntl is None:
            raise OSError(errno.ENOSYS, 'flock is unavailable on this platform')
        fd = _open_lock_file(path)
        _acquire(fd, timeout, busy_message(subject, timeout, purpose), busy_error)
        held = True
    except LockBusyError:
        _close(fd)
        logger.info("The %s lock is held by another process; %s refused",
                    subject, purpose)
        raise
    except OSError as exc:
        _close(fd)
        fd = None
        if not fail_open:
            logger.error(
                "The %s lock could not be taken (%s); %s was refused",
                subject, exc, purpose)
            raise busy_error(
                f"The {subject} lock could not be taken, so {purpose} was not "
                "started. Check the permissions on the data directory.")
        logger.error(
            "The %s lock could not be taken (%s); %s runs without protection "
            "against a concurrent operation", subject, exc, purpose)

    # Counted even when nothing was locked: the nesting has to unwind the
    # same way either way, and a nested block must not try to lock again.
    depths[key] = 1
    if held:
        _held().add(key)
    try:
        yield
    finally:
        depths[key] = 0
        _held().discard(key)
        if fd is not None:
            if held:
                try:
                    fcntl.flock(fd, fcntl.LOCK_UN)
                except OSError:
                    # Closing the descriptor releases it anyway.
                    logger.warning("Could not unlock %s explicitly", path)
            _close(fd)


def _close(fd) -> None:
    if fd is None:
        return
    try:
        os.close(fd)
    except OSError:
        logger.warning("Could not close a lock descriptor")
