"""Scheduled backup support.

Runs unattended encrypted backups when due, applies retention, and lists
backup history from disk.

The source of truth is the General-settings keys the UI actually writes:
``auto_backup_enabled``, ``backup_frequency`` (daily/weekly/monthly),
``backup_retention_days``, ``backup_password`` and ``backup_kdf``. There is
no time-of-day in the UI, so cadence is driven by a stored ``backup.last_run``
timestamp. A run reserves its slot by moving ``backup.last_run`` and concludes it
by copying that value to ``backup.concluded_run`` once its archive is written; the
schedule reports ``in_progress`` while a reservation is not concluded within its lease.
"""
import base64
import glob
import json
import logging
import os
import time
from datetime import datetime, timezone

import fips_mode
from models import db, SystemConfig
from config.settings import Config
from utils.config_cas import config_compare_and_set, config_release
from utils.datetime_utils import utc_now, utc_isoformat

from . import shared_store, storage
from .backup_service import BackupService
from .locking import BackupBusyError, backup_operation_lock
from .errors import ScheduledBackupError
from .settings_contract import scheduled_kdf

logger = logging.getLogger(__name__)

_BACKUP_GLOB = 'ucm_backup_*.ucmbkp'
_LAST_RUN_KEY = 'backup.last_run'
# The reservation (a last_run value) whose archive was written: a reservation that
# differs from it is in flight, or abandoned once the lease is over.
_CONCLUDED_KEY = 'backup.concluded_run'
_VALID_FREQUENCIES = ('daily', 'weekly', 'monthly')
_PERIOD_SECONDS = {'daily': 86400, 'weekly': 604800, 'monthly': 2592000}
# A claimed run not concluded is in flight for this long, then abandoned (killed,
# OOM, os._exit on shutdown): the slot becomes due again.
_CLAIM_LEASE_SECONDS = 2 * 3600

# Archives with no validation record are kept in this number, newest first:
# nothing can be proven about them either way, so prudence decides.
_UNRECORDED_KEPT = 2

# How many archives survive whatever their age, and how much room they may
# take. Age alone is the wrong sole criterion: a fortnight of failures with a
# seven-day retention leaves nothing to restore from, and a daily backup of a
# growing instance fills the filesystem it is stored on without ever tripping
# a date.
_MIN_KEEP_KEY = 'backup_min_keep'
_MAX_TOTAL_MB_KEY = 'backup_max_total_mb'
DEFAULT_MIN_KEEP = 2
DEFAULT_MAX_TOTAL_MB = 0            # 0 = no size ceiling

# What the last unattended run did, kept across restarts so the answer does
# not depend on which worker is asked.
_LAST_OUTCOME_KEY = 'backup.last_outcome'
_LAST_REASON_KEY = 'backup.last_reason'
_LAST_OUTCOME_AT_KEY = 'backup.last_outcome_at'


def _get(key, default=None):
    cfg = SystemConfig.query.filter_by(key=key).first()
    return cfg.value if cfg and cfg.value is not None else default


def get_schedule() -> dict:
    """Return the effective backup schedule, and what the last run did.

    `last_run` says when the task last decided something; it said nothing
    about whether an archive came out of it, so a schedule could look healthy
    with no backup anywhere. The age of the last provable restore point and
    the outcome of the last run are the two answers an administrator needs.

    `cadence` is `rolling_interval` on purpose: "daily" means twenty-four
    hours since the last run, not a time of day, and the runs drift with
    restarts. Saying so is more useful than implying a calendar the scheduler
    does not keep.
    """
    freq = _get('backup_frequency', 'daily')
    if freq not in _VALID_FREQUENCIES:
        freq = 'daily'
    try:
        retention = int(_get('backup_retention_days', '30'))
    except (ValueError, TypeError):
        retention = 30

    newest, age = _newest_validated_archive()
    last_run = _get(_LAST_RUN_KEY)
    return {
        'enabled': _get('auto_backup_enabled', 'false') == 'true',
        'frequency': freq,
        'cadence': 'rolling_interval',
        'retention_days': retention,
        'min_keep': _min_keep(),
        'max_total_mb': _max_total_bytes() // (1024 * 1024),
        'last_run': last_run,
        # last_run is then this run's reservation, the outcome still the previous run's
        'in_progress': _in_flight(last_run, _get(_CONCLUDED_KEY), utc_now()),
        'last_outcome': _get(_LAST_OUTCOME_KEY),
        'last_outcome_reason': _get(_LAST_REASON_KEY),
        'last_outcome_at': _get(_LAST_OUTCOME_AT_KEY),
        'last_archive': os.path.basename(newest) if newest else None,
        'last_archive_age_seconds': age,
        'password_set': bool(_get('backup_password')),
        'kdf': _get('backup_kdf') or 'auto',
    }


