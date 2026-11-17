"""The restore as a background job: the archive in a file named after the job, the password
encrypted until the take, the run in the scheduler process.

The run holds what the route held before (the HA maintenance, or a local write gate on a
single node; the migration and backup locks). Its transaction writes the job's ``committed``
phase last, so the mark commits or rolls back with the restore. After the commit each end
step advances the phase by a conditional UPDATE: replayed by the recovery of an executor that
died, none is done twice. The job concludes itself, audit line included, before the restart
is asked: the restart may end this process.
"""
import json
import logging
import os
import threading
import time

from services.jobs import (
    SLOT_RESTORE, JobCancelled, JobOutcome, JobType, register,
)
from services.jobs import store
from services.jobs.store import JobLost

logger = logging.getLogger(__name__)

KIND = 'restore'
ACTION = 'system_restore'
ARCHIVE_SUFFIX = '.archive'
CANCEL_SUFFIX = '.cancel'
COPY_CHUNK = 1024 * 1024

# Phases before the commit
WAITING, CHECKING, READING, APPLYING, COMMITTING = (
    'waiting', 'checking', 'reading', 'applying', 'committing')
# Phases after it, in order: each names the end step done last
COMMITTED = 'committed'
SESSIONS = 'sessions_revoked'
SESSION_FILES = 'session_files_removed'
CACHES = 'caches_purged'
CRLS = 'crls_regenerated'
FINISH_ORDER = (COMMITTED, SESSIONS, SESSION_FILES, CACHES, CRLS)
VALIDATED = frozenset(FINISH_ORDER)
# Past these the session epoch has moved
REVOKED = frozenset(FINISH_ORDER[1:])

# The restore core's checkpoints, in order: the progress is the index of the last one passed
STEPS = ('read', 'plan', 'core', 'rbac', 'auth', 'notifications', 'policies', 'extended',
         'generic', 'relink')
CHECK_SECONDS = 1.0

GONE = 'The uploaded archive is no longer on this server: nothing was restored. Upload it again.'
TOO_LATE = 'The restore has committed: it can no longer be cancelled'
NOTHING_CARRIED = ('The archive carried no data: nothing was restored, '
                   'no session was revoked and no restart is needed.')


def params_of(name, filename, mode='replace'):
    """What the job keeps of the request: never the password nor a server path."""
    return {'name': name, 'filename': filename, 'mode': mode}


def archive_name(job_id):
    return store.file_name_for(job_id, ARCHIVE_SUFFIX)


def write_archive(job_id, stream):
    """Copy the uploaded stream into the job's file (0600, never through a link), chunk by
    chunk, yielding between chunks; the file name. Written BEFORE the job row: a pending
    job always has its whole file, and a file without a row is swept."""
    from utils.upload_spool import prepare_spool_dir
    from config.settings import DATA_DIR
    directory = prepare_spool_dir(DATA_DIR) or store.jobs_tmp_dir()
    name = archive_name(job_id)
    path = os.path.join(directory, name)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, 'O_NOFOLLOW', 0), 0o600)
    try:
        with os.fdopen(fd, 'wb') as out:
            stream.seek(0)
            while True:
                chunk = stream.read(COPY_CHUNK)
                if not chunk:
                    break
                out.write(chunk)
                time.sleep(0)  # the gevent loop runs between two chunks
            out.flush()
            os.fsync(out.fileno())
    except BaseException:
        store.purge_file(name)
        raise
    return name


# -- the local state of a single node --------------------------------------------------
# Outside HA the executor writes one file the web worker reads: the write gate (Q3) while
# the restore runs, and the job's view when the SQLite transaction holds the database.

STATE_NAME = 'restore-gate.json'
GATE_LEASE_SECONDS = 300
GATE_RENEW_SECONDS = 30
# A request in flight when the gate goes up finishes before the transaction starts
GATE_DRAIN_SECONDS = 1.0


def state_path():
    return os.path.join(store.jobs_tmp_dir(), STATE_NAME)


