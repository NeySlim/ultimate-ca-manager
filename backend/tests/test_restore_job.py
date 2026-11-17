"""The restore as a background job, on the engine the session app runs on.

The conclusion matrix of test_background_jobs.py, for a real restore (replace and merge) of
an archive of the groups alone: each case asserts the final state and reason, exactly one
`system_restore` line, no secret, no archive file, no local gate left, the slot free, and
the database as the outcome says (the group restored, or not). Then the restore's own
properties: the mark in the transaction, the end steps replayed by the recovery, the commit
that raises, the cancellation that comes too late, the local write gate, the epoch purge.
"""
import io
import json
import os
import threading
import types
import uuid
from datetime import timedelta

import pytest
from flask import g
from sqlalchemy import func, select, update

from models import AuditLog, BackgroundJob, db
from services import jobs
from services.backup import manifest
from services.jobs import restore as restore_job
from services.jobs import runner, store

T = BackgroundJob.__table__
PASSWORD = 'Restore-Job-Password-9'
GROUP = 'restore-job-matrix-group'
ACTION = restore_job.ACTION


class HardStop(BaseException):
    """Not an Exception: what a thread sees of an interpreter going down."""


class Boom(Exception):
    pass


# -- fixtures and helpers ----------------------------------------------------------------

def _drop_group():
    from models.group import Group
    Group.query.filter_by(name=GROUP).delete()
    db.session.commit()


def _has_group():
    from models.group import Group
    found = Group.query.filter_by(name=GROUP).first() is not None
    db.session.rollback()
    return found


def _epoch():
    from auth.session_epoch import current_epoch
    value = current_epoch()
    db.session.rollback()
    return value


@pytest.fixture
def archive(app):
    """An archive of the groups alone that holds GROUP; the instance has lost it."""
    from models.group import Group
    from services.backup_service import BackupService
    with app.app_context():
        _drop_group()
        db.session.add(Group(name=GROUP))
        db.session.commit()
        blob = BackupService().create_backup(
            PASSWORD, include={name: name == 'groups' for name in manifest.SECTIONS})
        _drop_group()
    yield blob
    with app.app_context():
        _drop_group()


@pytest.fixture
def created(app):
    ids = []
    yield ids
    with app.app_context():
        for job_id in ids:
            runner.join_local(job_id, 30)
        db.session.execute(T.delete().where(T.c.id.in_(ids)))
        db.session.commit()
    restore_job.remove_state()


@pytest.fixture
def no_restart(monkeypatch):
    asked = []
    monkeypatch.setattr('services.backup.restore_completion.request_restart',
                        lambda: asked.append(1) or (True, 'Service restart initiated'))
    return asked


def _start(app, blob, created, mode='replace', password=PASSWORD):
    with app.test_request_context():
        g.current_user = types.SimpleNamespace(id=4343, username='restore-requester')
        g.user_id = 4343
        job_id = str(uuid.uuid4())
        name = restore_job.write_archive(job_id, io.BytesIO(blob))
        created.append(job_id)
        jobs.start_job(restore_job.KIND, params=restore_job.params_of('r.ucmbkp', 'r.ucmbkp', mode),
                       secret=password, file_name=name, job_id=job_id)
    return job_id, name


def _row(job_id):
    row = store.job_row(db.session, job_id)
    db.session.rollback()
    return row


def _lines():
    found = db.session.execute(select(func.count(AuditLog.id)).where(
        AuditLog.action == ACTION)).scalar()
    db.session.rollback()
    return found


def _named(job_id):
    found = [r[0] for r in db.session.execute(select(AuditLog.resource_name).where(
        AuditLog.action == ACTION, AuditLog.resource_id == job_id))]
    db.session.rollback()
    return found


def _lines_in(app):
    with app.app_context():
        return _lines()


def _assert_final(app, job_id, state, reason, before, file_name, restored):
    assert runner.join_local(job_id, 60)
    with app.app_context():
        row = _row(job_id)
        assert (row['state'], row['reason']) == (state, reason), row
        assert row['secret'] is None and row['lease_expires_at'] is None
        assert _lines() - before == 1
        # Every result line of a restore names its archive, whoever concludes it
        assert _named(job_id) == ['r.ucmbkp']
        assert not store.active_jobs(db.session)
        db.session.rollback()
        assert _has_group() is restored
    assert not os.path.exists(os.path.join(store.jobs_tmp_dir(), file_name))
    assert restore_job.read_state() is None, 'the local write gate stayed up'
    return row