def _newest_validated_archive():
    """The most recent archive whose bytes still match what was recorded."""
    if shared_store.enabled():
        # Each stored archive was read back before its commit
        stored = shared_store.list_archives()
        if not stored:
            return None, None
        newest = stored[0]
        return newest['filename'], max(0, int(time.time() - shared_store.timestamp(newest['created_at'])))
    paths = _existing_archives()
    newest = storage.newest_validated(paths) if paths else None
    if newest is None:
        return None, None
    return newest, max(0, int(time.time() - _mtime_of(newest)))


def _record_outcome(outcome: str, reason: str = None) -> None:
    """Remember what the last unattended run did.

    The scheduler view holds this in memory, so it is lost on restart and
    differs between workers; an administrator asking "did last night's backup
    run" deserves the same answer from any of them.
    """
    try:
        for key, value in ((_LAST_OUTCOME_KEY, outcome),
                           (_LAST_REASON_KEY, reason),
                           (_LAST_OUTCOME_AT_KEY, utc_isoformat(utc_now()))):
            row = SystemConfig.query.filter_by(key=key).first()
            if row:
                row.value = value
            else:
                db.session.add(SystemConfig(key=key, value=value))
        db.session.commit()
    except Exception:
        # The whole of it, not the commit alone: the read and the add can
        # fail too, and an exception escaping here reached the caller, which
        # recorded a backup that is on disk and readable as a failure -- and
        # then called this again from its own `except`, replacing the
        # original error with this one.
        try:
            db.session.rollback()
        except Exception:
            logger.warning("Could not roll back after a failed outcome record")
        # The outcome is a report, not the work: the schedule follows the conclusion
        # marker, so losing it neither fails a backup nor brings a second one.
        logger.warning("Could not record the outcome of the scheduled backup")


def _get_backup_password() -> str:
    """Return the decrypted configured backup password, or '' if unset.

    A stored value that looks encrypted but does not decrypt is an error, not
    a password: returning the ciphertext produced archives encrypted with a
    string the administrator has never seen, reported as successful backups.
    """
    val = _get('backup_password')
    if not val:
        return ''

    from utils.encryption import decrypt_value, is_encrypted
    if not is_encrypted(val):
        return val  # stored before at-rest encryption was enabled

    password = decrypt_value(val)  # raises when the key is missing/unusable
    if not password:
        raise ScheduledBackupError(
            'The configured backup password could not be decrypted '
            '(the DB encryption key changed?). Set it again under '
            'Settings > Backup.'
        )
    return password


def list_backups() -> list[dict]:
    """List the archives, newest first: on disk, or in HA the database's with their node."""
    if shared_store.enabled():
        return [{'filename': a['filename'], 'size': a['size'], 'node': a['node'],
                 'sha256': a['sha256'], 'created_at': utc_isoformat(a['created_at'])}
                for a in shared_store.list_archives()]
    backups = []
    try:
        for path in glob.glob(os.path.join(str(Config.BACKUP_DIR), _BACKUP_GLOB)):
            try:
                st = os.stat(path)
            except OSError:
                continue
            backups.append({
                'filename': os.path.basename(path),
                'size': st.st_size,
                'created_at': utc_isoformat(datetime.fromtimestamp(st.st_mtime, timezone.utc)),
            })
    except Exception as e:
        logger.error(f"Failed to list backups: {e}")
    backups.sort(key=lambda b: b['created_at'] or '', reverse=True)
    return backups


def _apply_shared_retention(retention_days: int, wait: float = 0) -> int:
    """HA: the rule below over the database's archives, under a lock of the whole cluster.

    Busy with no wait is a pass skipped; with a wait it raises BackupBusyError.
    """
    try:
        return shared_store.apply_retention(
            retention_days, min_keep=_min_keep(), max_total_bytes=_max_total_bytes(), wait=wait)
    except BackupBusyError as busy:
        if wait:
            raise
        logger.info("Backup retention skipped: %s", busy)
        return 0


