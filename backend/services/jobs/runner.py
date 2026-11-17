"""Where a job runs: a thread of the scheduler process under gunicorn, of this process otherwise.

The scheduler process's JobRunner polls for pending jobs, takes them, recovers orphans and
expires what nobody took. Every run renews its lease from a thread of its own, on a
connection of its own, exempt from the HA maintenance gate like the maintenance's own lease.
"""
import json
import logging
import os
import threading
import time
import uuid

from services import jobs
from services.jobs import store

logger = logging.getLogger(__name__)

POLL_SECONDS = 1
RENEW_SECONDS = 30
RECOVER_SECONDS = 15
PURGE_SECONDS = 3600
WAIT_POLL_SECONDS = 0.5
CONCLUDE_RETRY_SECONDS = 2

# Jobs run by a thread of this process: their end is awaited on the event, not the database
_local_done = {}
_local_lock = threading.Lock()
_TOKEN = uuid.uuid4().hex[:8]


def executor_id():
    """This process, as written on the jobs it takes (never shown by the API)."""
    return f'{jobs._node_id()}/{os.getpid()}/{_TOKEN}'


def _app():
    from flask import current_app
    return current_app._get_current_object()


def dispatch_job(job_id):
    """Hand a new job to its executor. Under gunicorn the scheduler process polls for it;
    otherwise this process takes it now and runs it in a thread."""
    from services.scheduler_service import supervised
    if supervised():
        return
    from models import db
    executor = executor_id()
    row = store.claim_job(db.session, job_id, executor, jobs._now())
    if row is None:
        return
    done = threading.Event()
    with _local_lock:
        _local_done[job_id] = done
    thread = threading.Thread(target=run_job, args=(_app(), row, executor, done),
                              name=f'job-{job_id[:8]}', daemon=True)
    thread.start()


def join_local(job_id, timeout=30):
    """Tests and the bounded wait: until a job run by this process has ended."""
    with _local_lock:
        done = _local_done.get(job_id)
    return True if done is None else done.wait(timeout)


class _Lease:
    def __init__(self, app, job_id, executor):
        self.app, self.job_id, self.executor = app, job_id, executor
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._runner_loop, daemon=True, name=f'job-lease-{job_id[:8]}')

    def start(self):
        self._thread.start()
        return self

    def stop(self):
        self._stop.set()

    def _runner_loop(self):
        from models import db
        from services.cluster_maintenance import exempt
        while not self._stop.wait(RENEW_SECONDS):
            with self.app.app_context(), exempt():
                try:
                    with db.engine.begin() as conn:
                        if not store.renew_lease(conn, self.job_id, self.executor, jobs._now(conn)):
                            return
                except Exception as e:
                    logger.error(f"Background job lease not renewed: {type(e).__name__}")


class JobContext:
    """What a run sees: its parameters, its secret (memory only), its file, and progress()."""

    def __init__(self, app, row, executor):
        self.app = app
        self.job_id = row['id']
        self.kind = row['kind']
        self.params = json.loads(row['params']) if row['params'] else {}
        self.file_name = row['file_name']
        self.executor = executor
        self._secret = row['secret']
        self._total = None

    @property
    def secret(self):
        if self._secret is None:
            return None
        from utils.encryption import decrypt_value
        return decrypt_value(self._secret)

    @property
    def file_path(self):
        return os.path.join(store.jobs_tmp_dir(), self.file_name) if self.file_name else None

    def progress(self, done=None, total=None, phase=None):
        """Record progress on a connection of its own; JobCancelled when one was asked."""
        from models import db
        from services.cluster_maintenance import exempt
        with exempt(), db.engine.begin() as conn:
            asked = store.write_progress(conn, self.job_id, self.executor, done, total, phase)
        if asked:
            raise jobs.JobCancelled(self.job_id)

    def check(self):
        self.progress()


def _response_of(outcome):
    response = {'code': outcome.code, 'message': outcome.message, 'data': outcome.data}
    if outcome.problem_type:
        response['problem_type'] = outcome.problem_type
    return response