class Hold:
    """Stops the run at its ``at``-th checkpoint of ``kind`` ('progress' or a core step)."""

    def __init__(self, monkeypatch, at=None, step=None, fail=None):
        self.at, self.step, self.fail, self.calls = at, step, fail, 0
        self.reached, self.release = threading.Event(), threading.Event()
        hold = self
        if step is None:
            real = runner.JobContext.progress

            def progress(ctx, *args, **kwargs):
                hold.calls += 1
                if hold.calls == hold.at:
                    hold._stop()
                return real(ctx, *args, **kwargs)
            monkeypatch.setattr(runner.JobContext, 'progress', progress)
        else:
            real_check = restore_job._Run.checkpoint

            def checkpoint(run, name):
                if name == hold.step and not hold.reached.is_set():
                    hold._stop()
                return real_check(run, name)
            monkeypatch.setattr(restore_job._Run, 'checkpoint', checkpoint)

    def _stop(self):
        self.reached.set()
        assert self.release.wait(30)
        if self.fail is not None:
            raise self.fail

    def wait(self):
        assert self.reached.wait(30), 'the run never reached the hold'


MODES = ['replace', 'merge']


# -- the matrix --------------------------------------------------------------------------

@pytest.mark.parametrize('mode', MODES)
def test_a_restore_runs_to_the_end(app, archive, created, no_restart, mode):
    before, epoch = _lines_in(app), None
    with app.app_context():
        epoch = _epoch()
    job_id, name = _start(app, archive, created, mode)
    row = _assert_final(app, job_id, 'succeeded', 'done', before, name, True)
    assert row['phase'] == restore_job.CRLS
    result = json.loads(row['result'])
    assert result['code'] == 200 and result['data']['restart_requested'] is True
    assert set(result['data']['invalidated']) >= {'sessions_revoked', 'caches_cleared',
                                                  'crls_regenerated', 'session_files_removed'}
    with app.app_context():
        assert _epoch() == epoch + 1
    assert no_restart == [1]


def test_a_refused_restore_restores_nothing(app, archive, created):
    before = _lines_in(app)
    job_id, name = _start(app, archive, created, password='Not-The-Password-1')
    _assert_final(app, job_id, 'failed', 'refused', before, name, False)


@pytest.mark.filterwarnings('ignore::pytest.PytestUnhandledThreadExceptionWarning')
@pytest.mark.parametrize('mode', MODES)
@pytest.mark.parametrize('at', [1, 3], ids=['taken', 'middle'])
@pytest.mark.parametrize('failure', [Boom('disk full'), HardStop()], ids=['exception', 'base_exception'])
def test_a_failure_before_the_commit_restores_nothing(app, archive, created, monkeypatch, mode, at,
                                                    failure):
    hold = Hold(monkeypatch, at=at, fail=failure)
    hold.release.set()
    before = _lines_in(app)
    job_id, name = _start(app, archive, created, mode)
    _assert_final(app, job_id, 'failed', 'error', before, name, False)


@pytest.mark.parametrize('mode', MODES)
@pytest.mark.parametrize('at', [1, 3], ids=['taken', 'middle'])
def test_a_cancellation_before_the_transaction_restores_nothing(app, archive, created, monkeypatch,
                                                              mode, at):
    hold = Hold(monkeypatch, at=at)
    before = _lines_in(app)
    job_id, name = _start(app, archive, created, mode)
    hold.wait()
    with app.app_context():
        assert jobs.request_cancellation(job_id) == 'requested'
    hold.release.set()
    _assert_final(app, job_id, 'cancelled', 'cancelled', before, name, False)


@pytest.mark.parametrize('mode', MODES)
def test_a_cancellation_inside_the_transaction_rolls_it_back(app, archive, created, monkeypatch,
                                                           mode):
    """SQLite: the transaction holds the database, the request is a local flag; PostgreSQL:
    the flag on the row. Either way the next checkpoint stops the restore and rolls back."""
    hold = Hold(monkeypatch, step='rbac')
    before = _lines_in(app)
    job_id, name = _start(app, archive, created, mode)
    hold.wait()
    with app.app_context():
        assert jobs.request_cancellation(job_id) == 'requested'
    hold.release.set()
    _assert_final(app, job_id, 'cancelled', 'cancelled', before, name, False)
    assert not restore_job.cancel_flagged(job_id), 'the cancellation flag was left behind'