def _apply_retention(retention_days: int) -> int:
    """Delete backup files older than retention_days. Returns count removed.

    Two archives are never pruned, whatever their age. The most recent one
    that still matches its validation record is the last provable restore
    point: retention ran on a timer of its own, so a long export outage (a
    lost DB key, no configured password) used to end with nothing left to
    restore from. Archives with no record at all — written before records
    existed, or by another path — are kept in the two most recent, since
    nothing proves they are usable and nothing proves they are not.
    """
    if shared_store.enabled():
        return _apply_shared_retention(retention_days)
    if not retention_days or retention_days < 1:
        return 0
    # Wall-clock seconds, not utc_now().timestamp(): utc_now() is naive UTC,
    # so Python reads it as local time and the cutoff drifts by the machine's
    # offset. File times are epoch seconds, and so is this.
    cutoff = time.time() - retention_days * 86400
    removed = 0
    paths = []
    for path in glob.glob(os.path.join(str(Config.BACKUP_DIR), _BACKUP_GLOB)):
        try:
            os.stat(path)
        except OSError:
            continue
        paths.append(path)

    keep = _protected_archives(paths)

    for path in _oldest_first(paths):
        if path in keep:
            continue
        try:
            if os.stat(path).st_mtime < cutoff:
                os.unlink(path)
                removed += 1
        except OSError:
            continue

    removed += _enforce_size_ceiling(keep)

    if removed:
        logger.info(f"Backup retention removed {removed} expired backup(s)")
    return removed


def _protected_archives(paths: list) -> set:
    """Archives retention will not touch, whatever their age.

    The most recent provable restore point, the archives nothing can vouch
    for either way, and a minimum number of the newest: a run of failed
    backups must not end with an empty directory because the calendar said so.
    """
    keep = set()
    validated = storage.newest_validated(paths)
    if validated:
        keep.add(validated)
    keep.update(storage.unrecorded(paths)[:_UNRECORDED_KEPT])

    # The minimum count protects against losing a restore point, so it does
    # not extend to an archive proven to be something other than what was
    # written: keeping it would push out one that can still be restored.
    tampered = set(storage.tampered(paths))  # hashes every archive: once per pass
    provable = [path for path in _newest_first(paths) if path not in tampered]
    keep.update(provable[:_min_keep()])
    return keep


