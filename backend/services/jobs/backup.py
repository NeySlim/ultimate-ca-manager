"""The manual backup as a background job: the password travels encrypted until the take.

Both create routes start it; ``params['route']`` keeps each one's answer as it was
(``size`` formatted or not, the download URL of its family, the refusal of a bad parameter).
The scheduled backup is not a job: it already runs in the scheduler process.
"""
import logging
import time

from services.jobs import SLOT_BACKUP, JobCancelled, JobOutcome, JobType, register
from services.jobs.store import JobLost

logger = logging.getLogger(__name__)

KIND = 'backup'
ROUTE_SYSTEM, ROUTE_SETTINGS = 'system', 'settings'
ACTION = 'system_backup'
# Seconds between two cancellation checks inside a section
CHECK_SECONDS = 1.0

BUSY = 'Backup refused: another backup or restore is running'


def params_of(route, kdf=None, generated=False):
    """What the job keeps of the request: never the password."""
    return {'route': route, 'kdf': kdf, 'generated': bool(generated)}


def format_size(size_bytes):
    if size_bytes < 1024:
        return f'{size_bytes} B'
    if size_bytes < 1024 * 1024:
        return f'{size_bytes / 1024:.1f} KB'
    return f'{size_bytes / (1024 * 1024):.1f} MB'


def _refused(code, message, details, problem_type=None):
    return JobOutcome(code=code, message=message, audit_details=details, problem_type=problem_type)


def _reporter(ctx):
    """progress(done, total) at each section; progress() between rows, checked once a second."""
    last = [time.monotonic()]

    def progress(done=None, total=None):
        now = time.monotonic()
        if done is not None:
            last[0] = now
            ctx.progress(done=done, total=total,
                         phase='publishing' if done == total else 'exporting')
        elif now - last[0] >= CHECK_SECONDS:
            last[0] = now
            ctx.check()
    return progress


def _export(ctx, service, password, kdf, route):
    """(size, filename) or the JobOutcome of today's refusal for what the export raised."""
    from fips_mode import FipsRestricted, PROBLEM_TYPE as FIPS_PROBLEM
    from services.backup import storage
    from services.backup.locking import BackupBusyError
    from services.backup_service import (BackupExportError, BackupPasswordError,
                                         BackupValidationError)
    try:
        size, _path, filename = storage.export_archive(service, password, kdf=kdf,
                                                       progress=_reporter(ctx))
        return (size, filename), None
    except (JobCancelled, JobLost):
        raise
    except FipsRestricted as e:
        return None, _refused(400, str(e), 'Backup refused: not allowed in FIPS mode', FIPS_PROBLEM)
    except BackupBusyError as busy:
        logger.info('Backup refused: %s', busy)
        return None, _refused(409, str(busy), BUSY)
    except BackupPasswordError as e:
        return None, _refused(400, str(e), 'Backup refused: password rejected')
    except BackupExportError as e:
        logger.error('Backup aborted: %s', e)
        return None, _refused(500, f'Backup aborted: {e}', 'Backup failed: export aborted')
    except BackupValidationError as e:
        logger.error('Backup written but not validated: %s', e)
        return None, _refused(500, f'Backup could not be validated: {e}',
                              'Backup failed: archive could not be validated')
    except ValueError:
        if route != ROUTE_SYSTEM:
            logger.exception('Backup failed')
            return None, _refused(500, 'Backup failed', 'Backup failed: unexpected error')
        logger.exception('Backup refused: invalid parameters')
        return None, _refused(400, 'Invalid backup parameters', 'Backup refused: invalid parameters')
    except Exception:
        logger.exception('Backup failed')
        return None, _refused(500, 'Backup failed', 'Backup failed: unexpected error')


def run(ctx):
    from services.backup.schedule import safe_ceiling_warning
    from services.backup_service import BackupService
    route = ctx.params.get('route') or ROUTE_SYSTEM
    generated = bool(ctx.params.get('generated'))
    password = ctx.secret
    ctx.progress(done=0, phase='waiting')
    service = BackupService()
    made, refusal = _export(ctx, service, password, ctx.params.get('kdf'), route)
    del password
    if refusal is not None:
        return refusal
    size, filename = made
    family = 'settings' if route == ROUTE_SETTINGS else 'system'
    data = {
        'filename': filename,
        # The settings family has always answered the byte count here, the system one a text
        'size': size if route == ROUTE_SETTINGS else format_size(size),
        'size_bytes': size,
        'download_url': f'/api/v2/{family}/backup/{filename}/download',
        # Creation removes nothing: the next retention brings the archives under the ceiling
        'warning': safe_ceiling_warning(),
    }
    message = 'Backup created successfully'
    warnings = list(service.last_export_warnings)
    if route == ROUTE_SETTINGS:
        message += ' - SAVE THE PASSWORD!' if generated else ''
        if warnings:
            data['export_warnings'] = warnings
            message += (' ' if message.endswith('!') else '. ') + '; '.join(warnings)
    elif warnings:
        data['export_warnings'] = warnings
        message = f"{message}. {'; '.join(warnings)}"
    return JobOutcome(code=200, message=message, data=data,
                      audit_details=f'Created backup: {filename}', audit_resource=filename)


register(JobType(
    kind=KIND, slot=SLOT_BACKUP, permission='admin:system', run=run, label='Backup',
    audit_action=ACTION, resource_name='manual',
    messages={'executor_lost': 'The backup stopped before the end: run it again',
              'not_taken': 'The backup was never started: run it again',
              'cancelled': 'The backup was cancelled',
              'error': 'Backup failed'}))