def read_state():
    """The local state written by a live executor, or None (absent, unreadable, dead pid)."""
    path = state_path()
    try:
        info = os.lstat(path)
        import stat as _stat
        if not _stat.S_ISREG(info.st_mode):
            return None
        with open(path, 'r', encoding='utf-8') as handle:
            state = json.load(handle)
    except (OSError, ValueError):
        return None
    if not isinstance(state, dict) or not _alive(state.get('pid')):
        return None
    if (state.get('expires') or 0) <= time.time():
        return None
    return state


def _alive(pid):
    if not isinstance(pid, int) or pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def _write_state(state):
    directory = store.jobs_tmp_dir()
    os.makedirs(directory, 0o700, exist_ok=True)
    path = state_path()
    tmp = f'{path}.{os.getpid()}.tmp'
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC | getattr(os, 'O_NOFOLLOW', 0), 0o600)
    with os.fdopen(fd, 'w', encoding='utf-8') as handle:
        json.dump(state, handle)
    os.replace(tmp, path)


def remove_state(job_id=None):
    """Remove the local state (only ``job_id``'s when given)."""
    path = state_path()
    if job_id is not None:
        try:
            with open(path, 'r', encoding='utf-8') as handle:
                if json.load(handle).get('job_id') != job_id:
                    return False
        except (OSError, ValueError):
            pass
    try:
        if os.path.islink(path):
            return False
        os.unlink(path)
        return True
    except FileNotFoundError:
        return False


def sweep_state(executor):
    """The scheduler's sweep: a state whose job is no longer active goes."""
    path = state_path()
    try:
        with open(path, 'r', encoding='utf-8') as handle:
            job_id = json.load(handle).get('job_id')
    except FileNotFoundError:
        return False
    except (OSError, ValueError):
        job_id = None
    row = store.job_row(executor, job_id) if job_id else None
    if row is not None and row['state'] in store.ACTIVE_STATES:
        return False
    return remove_state()


class LocalGate:
    """A single node's write gate: up while the restore runs, renewed by a thread of its own."""

    def __init__(self, app, ctx):
        self.app, self.ctx = app, ctx
        self.view = dict(ctx.view)
        # Written once: every renewal keeps the time the gate went up, which the 503 shows
        self.started_at = time.time()
        self._stop = threading.Event()
        self._lock = threading.Lock()
        self._thread = threading.Thread(target=self._renew_loop, daemon=True,
                                        name=f'restore-gate-{ctx.job_id[:8]}')

    def _state(self):
        return {'job_id': self.ctx.job_id, 'pid': os.getpid(), 'node_id': self.ctx.node_id,
                'actor': self.ctx.requested_by,
                'started_at': self.started_at, 'expires': time.time() + GATE_LEASE_SECONDS,
                'view': self.view}

    def raise_gate(self):
        with self._lock:
            _write_state(self._state())
        self._observe()
        self._thread.start()
        from services.scheduler_service import supervised
        if supervised():
            # The web worker reads the gate as each request starts: one in flight finishes
            time.sleep(GATE_DRAIN_SECONDS)
        return self

    def set_view(self, **view):
        with self._lock:
            self.view.update(view)
            if not self._stop.is_set():
                _write_state(self._state())

    def _renew_loop(self):
        while not self._stop.wait(GATE_RENEW_SECONDS):
            try:
                self.set_view()
            except OSError as e:
                logger.error(f"Restore write gate not renewed: {type(e).__name__}")

    def lift(self):
        with self._lock:
            self._stop.set()
            remove_state(self.ctx.job_id)
        self._observe()

    def _observe(self):
        from services import cluster_maintenance
        cluster_maintenance.observe_local(self.app)


# -- what a run sees --------------------------------------------------------------------