def _enforce_size_ceiling(keep: set) -> int:
    """Remove the oldest archives until they fit the configured ceiling.

    Retention by age lets a daily backup of a growing instance fill its
    filesystem: the archives are all recent, and all kept. The protected
    archives are never removed, so the ceiling can be exceeded rather than
    leave the instance without a restore point; that case is logged.
    """
    ceiling = _max_total_bytes()
    if ceiling <= 0:
        return 0

    paths = _existing_archives()
    total = sum(_size_of(path) for path in paths)
    if total <= ceiling:
        return 0

    removed = 0
    for path in _oldest_first(paths):
        if total <= ceiling:
            break
        if path in keep:
            continue
        size = _size_of(path)
        try:
            os.unlink(path)
        except OSError:
            continue
        total -= size
        removed += 1

    if total > ceiling:
        logger.warning(
            "Backup retention: the archives still take %d MiB, above the %d MiB "
            "ceiling, because what remains is the last restore point",
            total // (1024 * 1024), ceiling // (1024 * 1024))
    elif removed:
        logger.info("Backup retention removed %d archive(s) to stay under the "
                    "configured size ceiling", removed)
    return removed


def _existing_archives() -> list:
    paths = []
    for path in glob.glob(os.path.join(str(Config.BACKUP_DIR), _BACKUP_GLOB)):
        try:
            os.stat(path)
        except OSError:
            continue
        paths.append(path)
    return paths


def _size_of(path: str) -> int:
    try:
        return os.path.getsize(path)
    except OSError:
        return 0


def _mtime_of(path: str) -> float:
    try:
        return os.stat(path).st_mtime
    except OSError:
        return 0.0


def _newest_first(paths: list) -> list:
    return sorted(paths, key=_mtime_of, reverse=True)


def _oldest_first(paths: list) -> list:
    return sorted(paths, key=_mtime_of)


def _min_keep() -> int:
    try:
        value = int(_get(_MIN_KEEP_KEY, str(DEFAULT_MIN_KEEP)))
    except (TypeError, ValueError):
        return DEFAULT_MIN_KEEP
    return max(1, value)


def _max_total_bytes() -> int:
    try:
        megabytes = int(_get(_MAX_TOTAL_MB_KEY, str(DEFAULT_MAX_TOTAL_MB)))
    except (TypeError, ValueError):
        return 0
    return max(0, megabytes) * 1024 * 1024


def run_backup_retention(wait: float = 0) -> int:
    """Apply backup retention independently of the scheduled-backup run.

    Registered as its own daily scheduler task so retention is enforced even when
    automatic backups are disabled (manual backups would otherwise accumulate
    forever). Honours `backup_retention_days` (0 / unset → no pruning).
    """
    try:
        retention = int(_get('backup_retention_days', '30'))
    except (ValueError, TypeError):
        retention = 30

    try:
        # Retention deletes; a backup being written at the same moment is not
        # yet recorded, and would look like an archive nothing vouches for.
        with backup_operation_lock(timeout=wait, purpose='backup retention'):
            if shared_store.enabled():
                return _apply_shared_retention(retention, wait)
            return _apply_retention(retention)
    except BackupBusyError as busy:
        # The scheduled pass (wait=0) simply tries again in a day; a person
        # who asked for it is told instead of being handed "0 removed".
        if wait:
            raise
        logger.info("Backup retention skipped: %s", busy)
        return 0


def _claim_run(previous, now: datetime):
    """Move ``backup.last_run`` from what the due check read to this run, before any
    archive is written: of two nodes finding the run due, one writes. The claimed
    value, or None when another node moved it first."""
    claimed = utc_isoformat(now)
    try:
        moved = config_compare_and_set(_LAST_RUN_KEY, previous, claimed)
    except Exception as exc:
        db.session.rollback()
        raise ScheduledBackupError(f'The backup schedule could not be reserved: {exc}') from exc
    return claimed if moved else None


def _start_marking_conclusions(previous) -> None:
    """Create the conclusion marker before the first reservation that can need it, so
    a run killed with none recorded is retried; an existing marker is left alone."""
    try:
        # Read first: the compare-and-set's INSERT would hit the unique key, an ERROR in the PG log
        if db.session.query(SystemConfig.value).filter_by(key=_CONCLUDED_KEY).scalar() is not None:
            return
        config_compare_and_set(_CONCLUDED_KEY, None, previous or '')
    except Exception as exc:
        db.session.rollback()
        raise ScheduledBackupError(f'The backup schedule could not be reserved: {exc}') from exc


def _conclude_run(claimed: str) -> None:
    """Mark the reservation *claimed* as done once its archive exists; raises, since a
    lost marker would bring a second archive once the lease is over."""
    try:
        row = SystemConfig.query.filter_by(key=_CONCLUDED_KEY).first()
        if row:
            row.value = claimed
        else:
            db.session.add(SystemConfig(key=_CONCLUDED_KEY, value=claimed))
        db.session.commit()
    except Exception as exc:
        db.session.rollback()
        raise ScheduledBackupError(
            f'The archive was written but its run could not be marked concluded: {exc}') from exc


def _release_run(previous, claimed: str) -> None:
    """Give a run that wrote no archive back to the next tick, unless moved since."""
    # The claim is committed; a failed export may have left the transaction aborted
    db.session.rollback()
    try:
        config_release(_LAST_RUN_KEY, claimed, previous)
    except Exception:
        db.session.rollback()
        logger.warning("Could not release the backup schedule; retried once the lease is over")


def _parse(value):
    try:
        return _naive_utc(datetime.fromisoformat(value.replace('Z', '+00:00')))
    except (ValueError, AttributeError):
        return None


def _unconcluded_for(last_run, concluded, now: datetime):
    """Seconds since the reservation *last_run* was taken, or None when it is concluded.
    No marker at all: last_run predates it (upgraded install) and counts as concluded."""
    prev = _parse(last_run) if last_run else None
    if prev is None or concluded is None or concluded == last_run:
        return None
    return (_naive_utc(now) - prev).total_seconds()


def _in_flight(last_run, concluded, now: datetime) -> bool:
    elapsed = _unconcluded_for(last_run, concluded, now)
    return elapsed is not None and elapsed < _CLAIM_LEASE_SECONDS


def _is_due(sched: dict, now: datetime) -> bool:
    period = _PERIOD_SECONDS.get(sched.get('frequency', 'daily'), 86400)
    last_run = sched.get('last_run')
    if not last_run:
        return True  # never run → run now
    prev = _parse(last_run)
    if prev is None:
        return True
    elapsed = (_naive_utc(now) - prev).total_seconds()
    # An upgraded install has no marker yet: its last run counts as concluded
    unconcluded = _unconcluded_for(last_run, sched.get('concluded_run'), now)
    if unconcluded is not None and unconcluded >= _CLAIM_LEASE_SECONDS:
        return True  # claimed, never concluded, lease expired
    # small slack so a ~daily timer doesn't drift a day each run
    return elapsed >= period - 300


def _naive_utc(value: datetime) -> datetime:
    """Normalise to naive UTC, which is what utc_now() returns."""
    if value.tzinfo is not None:
        return value.astimezone(timezone.utc).replace(tzinfo=None)
    return value


def run_scheduled_backup() -> dict:
    """Scheduler task — creates an encrypted backup when one is due.

    Returns a structured result (`ok` / `skipped`) and raises on failure. Both
    matter to the scheduler: swallowing the exception left the task reporting
    "completed successfully", with a green view, a growing run count and no
    archive anywhere.
    """
    sched = get_schedule()
    if not sched.get('enabled'):
        _record_outcome('skipped', 'disabled')
        return {'status': 'skipped', 'reason': 'disabled'}

    now = utc_now()
    sched['concluded_run'] = _get(_CONCLUDED_KEY)
    if not _is_due(sched, now):
        return {'status': 'skipped', 'reason': 'not_due'}

    password = _get_backup_password()
    if not password or len(password) < 12:
        # Automatic backups are on and nothing can be produced: a failure the
        # administrator has to see, not a quiet log line.
        _audit_scheduled_backup(
            'scheduled', 'Scheduled backup failed: no valid backup password '
            'configured', success=False)
        _record_outcome('failed', 'no valid backup password configured')
        raise ScheduledBackupError(
            'No valid backup password configured (set a 12+ character '
            'password under Settings > Backup).'
        )

    try:
        # The scheduled run, the run-now button and retention all write in the
        # same directory: without this, two of them could produce the same
        # name, truncate each other's file, and both record a success.
        with backup_operation_lock(purpose='the scheduled backup'):
            return _create_scheduled_backup(sched, now, password)
    except BackupBusyError as busy:
        logger.info("Scheduled backup skipped: %s", busy)
        return {'status': 'skipped', 'reason': 'another operation in progress'}


def _create_scheduled_backup(sched: dict, now: datetime, password: str) -> dict:
    """Write, validate and record one scheduled archive."""
    try:
        kdf = scheduled_kdf(sched.get('kdf'))
        if kdf == 'argon2id' and fips_mode.enabled():
            # A setting carried over from a standard instance must not stop every run.
            logger.warning("Scheduled backup KDF is Argon2id, refused in FIPS mode: using PBKDF2")
            kdf = None
        _start_marking_conclusions(sched.get('last_run'))
        claimed = _claim_run(sched.get('last_run'), now)
        if claimed is None:
            logger.info("Scheduled backup already taken by another node")
            return {'status': 'skipped', 'reason': 'claimed by another node'}
        service = BackupService()
        try:
            # The same export and naming as every other archive, under the lock already held
            size, _path, filename = storage.export_archive(service, password, kdf=kdf)
        except Exception:
            # No archive: the next tick retries. Past this point the claim stays,
            # so nothing after the write can bring a second archive a minute later.
            _release_run(sched.get('last_run'), claimed)
            raise
        _conclude_run(claimed)

        logger.info(f"Scheduled backup created: {filename} ({size} bytes)")
        for left_out in service.last_export_warnings:
            logger.warning("Scheduled backup %s: %s", filename, left_out)
        _audit_scheduled_backup(filename, f'Scheduled backup: {filename}',
                                success=True)

        removed = _apply_retention(sched.get('retention_days', 30))
        _record_outcome('ok', filename)
        return {
            'status': 'ok',
            'filename': filename,
            'size': size,
            'retention_removed': removed,
        }
    except Exception as e:
        logger.error(f"Scheduled backup failed: {e}", exc_info=True)
        # A failure that only a log line reports is a backup nobody has:
        # the audit trail records it, as the successes are recorded
        _audit_scheduled_backup('scheduled', f'Scheduled backup failed: {e}',
                                success=False)
        _record_outcome('failed', str(e)[:200])
        raise


def _audit_scheduled_backup(resource_name: str, details: str, *,
                            success: bool) -> None:
    """Record a scheduled-backup outcome without masking it if audit is down."""
    try:
        from services.audit_service import AuditService
        AuditService.log_action(
            action='system_backup', resource_type='system',
            resource_name=resource_name, details=details,
            success=success, username='system',
        )
    except Exception:
        logger.exception("Scheduled backup outcome could not be audited")