def test_a_pending_restore_cancels_at_once(app, archive, created, monkeypatch):
    monkeypatch.setattr(runner, 'dispatch_job', lambda job_id: None)
    before = _lines_in(app)
    job_id, name = _start(app, archive, created)
    with app.app_context():
        assert _row(job_id)['secret'] not in (None, PASSWORD)  # encrypted while it waits
        assert jobs.request_cancellation(job_id) == 'cancelled'
    _assert_final(app, job_id, 'cancelled', 'cancelled', before, name, False)


def test_a_restore_nobody_takes_ends_not_taken(app, archive, created, monkeypatch):
    monkeypatch.setattr(runner, 'dispatch_job', lambda job_id: None)
    before = _lines_in(app)
    job_id, name = _start(app, archive, created)
    with app.app_context():
        later = jobs._now() + timedelta(seconds=store.NOT_TAKEN_SECONDS + 1)
        store.recover_orphans(db.session, now=later, all_running=False, audit_for=jobs.audit_writer,
                              resume_for=jobs.resumer, executor='recovery/1/x')
    _assert_final(app, job_id, 'failed', 'not_taken', before, name, False)


@pytest.mark.parametrize('lapsed', [False, True], ids=['single_node_start', 'lapsed_lease'])
def test_a_restore_lost_before_its_commit_failed_and_restored_nothing(app, archive, created,
                                                                     monkeypatch, lapsed):
    monkeypatch.setattr(runner, 'dispatch_job', lambda job_id: None)
    before = _lines_in(app)
    job_id, name = _start(app, archive, created)
    with app.app_context():
        assert store.claim_job(db.session, job_id, 'lost/1/x', jobs._now()) is not None
        now = jobs._now() + (timedelta(seconds=store.LEASE_SECONDS + 1) if lapsed else timedelta())
        store.recover_orphans(db.session, now=now, all_running=not lapsed,
                              audit_for=jobs.audit_writer, resume_for=jobs.resumer,
                              executor='recovery/1/x')
    row = _assert_final(app, job_id, 'failed', 'executor_lost', before, name, False)
    assert 'nothing was restored' in jobs.job_type('restore').messages['executor_lost']
    assert row['phase'] not in restore_job.VALIDATED


# -- after the commit: every end step replayed once ------------------------------------

STEP_FUNCTIONS = [
    # The first thing after the restore returns: only the mark in its transaction says it committed
    ('services.backup.restore_report.safe_restore_audit_details', restore_job.COMMITTED),
    ('services.backup.restore.invalidate.revoke_sessions_with', restore_job.COMMITTED),
    ('services.backup.restore.invalidate.remove_session_files', restore_job.SESSIONS),
    ('services.backup.restore.invalidate.purge_caches', restore_job.SESSION_FILES),
    ('services.backup.restore.invalidate.regenerate_crls_summary', restore_job.CACHES),
    ('services.jobs.restore._conclude', restore_job.CRLS),
]


@pytest.mark.filterwarnings('ignore::pytest.PytestUnhandledThreadExceptionWarning')
@pytest.mark.parametrize('target, phase', STEP_FUNCTIONS,
                         ids=['returned'] + [p for _, p in STEP_FUNCTIONS[1:]])
def test_an_executor_lost_after_the_commit_is_finished_by_the_recovery(
        app, archive, created, monkeypatch, no_restart, target, phase):
    """The executor dies before an end step (a BaseException is all a dying thread sees):
    the job stays running in the phase of the step before; the recovery finishes it, with
    the epoch advanced exactly once and exactly one audit line."""
    module, _, attribute = target.rpartition('.')
    import importlib
    loaded = importlib.import_module(module)
    real = getattr(loaded, attribute)
    died = []

    def dies(*args, **kwargs):
        if not died:
            died.append(1)
            raise HardStop()
        return real(*args, **kwargs)
    monkeypatch.setattr(loaded, attribute, dies)
    before = _lines_in(app)
    with app.app_context():
        epoch = _epoch()
    job_id, name = _start(app, archive, created)
    assert runner.join_local(job_id, 60)
    with app.app_context():
        row = _row(job_id)
        assert (row['state'], row['phase']) == ('running', phase)
        assert _lines() == before
        assert _has_group()
        store.recover_orphans(db.session, now=jobs._now(), all_running=True,
                              audit_for=jobs.audit_writer, resume_for=jobs.resumer,
                              executor='recovery/1/x')
    row = _assert_final(app, job_id, 'succeeded', 'done', before, name, True)
    assert row['phase'] == restore_job.CRLS
    with app.app_context():
        assert _epoch() == epoch + 1, 'the epoch was advanced twice, or never'
    assert no_restart == [1]


