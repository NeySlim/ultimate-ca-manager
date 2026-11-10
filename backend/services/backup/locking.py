"""One backup operation at a time, across every worker process.

Three paths create, validate or delete archives: the scheduled task (which
wakes every 60 seconds), the "run now" button, and retention (a daily task
plus an on-demand route). Nothing serialised them, so two runs could pick the
same filename within the same second, delete what the other was still reading
back, and both record a success. UCM runs under gunicorn with several
workers, so an in-memory lock would only serialise the threads of one of
them: the exclusion has to live in the filesystem, which is what every worker
shares.

The mechanism itself is ``utils.process_lock``, shared with the database
migration lock. What belongs here is only what is specific to backups: where
the lock file lives, and the exception a refused caller sees.
"""
from contextlib import contextmanager
from pathlib import Path
import logging

from config.settings import Config
from utils.process_lock import (  # noqa: F401  (_local: the test suite resets it)
    LockBusyError,
    _local,
    lock_depth,
    process_lock,
)

logger = logging.getLogger(__name__)

LOCK_NAME = '.ucm_backup_operation.lock'

# What the refusal calls the operation it is protecting.
_SUBJECT = 'backup operation'


class BackupBusyError(LockBusyError):
    """Another backup operation holds the lock.

    Raised instead of waiting, so a caller can report plainly that nothing was
    started rather than queueing a second archive nobody asked for. The
    message names no path and no host, and is safe to return to the caller.
    """


def operation_lock_path() -> Path:
    """Return the lock file, which lives next to the archives it guards.

    The name is a dotfile and does not end in an archive extension, so
    neither the listing route (which filters on ``.ucmbkp``/``.json.enc``)
    nor the retention glob (``ucm_backup_*.ucmbkp``) can mistake it for a
    restore point.

    It is created once and never deleted. Removing it would not release
    anything — it would let the next process create a *new* inode under the
    same name and take a second, independent lock, which is precisely the
    mutual exclusion this module exists to provide.
    """
    return Path(Config.BACKUP_DIR) / LOCK_NAME


def operation_lock_depth() -> int:
    """How many nested backup blocks this thread currently holds."""
    return lock_depth(operation_lock_path())


@contextmanager
def backup_operation_lock(*, timeout: float = 0, purpose: str = 'backup',
                          fail_open: bool = True):
    """Hold the backup lock for the duration of the block.

    Every path that creates, validates or deletes an archive takes this same
    lock, so that only one of them is ever touching the backup directory.
    ``timeout``, reentrancy and the fail-open behaviour on a filesystem
    without flock are documented on ``utils.process_lock.process_lock``.
    """
    with process_lock(operation_lock_path(), timeout=timeout, purpose=purpose,
                      subject=_SUBJECT, busy_error=BackupBusyError,
                      fail_open=fail_open):
        yield