class _Run:
    """The checkpoints of one run: progress, cancellation, the local state."""

    def __init__(self, ctx, sqlite):
        self.ctx, self.sqlite = ctx, sqlite
        self.gate = None
        self._last = 0.0
        self._done = 0

    def checkpoint(self, step):
        from services.backup.restore import transaction
        done = STEPS.index(step) + 1 if step in STEPS else self._done
        phase = READING if step == 'read' else APPLYING
        changed = done != self._done
        self._done = max(self._done, done)
        now = time.monotonic()
        if not changed and now - self._last < CHECK_SECONDS:
            return
        self._last = now
        held = self.sqlite and transaction.inside()
        if self.gate is not None:
            self.gate.set_view(phase=phase, progress={'done': self._done, 'total': len(STEPS)},
                             held=held)
        if cancel_flagged(self.ctx.job_id):
            raise JobCancelled(self.ctx.job_id)
        if held:
            return  # the restore transaction holds the SQLite database: no other connection writes
        self.ctx.progress(done=self._done, total=len(STEPS), phase=phase)

    def mark(self, session, report):
        """In the restore transaction, last before its commit: the job is ``committed``
        with the report known so far, unless a cancellation was asked first."""
        from sqlalchemy import update
        T = store.T
        if self.gate is not None:
            self.gate.set_view(phase=COMMITTING)
        if cancel_flagged(self.ctx.job_id):
            raise JobCancelled(self.ctx.job_id)
        done = session.execute(update(T).where(
            T.c.id == self.ctx.job_id, T.c.state == store.RUNNING,
            T.c.executor == self.ctx.executor, T.c.cancel_requested.is_(False),
        ).values(phase=COMMITTED, result=_stored(report))).rowcount
        if done != 1:
            asked = session.execute(T.select().where(T.c.id == self.ctx.job_id)).mappings().first()
            if asked is not None and asked['state'] == store.RUNNING and asked['cancel_requested']:
                raise JobCancelled(self.ctx.job_id)
            raise JobLost(self.ctx.job_id)


def cancel_flagged(job_id):
    return os.path.exists(os.path.join(store.jobs_tmp_dir(), store.file_name_for(job_id, CANCEL_SUFFIX)))


def flag_cancel(job_id):
    """A cancellation asked while the SQLite transaction holds the database: a local file."""
    path = os.path.join(store.jobs_tmp_dir(), store.file_name_for(job_id, CANCEL_SUFFIX))
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | getattr(os, 'O_NOFOLLOW', 0), 0o600)
    os.close(fd)


def _stored(report, **extra):
    return json.dumps({'code': None, 'message': None, 'data': report, **extra}, default=str)


def _committed_on_a_fresh_connection(job_id):
    """The issue of a commit that raised, read again where the restore did not run."""
    from models import db
    with db.engine.connect() as conn:
        row = store.job_row(conn, job_id)
    if row is not None and row['phase'] in VALIDATED and row['result']:
        return json.loads(row['result'])['data']
    return None


def _refused(code, message, details):
    return JobOutcome(code=code, message=message, audit_details=details)


def _request_refused(code, message, reason):
    from services.backup.restore_completion import REQUEST_REFUSED
    return _refused(code, message, REQUEST_REFUSED + reason)


def run(ctx):
    from config.settings import Config
    from models import db
    from services import jobs
    sqlite = db.engine.dialect.name == 'sqlite'
    row = store.job_row(db.session, ctx.job_id)
    db.session.rollback()
    ctx.node_id = Config.NODE_ID
    ctx.requested_by = (row or {}).get('requested_by_name')
    ctx.view = jobs.public_view(row, with_result=False) if row else {'id': ctx.job_id, 'kind': KIND}
    password = ctx.secret
    path = ctx.file_path
    ctx.progress(done=0, total=len(STEPS), phase=CHECKING)
    try:
        fd = os.open(path or '', os.O_RDONLY | getattr(os, 'O_NOFOLLOW', 0))
    except OSError:
        outcome = _refused(500, GONE, 'Restore failed: the uploaded archive was gone')
    else:
        with os.fdopen(fd, 'rb') as stream:
            outcome = _restore(ctx, _Run(ctx, sqlite), stream, password)
    return outcome  # its audit line names the archive: the type's resource_param


def _archive_label(ctx):
    return ctx.params.get('name') or 'upload'