@pytest.mark.filterwarnings('ignore::pytest.PytestUnhandledThreadExceptionWarning')
def test_an_executor_lost_after_its_conclusion_leaves_the_job_final(app, archive, created,
                                                                   monkeypatch):
    """The state is written before the restart is asked: dying there loses only the restart."""
    def dies():
        raise HardStop()
    monkeypatch.setattr('services.backup.restore_completion.request_restart', dies)
    before = _lines_in(app)
    job_id, name = _start(app, archive, created)
    _assert_final(app, job_id, 'succeeded', 'done', before, name, True)


def test_the_mark_commits_and_rolls_back_with_the_restore(app, archive, created, monkeypatch):
    """The commit raises without reaching the database: the mark went with it, nothing is
    restored and the job fails; read again on a fresh connection, never from the exception."""
    _commit_raises(monkeypatch, reaches_the_database=False)
    before = _lines_in(app)
    job_id, name = _start(app, archive, created)
    row = _assert_final(app, job_id, 'failed', 'error', before, name, False)
    assert row['phase'] not in restore_job.VALIDATED


def test_a_commit_that_raises_after_the_database_has_it_finishes_the_restore(
        app, archive, created, monkeypatch, no_restart):
    _commit_raises(monkeypatch, reaches_the_database=True)
    before = _lines_in(app)
    job_id, name = _start(app, archive, created)
    row = _assert_final(app, job_id, 'succeeded', 'done', before, name, True)
    assert row['phase'] == restore_job.CRLS


def _commit_raises(monkeypatch, *, reaches_the_database):
    from sqlalchemy.orm import Session
    from services.backup.restore import transaction
    real_commit = Session.commit
    real_marking = transaction.marking

    def marking(mark):
        def flagged(session, report):
            mark(session, report)
            session.info['restore_commit'] = True
        return real_marking(flagged)

    def commit(self):
        if self.info.pop('restore_commit', False):
            if reaches_the_database:
                real_commit(self)
            raise RuntimeError('connection lost while committing')
        return real_commit(self)
    monkeypatch.setattr(transaction, 'marking', marking)
    monkeypatch.setattr(Session, 'commit', commit)


def test_a_cancellation_after_the_commit_is_too_late(app, archive, created, monkeypatch, no_restart):
    hold = Hold(monkeypatch)
    real = restore_job._finish_steps
    reached, release = threading.Event(), threading.Event()

    def held(job_id):
        reached.set()
        assert release.wait(30)
        return real(job_id)
    monkeypatch.setattr(restore_job, '_finish_steps', held)
    hold.release.set()
    before = _lines_in(app)
    job_id, name = _start(app, archive, created)
    assert reached.wait(30)
    with app.app_context():
        assert jobs.request_cancellation(job_id) == 'too_late'
        assert not _row(job_id)['cancel_requested']
    release.set()
    _assert_final(app, job_id, 'succeeded', 'done', before, name, True)


def test_a_flag_set_before_the_mark_rolls_the_restore_back(app, archive, created, monkeypatch):
    """The flag and the mark are conditional UPDATEs of one row: the flag won, the mark finds it.
    PostgreSQL only: on SQLite the transaction holds the database and the flag is local."""
    from services import cluster_maintenance
    with app.app_context():
        if db.engine.dialect.name == 'sqlite':
            pytest.skip('SQLite: no other connection writes during the restore transaction')
    hold = Hold(monkeypatch, step='relink')
    before = _lines_in(app)
    job_id, name = _start(app, archive, created)
    hold.wait()
    with app.app_context(), cluster_maintenance.exempt():
        db.session.execute(update(T).where(T.c.id == job_id).values(cancel_requested=True))
        db.session.commit()
    hold.release.set()
    _assert_final(app, job_id, 'cancelled', 'cancelled', before, name, False)


# -- the archive file ------------------------------------------------------------------