def _conclude_after_maintenance(app, conclude):
    """A conclusion refused by a maintenance is tried again once it is lifted, lease kept:
    its audit line is no write to make while a restore replaces the tables."""
    from models import db
    from services.cluster_maintenance import MaintenanceActive, blocks_writes
    while True:
        try:
            if conclude():
                return True
            if not blocks_writes(app):
                return False
        except MaintenanceActive:
            db.session.rollback()
        while blocks_writes(app):
            time.sleep(CONCLUDE_RETRY_SECONDS)


def run_job(app, row, executor, done=None):
    """Run a taken job to its one conclusion, whatever the run raises."""
    from models import db
    job_id, kind = row['id'], row['kind']
    jt = jobs.job_type(kind)
    audit = jobs.audit_writer(kind)
    with app.app_context():
        lease = _Lease(app, job_id, executor).start()
        raised = None
        try:
            try:
                if jt is None:
                    raise RuntimeError(f'unknown job kind {kind}')
                outcome = jt.run(JobContext(app, row, executor))
                ok = outcome.code < 400
                state = store.SUCCEEDED if ok else store.FAILED
                # A 4xx is the run refusing; a 5xx is an error, whoever caught it
                reason = (store.DONE if ok else store.ERROR if outcome.code >= 500
                          else store.REFUSED)
                result, details = _response_of(outcome), outcome.audit_details
                resource = outcome.audit_resource
            except jobs.JobCancelled:
                state, reason, result, details = store.CANCELLED, store.CANCELLED_REASON, None, None
                resource = None
            except store.JobLost:
                logger.warning(f"Background job {job_id} was concluded elsewhere while it ran")
                return
            except BaseException as e:  # noqa: B036 - concluded, then raised again if not an Exception
                logger.error(f"Background job {job_id} ({kind}) failed: {type(e).__name__}",
                             exc_info=isinstance(e, Exception))
                state, reason, result, details = store.FAILED, store.ERROR, None, None
                resource = None
                if not isinstance(e, Exception):
                    raised = e
            db.session.rollback()
            line = None
            if audit is not None:
                def _job_result_line(r, s, why):
                    return audit(r, s, why, details, resource)
                line = _job_result_line
            def conclude(result_line):
                return store.conclude_job(
                    db.session, job_id, state=state, reason=reason, from_states=(store.RUNNING,),
                    now=jobs._now(), result=result, executor=executor, result_line=result_line)
            # One result line per job: tried twice, then the job ends without it (a slot held
            # until a restart is worse) and the line goes to the log; no-op if concluded elsewhere
            if (not _conclude_after_maintenance(app, lambda: conclude(line)) and line is not None
                    and not _conclude_after_maintenance(app, lambda: conclude(line))
                    and _conclude_after_maintenance(app, lambda: conclude(None))):
                logger.error(f"Background job {job_id} concluded without its audit line: "
                             + jobs.result_line_text(kind, state, reason, details, resource))
        except Exception as e:
            logger.error(f"Background job {job_id} not concluded: {type(e).__name__}")
            db.session.rollback()
        finally:
            lease.stop()
            db.session.remove()
            if done is not None:
                done.set()
                with _local_lock:
                    _local_done.pop(job_id, None)
        if raised is not None:
            raise raised


def wait_for_job(job_id, seconds):
    """The job row once it is final or ``seconds`` have passed, whichever comes first."""
    from models import db
    with _local_lock:
        done = _local_done.get(job_id)
    if done is not None:
        done.wait(max(0.0, seconds))
        return jobs.get_job(job_id)
    deadline = time.monotonic() + max(0.0, seconds)
    while True:
        db.session.rollback()  # each read sees what the executor committed since
        row = store.job_row(db.session, job_id)
        db.session.rollback()
        if row is None or row['state'] in store.FINAL_STATES or time.monotonic() >= deadline:
            return row
        time.sleep(min(WAIT_POLL_SECONDS, max(0.0, deadline - time.monotonic())))


