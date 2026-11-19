"""Errors raised while building a backup archive.

An archive that is missing a section, or that carries a key nobody can
decrypt, is not a backup: it is a file that will only reveal what it lost on
the day it is restored. Every such condition aborts the backup with one of
these errors instead of being downgraded to a log line. The one exception is
an HSM field this installation itself cannot open: see `decrypt_stored_fields`.
"""


class BackupExportError(RuntimeError):
    """A requested section could not be exported.

    The message names the section (and, for key material, the object) so an
    administrator can act on it. It never carries key material, secrets or the
    underlying driver error, and is safe to return to the caller.
    """


class ScheduledBackupError(RuntimeError):
    """The scheduled backup task could not produce a usable archive.

    Raised so the scheduler records the run as failed: the task used to
    swallow every error and still report a successful run.
    """


class BackupValidationError(RuntimeError):
    """An archive did not read back as it was written.

    Raised after publication, before the archive is recorded as a restore
    point: a file that cannot be proven whole must not be one.
    """


class BackupSchemaError(ValueError):
    """The payload describes a shape this version cannot restore.

    Raised before the first write, so its message can say plainly that
    nothing was changed: an archive from a newer UCM, or one whose sections
    are short of the counts it announces.
    """