def test_the_archive_is_written_owner_only_before_the_job(app, created, monkeypatch):
    monkeypatch.setattr(runner, 'dispatch_job', lambda job_id: None)
    with app.app_context():
        job_id = str(uuid.uuid4())
        name = restore_job.write_archive(job_id, io.BytesIO(b'archive bytes' * 1000))
        path = os.path.join(store.jobs_tmp_dir(), name)
        try:
            assert oct(os.stat(path).st_mode & 0o777) == oct(0o600)
            assert oct(os.stat(store.jobs_tmp_dir()).st_mode & 0o777) == oct(0o700)
            with pytest.raises(FileExistsError):  # never through an existing name or link
                restore_job.write_archive(job_id, io.BytesIO(b'x'))
        finally:
            store.purge_file(name)


def test_a_sweep_between_the_file_and_the_row_fails_the_job_cleanly(app, archive, created,
                                                                   monkeypatch):
    """The route writes the file, then the row: a scheduler that starts in between removes the
    unknown file; the job then fails, nothing restored, nothing left."""
    real = jobs.start_job

    def swept_first(*args, **kwargs):
        with app.app_context():
            store.sweep_job_files(db.session, keep_unknown=False)
            db.session.rollback()
        return real(*args, **kwargs)
    monkeypatch.setattr(jobs, 'start_job', swept_first)
    before = _lines_in(app)
    job_id, name = _start(app, archive, created)
    row = _assert_final(app, job_id, 'failed', 'error', before, name, False)
    assert json.loads(row['result'])['message'] == restore_job.GONE


def test_a_pending_restore_file_survives_a_later_sweep(app, archive, created, monkeypatch):
    monkeypatch.setattr(runner, 'dispatch_job', lambda job_id: None)
    job_id, name = _start(app, archive, created)
    with app.app_context():
        store.sweep_job_files(db.session, keep_unknown=False)
        db.session.rollback()
        assert os.path.exists(os.path.join(store.jobs_tmp_dir(), name))
        jobs.request_cancellation(job_id)
    assert not os.path.exists(os.path.join(store.jobs_tmp_dir(), name))


def test_an_unknown_file_goes_after_an_hour_even_past_the_first_pass(app):
    with app.app_context():
        name = store.file_name_for(str(uuid.uuid4()), restore_job.ARCHIVE_SUFFIX)
        path = os.path.join(store.jobs_tmp_dir(), name)
        os.makedirs(store.jobs_tmp_dir(), exist_ok=True)
        with open(path, 'wb') as handle:
            handle.write(b'x')
        store.sweep_job_files(db.session, keep_unknown=True)
        assert os.path.exists(path)
        old = os.stat(path).st_mtime - store.UNKNOWN_FILE_SECONDS - 5
        os.utime(path, (old, old))
        store.sweep_job_files(db.session, keep_unknown=True)
        db.session.rollback()
        assert not os.path.exists(path)


# -- the write gate of a single node ------------------------------------------------------

def test_the_local_gate_refuses_writes_and_serves_reads_during_the_restore(
        app, auth_client, archive, created, monkeypatch, no_restart):
    from services import cluster_maintenance
    from services.scheduler_service import get_scheduler
    hold = Hold(monkeypatch, step='plan')
    before = _lines_in(app)
    assert auth_client.get('/api/v2/system/jobs').status_code == 200  # signed in before the gate
    job_id, name = _start(app, archive, created)
    hold.wait()
    try:
        write = auth_client.post('/api/v2/groups', json={'name': 'refused-during-restore'})
        assert write.status_code == 503, write.data
        assert write.headers['Retry-After'] == str(cluster_maintenance.RETRY_AFTER_SECONDS)
        assert write.get_json()['message'] == cluster_maintenance.LOCAL_MESSAGE
        assert auth_client.get('/api/v2/groups').status_code == 200
        assert auth_client.get('/health/live').status_code == 200
        seen = auth_client.get(f'/api/v2/system/jobs/{job_id}')
        assert seen.status_code == 200 and seen.get_json()['data']['state'] == 'running'
        # No job starts: the restore holds every slot, and the gate answers first
        busy = auth_client.post('/api/v2/system/restore', data={
            'file': (io.BytesIO(archive), 'r.ucmbkp'), 'password': PASSWORD},
            content_type='multipart/form-data')
        assert busy.status_code == 503
        scheduler = get_scheduler()
        monkeypatch.setattr(scheduler, '_app', app)
        assert scheduler._in_maintenance(), 'a scheduled task would write during the restore'
    finally:
        hold.release.set()
    _assert_final(app, job_id, 'succeeded', 'done', before, name, True)
    with app.app_context():
        assert not cluster_maintenance.current().active()