def _restore(ctx, current, stream, password):
    from fips_mode import FipsRestricted, PROBLEM_TYPE as FIPS_PROBLEM
    from services import cluster_maintenance
    from services.backup.decrypt_mixin import BackupDecryptionError
    from services.backup.errors import RestoreFilesUnwritable
    from services.backup.locking import BackupBusyError, backup_operation_lock
    from services.backup.restore import transaction
    from services.backup.restore.plan import RestoreValidationError
    from services.backup_service import BackupSchemaError, BackupService, ContainerError
    from services.database_admin.lock import MigrationBusyError, database_migration_lock
    from utils.ha import ha_enabled
    name, mode = _archive_label(ctx), ctx.params.get('mode') or 'replace'
    service = BackupService()
    actor = ctx.requested_by
    try:
        with cluster_maintenance.restore_window(
                actor, preflight=lambda: service.check_archive_opens(stream, password)) as maintenance:
            with _local_gate(ctx, current, maintenance is None and not ha_enabled()):
                try:
                    with database_migration_lock(purpose='the restore'), \
                            backup_operation_lock(purpose='the restore', fail_open=False), \
                            transaction.marking(current.mark), \
                            transaction.progressing(current.checkpoint):
                        try:
                            results = service.restore_backup_from_stream(stream, password, mode=mode)
                        except (JobCancelled, JobLost):
                            raise
                        except BaseException:
                            results = _committed_on_a_fresh_connection(ctx.job_id)
                            if results is None:
                                raise
                            logger.error("Restore: its commit raised but the database has it")
                except MigrationBusyError as busy:
                    if busy.unavailable:
                        return _request_refused(409, str(busy), 'the migration lock could not be taken')
                    return _request_refused(
                        409, f'{busy} A backend migration or another restore is still running.',
                        'a backend migration or another restore is running')
                except BackupBusyError as busy:
                    if busy.unavailable:
                        return _request_refused(409, str(busy), 'the backup lock could not be taken')
                    return _request_refused(409, f'{busy} Retry once it has finished.',
                                            'a backup or another restore is running')
                except RestoreFilesUnwritable as unwritable:
                    return _refused(409, str(unwritable),
                                    'Restore refused: a file directory is not writable')
                return finish(ctx.job_id, ctx.executor, results, name,
                              ctx.params.get('filename'), maintenance, current.gate)
    except (JobCancelled, JobLost):
        raise
    except cluster_maintenance.MaintenanceRefused as refused:
        logger.warning('Restore refused: %s', refused)
        outcome = _request_refused(409, str(refused), 'the cluster maintenance could not be held')
        outcome.problem = {'code': refused.code}
        if getattr(refused, 'missing', None):
            outcome.problem['nodes'] = refused.missing
        return outcome
    except FipsRestricted as e:
        outcome = _refused(400, str(e), 'Restore refused: not allowed in FIPS mode')
        outcome.problem_type = FIPS_PROBLEM
        return outcome
    except BackupDecryptionError:
        logger.warning('Restore refused: the backup could not be decrypted')
        return _refused(400, 'Wrong backup password, or the file is not a valid backup',
                        'Restore refused: wrong password or invalid backup')
    except (ContainerError, BackupSchemaError, RestoreValidationError) as e:
        logger.warning('Restore refused: %s', e)
        return _refused(400, str(e), 'Restore refused: the archive failed validation')
    except OverflowError as e:
        logger.warning('Restore refused: a value is out of range (%s)', e)
        return _refused(400, 'The archive carries a numeric value this database cannot '
                             'store; the file is not a valid backup',
                        'Restore refused: a value is out of range')
    except ValueError as e:
        logger.warning('Restore refused: %s', e)
        return _refused(400, f'The archive could not be read: {e}',
                        'Restore refused: the archive could not be read')
    except Exception:
        logger.exception('Restore failed')
        return _refused(500, 'Restore failed', 'Restore failed: unexpected error')