class JobRunner:
    """The scheduler process's executor: takes pending jobs while this process leads
    (or, for a job bound to this node, whenever it runs), recovers orphans, purges."""

    def __init__(self, app, scheduler):
        self.app = app
        self.scheduler = scheduler
        self.executor = executor_id()
        self._stop = threading.Event()
        self._thread = None
        self._running = {}          # job id -> thread
        self._recovered = False
        self._last_recover = 0.0
        self._last_purge = 0.0
        self._swept = False
        self._last_files = 0.0

    def start(self):
        self._thread = threading.Thread(target=self._runner_loop, daemon=True, name='JobRunner')
        self._thread.start()
        return self

    def stop(self):
        """No job is taken after this; running ones go on until join()."""
        self._stop.set()

    def join(self, timeout):
        deadline = time.monotonic() + timeout
        for thread in [self._thread, *self._running.values()]:
            if thread is not None and thread.is_alive():
                thread.join(max(0.0, deadline - time.monotonic()))
                if thread.is_alive():
                    return False
        return True

    def _runner_loop(self):
        while not self._stop.wait(POLL_SECONDS):
            try:
                with self.app.app_context():
                    self.run_pass()
            except Exception as e:
                logger.error(f"Background jobs pass failed: {type(e).__name__}: {e}")
            finally:
                try:
                    from models import db
                    with self.app.app_context():
                        db.session.remove()
                except Exception:
                    pass

    def leads(self):
        return self.scheduler.holds_lock()

    def run_pass(self):
        from models import db
        from utils.ha import ha_enabled
        ha = ha_enabled()
        # A maintenance refuses every write of this pass: none is tried until it is lifted
        if self.scheduler._in_maintenance():
            return
        leads = self.leads()
        finished = {job_id: self.executor for job_id, thread in self._running.items()
                    if not thread.is_alive()}
        for job_id in finished:
            self._running.pop(job_id, None)
        now_mono = time.monotonic()
        if leads and (not self._recovered or finished
                      or now_mono - self._last_recover >= RECOVER_SECONDS):
            # Single node: the first pass under the host lock finds only orphans (nothing is
            # taken here before it: a take needs the lead, and recovery comes first in a pass)
            all_running = not ha and not self._recovered
            store.recover_orphans(db.session, now=jobs._now(), all_running=all_running,
                          audit_for=jobs.audit_writer, mine=finished)
            self._recovered, self._last_recover = True, now_mono
        # Each node sweeps its own disk, leader or not: a job concluded by another node
        # purged that node's disk only. Unknown files stay after the first pass (uploads).
        if not self._swept or now_mono - self._last_files >= RECOVER_SECONDS:
            store.sweep_job_files(db.session, keep_unknown=self._swept)
            db.session.rollback()
            self._swept, self._last_files = True, now_mono
        if leads and now_mono - self._last_purge >= PURGE_SECONDS:
            store.purge_finished(db.session, jobs._now())
            self._last_purge = now_mono
        if self._stop.is_set():
            return
        self._take_pending(leads)

    def _take_pending(self, leads):
        from sqlalchemy import select
        from models import db
        T = store.T
        me = jobs._node_id()
        rows = db.session.execute(select(T.c.id, T.c.node_id).where(
            T.c.state == store.PENDING).order_by(T.c.created_at)).all()
        db.session.rollback()
        for job_id, node_id in rows:
            # HA: a job bound to a node is that node's alone, leader or not
            if node_id is not None:
                if node_id != me:
                    continue
            elif not leads:
                continue
            row = store.claim_job(db.session, job_id, self.executor, jobs._now())
            if row is None:
                continue
            thread = threading.Thread(target=run_job, args=(self.app, row, self.executor),
                                      name=f'job-{job_id[:8]}', daemon=True)
            self._running[job_id] = thread
            thread.start()