def test_a_gate_whose_executor_died_refuses_nothing(app, monkeypatch):
    from services import cluster_maintenance
    monkeypatch.setattr(restore_job, '_alive', lambda pid: False)
    restore_job._write_state({'job_id': 'x', 'pid': 1, 'expires': 4102444800, 'view': {}})
    try:
        with app.app_context():
            assert not cluster_maintenance.current().active()
    finally:
        restore_job.remove_state()


def test_the_job_is_read_from_its_local_state_when_the_database_is_held(
        app, auth_client, archive, created, monkeypatch):
    from sqlalchemy.exc import OperationalError
    import api.v2.system.jobs as routes
    hold = Hold(monkeypatch, step='plan')
    assert auth_client.get('/api/v2/system/jobs').status_code == 200  # signed in before the gate
    job_id, name = _start(app, archive, created)
    hold.wait()
    try:
        def locked(job_id):
            raise OperationalError('SELECT', {}, Exception('database is locked'))
        monkeypatch.setattr(routes, '_visible', locked)
        seen = auth_client.get(f'/api/v2/system/jobs/{job_id}')
        assert seen.status_code == 200, seen.data
        data = seen.get_json()['data']
        assert data['id'] == job_id and data['kind'] == 'restore'
        assert 'held' not in data and 'result' not in data
    finally:
        hold.release.set()
    assert runner.join_local(job_id, 60)


# -- every process purges its caches once the epoch moves (Q4) --------------------------------

def test_a_process_purges_its_caches_once_when_the_epoch_moves(app, monkeypatch):
    from auth.session_epoch import advance_epoch
    from services.backup.restore import invalidate
    purged = []
    monkeypatch.setattr(invalidate, 'purge_caches',
                        lambda with_tables=False: purged.append(with_tables) or ([], []))
    with app.app_context():
        invalidate.refresh_caches_on_epoch(force=True)
        assert purged == []
        advance_epoch()
        assert invalidate.refresh_caches_on_epoch(force=True)
        assert not invalidate.refresh_caches_on_epoch(force=True)
    assert purged == [False], 'a process purged the cache tables, or purged twice'


def test_a_web_worker_purges_on_its_own_timer_without_a_request(app, monkeypatch):
    import time

    from auth.session_epoch import advance_epoch
    from services.backup.restore import invalidate
    purged = []
    monkeypatch.setattr(invalidate, 'purge_caches',
                        lambda with_tables=False: purged.append(with_tables) or ([], []))
    with app.app_context():
        invalidate.note_purged_epoch()
        advance_epoch()
    invalidate.start_epoch_watcher(app, interval=0.05)
    try:
        deadline = time.monotonic() + 10
        while not purged and time.monotonic() < deadline:
            time.sleep(0.05)
    finally:
        invalidate.stop_epoch_watcher()
    assert purged == [False]


# -- a real process killed around the commit (no application loaded in the child) --------------

CHILD = r'''
import os, signal, sys
sys.path.insert(0, sys.argv[1])
from sqlalchemy import create_engine, text
assert 'config.settings' not in sys.modules and 'app' not in sys.modules
url, when = sys.argv[2], sys.argv[3]
engine = create_engine(url)
conn = engine.connect()
tx = conn.begin()
conn.execute(text("INSERT INTO restored (name) VALUES ('group')"))
conn.execute(text("UPDATE background_jobs SET phase = 'committed' WHERE id = 'j' "
                  "AND state = 'running' AND cancel_requested = 0"))
if when == 'after':
    tx.commit()
os.kill(os.getpid(), signal.SIGKILL)
'''