class _local_gate:
    """The single node's write gate around the restore, its executor exempt from it."""

    def __init__(self, ctx, current, wanted):
        self.ctx, self.current, self.wanted = ctx, current, wanted
        self._token = None

    def __enter__(self):
        from services import cluster_maintenance
        if not self.wanted:
            return None
        self._token = cluster_maintenance._exempt.set(True)
        self.current.gate = LocalGate(self.ctx.app, self.ctx).raise_gate()
        return self.current.gate

    def __exit__(self, *exc):
        from services import cluster_maintenance
        store.purge_file(store.file_name_for(self.ctx.job_id, CANCEL_SUFFIX))
        if self.current.gate is not None:
            self.current.gate.lift()
        if self._token is not None:
            cluster_maintenance._exempt.reset(self._token)
        return False


# -- after the commit -------------------------------------------------------------------

class _Ledger:
    """The stored result of a committed restore: its report, and what each end step noted."""

    def __init__(self, job_id):
        self.job_id = job_id
        self.reload()

    def reload(self):
        from models import db
        row = store.job_row(db.session, self.job_id)
        db.session.rollback()
        stored = json.loads(row['result']) if row and row['result'] else {}
        self.phase = row['phase'] if row else None
        self.report = stored.get('data') or {}
        self.notes = {k: v for k, v in stored.items() if k not in ('code', 'message', 'data')}
        self.summary = dict(self.report.get('invalidated') or {})

    def advance(self, was, now_phase, **notes):
        """``was`` -> ``now_phase`` on db.session, not committed; False when another actor did it."""
        from sqlalchemy import update
        from models import db
        T = store.T
        self.notes.update(notes)
        self.report['invalidated'] = self.summary
        done = db.session.execute(update(T).where(
            T.c.id == self.job_id, T.c.state == store.RUNNING, T.c.phase == was).values(
            phase=now_phase, result=_stored(self.report, **self.notes))).rowcount == 1
        if done:
            self.phase = now_phase
        return done


def claim_sessions(session, job_id=None):
    """The one actor that advances the epoch for a committed restore: 'claimed' (this
    transaction moves the job past its sessions step: advance the epoch in it), 'done'
    (another did) or None (no restore job is concerned: the caller decides alone)."""
    from sqlalchemy import select, update
    T = store.T
    query = select(T.c.id, T.c.phase).where(T.c.kind == KIND, T.c.state == store.RUNNING)
    if job_id is not None:
        query = query.where(T.c.id == job_id)
    rows = session.execute(query).all()
    validated = [(i, p) for i, p in rows if p in VALIDATED]
    if not validated:
        return None
    for found, phase in validated:
        if phase == COMMITTED and session.execute(update(T).where(
                T.c.id == found, T.c.state == store.RUNNING, T.c.phase == COMMITTED).values(
                phase=SESSIONS)).rowcount == 1:
            row = session.execute(select(T.c.result).where(T.c.id == found)).first()
            stored = json.loads(row[0]) if row and row[0] else {}
            stored['sessions_at'] = time.time()
            session.execute(update(T).where(T.c.id == found).values(
                result=json.dumps(stored, default=str)))
            return 'claimed'
    return 'done'


SESSION_TRIES = 3


def _marked(job_id, report):
    """A restore that returned without its transaction's mark (none was taken) is marked
    now, so its end steps are noted like any other's."""
    from sqlalchemy import update
    from models import db
    T = store.T
    db.session.execute(update(T).where(
        T.c.id == job_id, T.c.state == store.RUNNING,
        T.c.phase.is_(None) | T.c.phase.notin_(tuple(VALIDATED))).values(
        phase=COMMITTED, result=_stored(report)))
    db.session.commit()


