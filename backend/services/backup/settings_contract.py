"""What a backup setting may hold, decided in one place.

Frequency and retention reached the database through two routes that did not
agree on what was legal: the dedicated schedule route bounded both, General
settings took any string for the frequency and any value at all for the
retention, and reading the schedule back quietly substituted a default for
whatever had been stored. A cadence the scheduler does not know became "daily"
without anyone being told, and a retention of ``null`` became 30 days on one
screen and nothing at all on another.

A value this product refuses is refused where it is written, by these
functions, with a message that names the rule. What is stored is therefore
always something the scheduler can run, and reading it back needs no
correction.
"""
import logging
from typing import Optional

from fips_mode import FipsRestricted

logger = logging.getLogger(__name__)

# Retention is a number of days, bounded like every other validity input in
# this project (1 day .. 10 years). Zero is not "no pruning" here: the schedule
# route never accepted it, and a retention nobody can see is how archives grow
# until the filesystem decides.
MIN_RETENTION_DAYS = 1
MAX_RETENTION_DAYS = 3650


class BackupSettingError(ValueError):
    """A backup setting was refused.

    The message names the field and the rule that refused it, and nothing
    else: it is meant to be returned to the caller as-is.
    """


def valid_frequencies() -> tuple:
    """The cadences the scheduler knows how to run.

    Read from the scheduler instead of being restated here: a frequency this
    contract accepted and the scheduler did not know would be a schedule that
    silently never runs at the cadence that was asked for.

    The import is deferred because the scheduler is built on the backup
    service this contract is itself part of.
    """
    from .schedule import _VALID_FREQUENCIES
    return tuple(_VALID_FREQUENCIES)


def validate_frequency(value, field: str = 'backup_frequency') -> str:
    """Return the frequency, or raise BackupSettingError naming the rule."""
    allowed = valid_frequencies()
    if not isinstance(value, str) or value not in allowed:
        raise BackupSettingError(
            f"{field} must be one of {', '.join(allowed)}")
    return value


def validate_retention_days(value, field: str = 'backup_retention_days') -> int:
    """Return the retention in days, or raise BackupSettingError.

    A value that is not a whole number of days is refused rather than
    truncated: 7.5 stored as 7 is a retention nobody asked for.
    """
    days = _whole_number(value)
    if days is None:
        raise BackupSettingError(f"{field} must be a whole number of days")
    if days < MIN_RETENTION_DAYS or days > MAX_RETENTION_DAYS:
        raise BackupSettingError(
            f"{field} must be between {MIN_RETENTION_DAYS} and "
            f"{MAX_RETENTION_DAYS} days")
    return days


def validate_backup_password(value) -> str:
    """Return the password, or raise BackupSettingError naming the rule.

    The rule is the backup service's own: a password refused when an archive
    is created must be refused when it is stored for the unattended run, or
    every scheduled backup fails in silence (#346).
    """
    # Deferred for the same reason as the frequencies: this contract is part
    # of the backup service package the rule lives in.
    from services.backup_service import BackupService, BackupPasswordError

    if not isinstance(value, str):
        raise BackupSettingError('Backup password must be a string')
    try:
        BackupService.validate_password(value)
    except BackupPasswordError as exc:
        raise BackupSettingError(str(exc)) from exc
    return value


BACKUP_KDFS = ('auto', 'pbkdf2', 'argon2id')


def validate_backup_kdf(value, field: str = 'backup_kdf') -> str:
    """The scheduled backups' KDF: 'auto' (Argon2id when available, PBKDF2 in
    FIPS mode), 'pbkdf2' or 'argon2id'; FIPS mode refuses 'argon2id'."""
    from .backup_service import check_backup_kdf

    if value in (None, ''):
        return 'auto'
    if not isinstance(value, str) or value not in BACKUP_KDFS:
        raise BackupSettingError(f"{field} must be one of {', '.join(BACKUP_KDFS)}")
    if value != 'auto':
        try:
            check_backup_kdf(value)
        except FipsRestricted:
            raise
        except ValueError as exc:
            raise BackupSettingError(str(exc)) from exc
    return value


def scheduled_kdf(stored) -> Optional[str]:
    """What create_backup is given for a stored KDF setting: None means automatic."""
    return stored if stored in ('pbkdf2', 'argon2id') else None


def _whole_number(value):
    """Return `value` as an int when it is exactly a whole number, else None."""
    # bool is an int in Python: True would silently become one day.
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value) if value.is_integer() else None
    if isinstance(value, str):
        try:
            return int(value.strip())
        except ValueError:
            return None
    return None