@pytest.mark.parametrize('when', ['before', 'after'])
def test_a_process_killed_around_the_commit_leaves_the_mark_with_the_data(tmp_path, when):
    import subprocess
    import sys
    from sqlalchemy import create_engine, text
    from utils.datetime_utils import utc_now
    backend = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    url = f'sqlite:///{tmp_path / "kill.db"}'
    engine = create_engine(url)
    BackgroundJob.__table__.create(engine)
    with engine.begin() as conn:
        conn.execute(text("CREATE TABLE restored (name TEXT)"))
        conn.execute(T.insert().values(id='j', kind='restore', slot='restore', state='running',
                                       cancel_requested=False, created_at=utc_now()))
    env = {k: v for k, v in os.environ.items() if not k.startswith('GIT_')}
    env['PYTHONPATH'] = backend
    child = subprocess.run([sys.executable, '-c', CHILD, backend, url, when], env=env, timeout=60)
    assert child.returncode == -9
    with engine.connect() as conn:
        restored = conn.execute(text("SELECT count(*) FROM restored")).scalar()
        phase = conn.execute(select(T.c.phase).where(T.c.id == 'j')).scalar()
    engine.dispose()
    assert (restored, phase) == ((1, 'committed') if when == 'after' else (0, None))


# -- PostgreSQL, two connections: the races the row lock decides --------------------------------

@pytest.fixture
def pg_jobs():
    """(engine) of a PostgreSQL schema holding only background_jobs."""
    from sqlalchemy import create_engine, text
    url = os.getenv('UCM_TEST_PG_URL')
    if not url:
        pytest.skip('UCM_TEST_PG_URL not set')
    schema = f"restore_job_{os.getenv('PYTEST_XDIST_WORKER', 'main')}"
    admin = create_engine(url)
    with admin.begin() as conn:
        conn.execute(text(f'DROP SCHEMA IF EXISTS {schema} CASCADE'))
        conn.execute(text(f'CREATE SCHEMA {schema}'))
    engine = create_engine(url, connect_args={'options': f'-csearch_path={schema}'})
    BackgroundJob.__table__.create(engine)
    yield engine
    engine.dispose()
    with admin.begin() as conn:
        conn.execute(text(f'DROP SCHEMA IF EXISTS {schema} CASCADE'))
    admin.dispose()


def _pg_job(engine, phase):
    from utils.datetime_utils import utc_now
    with engine.begin() as conn:
        conn.execute(T.insert().values(id='j', kind='restore', slot='restore', state='running',
                                       phase=phase, executor='e', cancel_requested=False,
                                       created_at=utc_now(), result='{}'))


@pytest.mark.postgres
def test_two_actors_claim_the_sessions_step_once(pg_jobs):
    """The job's end and the HA maintenance's completion: one advances the epoch, the other
    finds it done, whichever commits first."""
    from sqlalchemy.orm import Session
    _pg_job(pg_jobs, restore_job.COMMITTED)
    first, second = Session(pg_jobs), Session(pg_jobs)
    try:
        assert restore_job.claim_sessions(first) == 'claimed'
        answers = []
        racer = threading.Thread(target=lambda: answers.append(restore_job.claim_sessions(second)))
        racer.start()
        racer.join(1.0)
        assert racer.is_alive(), 'the second claim did not wait for the row lock'
        first.commit()
        racer.join(10)
        assert answers == ['done']
    finally:
        first.close()
        second.rollback()
        second.close()


@pytest.mark.postgres
@pytest.mark.parametrize('first', ['cancel', 'mark'])
def test_the_cancellation_and_the_mark_never_both_win(pg_jobs, first):
    from sqlalchemy.orm import Session
    from utils.datetime_utils import utc_now
    _pg_job(pg_jobs, restore_job.APPLYING)
    mark, flag = Session(pg_jobs), Session(pg_jobs)
    marked = lambda: mark.execute(update(T).where(  # noqa: E731
        T.c.id == 'j', T.c.state == 'running', T.c.cancel_requested.is_(False)).values(
        phase=restore_job.COMMITTED)).rowcount
    try:
        if first == 'mark':
            assert marked() == 1
            answers = []
            racer = threading.Thread(target=lambda: answers.append(store.cancel_or_flag(
                flag, 'j', utc_now(), past=restore_job.VALIDATED)))
            racer.start()
            racer.join(1.0)
            assert racer.is_alive(), 'the cancellation did not wait for the restore transaction'
            mark.commit()
            racer.join(10)
            assert answers == ['too_late']
        else:
            assert store.cancel_or_flag(flag, 'j', utc_now(), past=restore_job.VALIDATED) == 'requested'
            assert marked() == 0
            mark.rollback()
    finally:
        mark.close()
        flag.close()