def _finish_steps(job_id):
    """Every end step not yet done, each noted on the job as it is: the report."""
    from models import db
    from services.backup.restore import invalidate
    ledger = _Ledger(job_id)
    if ledger.phase == COMMITTED:
        def claim(counts):
            ledger.summary.update(counts)
            return ledger.advance(COMMITTED, SESSIONS, sessions_at=time.time())
        counts = None
        for attempt in range(SESSION_TRIES):
            try:
                counts = invalidate.revoke_sessions_with(claim)
                break
            except Exception:
                db.session.rollback()
                if attempt == SESSION_TRIES - 1:
                    raise
                time.sleep(1)
        ledger.reload()
        if counts is None:
            logger.warning(f"Restore job {job_id}: its sessions were revoked by another actor")
    if ledger.phase == SESSIONS:
        older = ledger.notes.get('sessions_at') or time.time()
        ledger.summary['session_files_removed'] = invalidate.remove_session_files(older_than=older)
        ledger.advance(SESSIONS, SESSION_FILES)
        db.session.commit()
    if ledger.phase == SESSION_FILES:
        cleared, failed = invalidate.purge_caches(with_tables=True)
        ledger.summary.update(caches_cleared=cleared, caches_failed=failed)
        invalidate.note_purged_epoch()
        ledger.advance(SESSION_FILES, CACHES)
        db.session.commit()
    if ledger.phase == CACHES:
        ledger.summary.update(invalidate.regenerate_crls_summary())
        ledger.advance(CACHES, CRLS)
        db.session.commit()
    ledger.reload()
    return ledger.report


def predicted_restart():
    """What asking the restart will answer, known before it is asked (it may end this process)."""
    from config.settings import Config, is_docker
    if Config.HA_MODE:
        from services.cluster_commands import ROLLING_RESTART_MESSAGE
        return True, ROLLING_RESTART_MESSAGE
    if is_docker():
        return False, "Service restart not available in Docker. Restart the container instead."
    return True, "Service restart initiated"


def finish(job_id, executor, results, name, filename, maintenance=None, gate=None,
           resumed=False):
    """A committed restore: the end steps, the conclusion with its audit line, then the
    restart. Returns a concluded JobOutcome."""
    from models import db
    from services import cluster_maintenance
    from services.backup.restore_completion import (
        attach_restore_todo, request_restart, restore_message)
    from services.backup.restore_report import safe_restore_audit_details
    results = dict(results or {})
    details = safe_restore_audit_details(name, results)
    if not results.get('sections_carried'):
        # Nothing changed: no session revoked, no restart
        if maintenance:
            maintenance.lift_unchanged()
        logger.warning('Restore: the archive carried no data section')
        attach_restore_todo(results)
        _conclude(job_id, executor, 200, NOTHING_CARRIED, results, details, name)
        return JobOutcome(concluded=True)
    if gate is not None:
        gate.set_view(phase=COMMITTED, held=False)  # a cancellation is now the row's to refuse
    with cluster_maintenance.exempt():
        try:
            _marked(job_id, results)
            results = _finish_steps(job_id)
        except Exception:
            db.session.rollback()
            logger.exception('Restore: sessions could not be revoked')
            _conclude(job_id, executor, 500,
                      'Backup restored, but the sessions opened before it could not be revoked. '
                      'Restart the application before using it.', None, details, name, ok=True)
            return JobOutcome(concluded=True)
        ok, detail = (True, _rolling_message()) if maintenance is not None else predicted_restart()
        try:
            results['restart_requested'], results['restart_detail'] = ok, detail
            if filename is not None:
                results['filename'] = filename
            attach_restore_todo(results)
            message = restore_message(results)
        except Exception:
            # Committed and audited as a success: no second, contradicting line
            db.session.rollback()
            logger.exception('Restore: finishing after the restore failed')
            _conclude(job_id, executor, 500, 'Backup restored, but finishing the restore failed. '
                      'Restart the application before using it.', None, details, name, ok=True)
            return JobOutcome(concluded=True)
        _conclude(job_id, executor, 200, message, results, details, name)
    if gate is not None:
        gate.lift()
    # Asked once the job is final: the restart may stop this process
    if maintenance is not None:
        actual = maintenance.finish()
    elif resumed and _ha():
        actual = (ok, detail)  # the cluster maintenance's completion asks it (complete_committed)
    else:
        actual = request_restart() if ok else (ok, detail)
    if tuple(actual) != (ok, detail):
        _amend_restart(job_id, results, actual)
    return JobOutcome(concluded=True)


def _ha():
    from utils.ha import ha_enabled
    return ha_enabled()


def _rolling_message():
    from services.cluster_commands import ROLLING_RESTART_MESSAGE
    return ROLLING_RESTART_MESSAGE


def _conclude(job_id, executor, code, message, data, details, name, ok=None):
    """The job's one conclusion and audit line, in one transaction; retried while the
    database refuses it (the result stands; the recovery concludes it otherwise)."""
    from models import db
    from services import jobs
    succeeded = code < 400 if ok is None else ok
    audit = jobs.audit_writer(KIND)
    result = {'code': code, 'message': message, 'data': data}
    def line(r, s, why):
        return audit(r, s, why, details, name)
    for attempt in range(3):
        try:
            for result_line in (line, None):
                done = store.conclude_job(
                    db.session, job_id, state=store.SUCCEEDED if succeeded else store.FAILED,
                    reason=store.DONE if succeeded else store.ERROR, from_states=(store.RUNNING,),
                    now=jobs._now(), result=result, executor=executor, result_line=result_line)
                if done:
                    if result_line is None:
                        # The restore committed: its result stands without its line
                        logger.error(f"Restore job {job_id} concluded without its audit line")
                    return True
            logger.warning(f"Restore job {job_id} was concluded elsewhere")
            return False
        except Exception as e:
            db.session.rollback()
            logger.error(f"Restore job {job_id} not concluded: {type(e).__name__}")
            time.sleep(1)
    return False


def _amend_restart(job_id, results, actual):
    """The restart did not go as announced: the final result says so (best effort)."""
    from sqlalchemy import update
    from models import db
    from services.backup.restore_completion import restore_message
    results = dict(results)
    results['restart_requested'], results['restart_detail'] = bool(actual[0]), actual[1]
    T = store.T
    try:
        db.session.execute(update(T).where(T.c.id == job_id).values(result=json.dumps(
            {'code': 200, 'message': restore_message(results), 'data': results}, default=str)))
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        logger.error(f"Restore job {job_id}: restart outcome not recorded: {type(e).__name__}")


def resume(job_id, executor):
    """Recovery of a committed restore whose executor is gone: the end steps it had not done,
    its conclusion and the restart (outside HA)."""
    from models import db
    row = store.job_row(db.session, job_id)
    db.session.rollback()
    if row is None or row['phase'] not in VALIDATED:
        return False
    stored = json.loads(row['result']) if row['result'] else {}
    report = stored.get('data') or {}
    params = json.loads(row['params']) if row['params'] else {}
    logger.warning(f"Restore job {job_id} committed before its executor was lost: finishing it")
    try:
        finish(job_id, executor, report, params.get('name') or 'upload',
               params.get('filename'), resumed=True)
    except Exception as e:
        db.session.rollback()
        logger.error(f"Restore job {job_id} not finished by the recovery: {type(e).__name__}")
        return False
    return True


def local_view(job_id):
    """The job as the local state shows it, for a read the SQLite transaction blocks."""
    state = read_state()
    if state is None or state.get('job_id') != job_id:
        return None
    return {k: v for k, v in (state.get('view') or {}).items() if k != 'held'}


def cancel_locally(job_id):
    """None, or the outcome of a cancellation answered from the local state."""
    state = read_state()
    view = (state or {}).get('view') or {}
    if state is None or state.get('job_id') != job_id or not view.get('held'):
        return None
    if view.get('phase') == COMMITTING:
        return 'too_late'
    flag_cancel(job_id)
    return 'requested'


register(JobType(
    kind=KIND, slot=SLOT_RESTORE, permission='admin:system', run=run, label='Restore',
    audit_action=ACTION, node_bound=True, resume=resume, resumable_phases=VALIDATED,
    # Every result line names the archive, whoever concludes the job (cancelled, lost, not taken)
    resource_param='name',
    messages={'executor_lost': 'The restore stopped before it committed: nothing was restored',
              'not_taken': 'The restore was never started: nothing was restored',
              'cancelled': 'The restore was cancelled: nothing was restored',
              'error': 'Restore failed'}))
