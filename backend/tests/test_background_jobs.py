"""Background jobs: the conclusion matrix on the engine the session app runs on.

Every case ends a job one way and checks the same things: its final state and reason,
exactly one audit line for a job that writes them (none for the audit verification), no
secret and no file left, its slot free again. Operations: the audit verification, and a
fake job on the backup and restore slots that later sub-lots replace with their own.
"""
import os
import threading
import types
from datetime import timedelta

import pytest
from flask import g
from sqlalchemy import func, select, update

from models import AuditLog, BackgroundJob, db
from services import jobs
from services.audit_service import AuditService
from services.jobs import runner, store
from services.jobs import JobOutcome, JobType

FAKE_ACTION = 'test_fake_job'
T = BackgroundJob.__table__


class Boom(Exception):
    pass


class HardStop(BaseException):
    """Not an Exception: what a thread sees of an interpreter going down."""


def _fake_run(ctx):
    ctx.seen_secret = ctx.secret
    _SEEN['secret'] = ctx.secret
    ctx.progress(done=0, total=3, phase='working')
    for page in (1, 2, 3):
        ctx.progress(done=page)
    return JobOutcome(code=200, message='Fake done', data={'pages': 3},
                      audit_details='Fake job finished')


_SEEN = {}


@pytest.fixture
def fake_types():
    made = [jobs.register(JobType(kind=f'test_fake_{slot}', slot=slot, permission='admin:system',
                                  run=_fake_run, label=f'Fake {slot}', audit_action=FAKE_ACTION))
            for slot in (jobs.SLOT_BACKUP, jobs.SLOT_RESTORE)]
    yield {jt.slot: jt.kind for jt in made}
    for jt in made:
        jobs.unregister(jt.kind)


@pytest.fixture
def created(app):
    """The ids of the jobs a test made: concluded if still active, then deleted."""
    ids = []
    yield ids
    with app.app_context():
        for job_id in ids:
            runner.join_local(job_id, 10)
        db.session.execute(T.delete().where(T.c.id.in_(ids)))
        db.session.commit()


class Gate:
    """Stops the run at its ``at``-th progress call, before it reaches the database."""

    def __init__(self, monkeypatch, at, fail=None):
        self.at, self.fail, self.calls = at, fail, 0
        self.reached, self.release = threading.Event(), threading.Event()
        real = runner.JobContext.progress
        gate = self

        def progress(ctx, *args, **kwargs):
            gate.calls += 1
            if gate.calls == gate.at:
                gate.reached.set()
                assert gate.release.wait(10)
                if gate.fail is not None:
                    raise gate.fail
            return real(ctx, *args, **kwargs)
        monkeypatch.setattr(runner.JobContext, 'progress', progress)

    def wait(self):
        assert self.reached.wait(10), 'the run never reached the gate'


def _audit_lines():
    found = db.session.execute(select(func.count(AuditLog.id)).where(
        AuditLog.action == FAKE_ACTION)).scalar()
    db.session.rollback()
    return found


def _start(app, kind, created, secret=None, with_file=False, params=None):
    with app.test_request_context():
        g.current_user = types.SimpleNamespace(id=4242, username='job-requester')
        g.user_id = 4242
        name = None
        if with_file:
            job_file_id = str(__import__('uuid').uuid4())
            name = store.file_name_for(job_file_id, '.upload')
            os.makedirs(store.jobs_tmp_dir(), exist_ok=True)
            with open(os.path.join(store.jobs_tmp_dir(), name), 'wb') as handle:
                handle.write(b'archive bytes')
            job_id = jobs.start_job(kind, params=params, secret=secret, file_name=name, job_id=job_file_id)
        else:
            job_id = jobs.start_job(kind, params=params, secret=secret)
    created.append(job_id)
    return job_id, name


def _row(job_id):
    row = store.job_row(db.session, job_id)
    db.session.rollback()
    return row


def _assert_final(app, job_id, state, reason, lines_before, lines, file_name=None):
    assert runner.join_local(job_id, 10)
    with app.app_context():
        row = _row(job_id)
        assert (row['state'], row['reason']) == (state, reason)
        assert row['secret'] is None and row['lease_expires_at'] is None
        assert row['finished_at'] is not None
        assert _audit_lines() - lines_before == lines
        assert not [r for r in store.active_jobs(db.session, row['slot'])]
        db.session.rollback()
    if file_name:
        assert not os.path.exists(os.path.join(store.jobs_tmp_dir(), file_name))


def _audit_rows(app, count=7):
    with app.app_context():
        for i in range(count):
            AuditService.log_action(action='test_job_matrix_row', details=f'row {i}')


# -- the matrix -------------------------------------------------------------------------

OPERATIONS = ['fake_backup', 'fake_restore', 'verify']


@pytest.fixture
def operation(request, app, fake_types, monkeypatch):
    name = request.param
    if name == 'verify':
        import services.audit.core as core
        monkeypatch.setattr(core, 'VERIFY_PAGE', 2)
        _audit_rows(app)
        return types.SimpleNamespace(kind='audit_verify', lines=0, slot=jobs.SLOT_AUDIT_VERIFY,
                                     secret=None, with_file=False)
    slot = jobs.SLOT_BACKUP if name == 'fake_backup' else jobs.SLOT_RESTORE
    return types.SimpleNamespace(kind=fake_types[slot], lines=1, slot=slot, secret='archive-pw',
                                 with_file=True)


@pytest.mark.parametrize('operation', OPERATIONS, indirect=True)
def test_a_job_that_runs_to_the_end(app, operation, created):
    before = _audit_lines_in(app)
    job_id, name = _start(app, operation.kind, created, operation.secret, operation.with_file)
    _assert_final(app, job_id, 'succeeded', 'done', before, operation.lines, name)
    with app.app_context():
        row = _row(job_id)
    assert row['progress_done'] == row['progress_total']
    if operation.secret:
        assert _SEEN.pop('secret') == operation.secret


def _audit_lines_in(app):
    with app.app_context():
        return _audit_lines()


# (gate position, failure): 1 = taken, before its first effect; 3 = after two pages
POINTS = [(1, 'taken'), (3, 'middle')]


@pytest.mark.filterwarnings('ignore::pytest.PytestUnhandledThreadExceptionWarning')
@pytest.mark.parametrize('operation', OPERATIONS, indirect=True)
@pytest.mark.parametrize('at', [p[0] for p in POINTS], ids=[p[1] for p in POINTS])
@pytest.mark.parametrize('failure', [Boom('disk full'), HardStop()], ids=['exception', 'base_exception'])
def test_a_failure_in_the_thread_fails_the_job(app, operation, created, monkeypatch, at, failure):
    gate = Gate(monkeypatch, at, fail=failure)
    gate.release.set()
    before = _audit_lines_in(app)
    job_id, name = _start(app, operation.kind, created, operation.secret, operation.with_file)
    _assert_final(app, job_id, 'failed', 'error', before, operation.lines, name)


@pytest.mark.parametrize('operation', OPERATIONS, indirect=True)
@pytest.mark.parametrize('at', [p[0] for p in POINTS], ids=[p[1] for p in POINTS])
def test_a_cancellation_stops_a_running_job(app, operation, created, monkeypatch, at):
    gate = Gate(monkeypatch, at)
    before = _audit_lines_in(app)
    job_id, name = _start(app, operation.kind, created, operation.secret, operation.with_file)
    gate.wait()
    with app.app_context():
        assert jobs.request_cancellation(job_id) == 'requested'
        assert _row(job_id)['state'] == 'running'
    gate.release.set()
    _assert_final(app, job_id, 'cancelled', 'cancelled', before, operation.lines, name)


@pytest.mark.parametrize('operation', OPERATIONS, indirect=True)
def test_a_pending_job_cancels_at_once(app, operation, created, monkeypatch):
    monkeypatch.setattr(runner, 'dispatch_job', lambda job_id: None)  # no executor yet
    before = _audit_lines_in(app)
    job_id, name = _start(app, operation.kind, created, operation.secret, operation.with_file)
    with app.app_context():
        if operation.secret:  # encrypted while it waits
            assert _row(job_id)['secret'] not in (None, operation.secret)
        assert jobs.request_cancellation(job_id) == 'cancelled'
        assert jobs.request_cancellation(job_id) == 'final'
    _assert_final(app, job_id, 'cancelled', 'cancelled', before, operation.lines, name)


@pytest.mark.parametrize('operation', OPERATIONS, indirect=True)
def test_a_job_nobody_takes_ends_not_taken(app, operation, created, monkeypatch):
    monkeypatch.setattr(runner, 'dispatch_job', lambda job_id: None)
    before = _audit_lines_in(app)
    job_id, name = _start(app, operation.kind, created, operation.secret, operation.with_file)
    with app.app_context():
        now = jobs._now()
        # Not yet past the delay: left alone
        assert store.recover_orphans(db.session, now=now, all_running=False, audit_for=jobs.audit_writer) == 0
        later = now + timedelta(seconds=store.NOT_TAKEN_SECONDS + 1)
        assert store.recover_orphans(db.session, now=later, all_running=False, audit_for=jobs.audit_writer) == 1
    _assert_final(app, job_id, 'failed', 'not_taken', before, operation.lines, name)


def _taken_by_a_lost_executor(app, operation, created, monkeypatch):
    monkeypatch.setattr(runner, 'dispatch_job', lambda job_id: None)
    job_id, name = _start(app, operation.kind, created, operation.secret, operation.with_file)
    with app.app_context():
        assert store.claim_job(db.session, job_id, 'lost-node/1/x', jobs._now()) is not None
        assert _row(job_id)['secret'] is None  # cleared by the take itself
    return job_id, name


@pytest.mark.parametrize('operation', OPERATIONS, indirect=True)
def test_a_single_node_start_concludes_every_running_job(app, operation, created, monkeypatch):
    before = _audit_lines_in(app)
    job_id, name = _taken_by_a_lost_executor(app, operation, created, monkeypatch)
    with app.app_context():
        assert store.recover_orphans(db.session, now=jobs._now(), all_running=True,
                             audit_for=jobs.audit_writer) >= 1
    _assert_final(app, job_id, 'failed', 'executor_lost', before, operation.lines, name)


@pytest.mark.parametrize('operation', OPERATIONS, indirect=True)
def test_a_lapsed_lease_concludes_the_job_and_only_then(app, operation, created, monkeypatch):
    before = _audit_lines_in(app)
    job_id, name = _taken_by_a_lost_executor(app, operation, created, monkeypatch)
    with app.app_context():
        now = jobs._now()
        assert store.recover_orphans(db.session, now=now, all_running=False, audit_for=jobs.audit_writer) == 0
        assert _row(job_id)['state'] == 'running'
        later = now + timedelta(seconds=store.LEASE_SECONDS + 1)
        assert store.recover_orphans(db.session, now=later, all_running=False, audit_for=jobs.audit_writer) == 1
    _assert_final(app, job_id, 'failed', 'executor_lost', before, operation.lines, name)


@pytest.mark.parametrize('operation', OPERATIONS, indirect=True)
def test_a_run_concluded_elsewhere_never_concludes_twice(app, operation, created, monkeypatch):
    """The reaper wins while the run is held mid-way: the run stops at its next progress."""
    gate = Gate(monkeypatch, 3)
    before = _audit_lines_in(app)
    job_id, name = _start(app, operation.kind, created, operation.secret, operation.with_file)
    gate.wait()
    with app.app_context():
        later = jobs._now() + timedelta(seconds=store.LEASE_SECONDS + 1)
        assert store.recover_orphans(db.session, now=later, all_running=False, audit_for=jobs.audit_writer) == 1
    gate.release.set()
    _assert_final(app, job_id, 'failed', 'executor_lost', before, operation.lines, name)


def test_the_conclusion_is_undone_when_its_audit_line_is_not_written(app, fake_types, created,
                                                                    monkeypatch):
    monkeypatch.setattr(runner, 'dispatch_job', lambda job_id: None)
    job_id, _ = _start(app, fake_types[jobs.SLOT_BACKUP], created)
    with app.app_context():
        assert not store.conclude_job(db.session, job_id, state='cancelled', reason='cancelled',
                                  from_states=('pending',), now=jobs._now(),
                                  result_line=lambda row, state, reason: False)
        assert _row(job_id)['state'] == 'pending'
        assert jobs.request_cancellation(job_id) == 'cancelled'


def test_the_audit_line_names_the_requester(app, fake_types, created):
    job_id, _ = _start(app, fake_types[jobs.SLOT_BACKUP], created)
    assert runner.join_local(job_id, 10)
    with app.app_context():
        line = AuditLog.query.filter_by(action=FAKE_ACTION).order_by(AuditLog.id.desc()).first()
        assert (line.username, line.resource_id) == ('job-requester', job_id)
        assert line.details == 'Fake job finished' and line.success
        db.session.rollback()


# -- slots ------------------------------------------------------------------------------

def test_one_active_job_per_slot_and_a_restore_excludes_all(app, fake_types, created, monkeypatch):
    monkeypatch.setattr(runner, 'dispatch_job', lambda job_id: None)
    backup, _ = _start(app, fake_types[jobs.SLOT_BACKUP], created)
    with pytest.raises(jobs.SlotBusy) as busy:
        _start(app, fake_types[jobs.SLOT_BACKUP], created)
    assert busy.value.job['id'] == backup and busy.value.job['requested_by_name'] == 'job-requester'
    with pytest.raises(jobs.SlotBusy) as busy:
        _start(app, fake_types[jobs.SLOT_RESTORE], created)
    assert busy.value.job['id'] == backup
    verify, _ = _start(app, 'audit_verify', created)  # another slot: runs beside the backup
    with app.app_context():
        for job_id in (backup, verify):
            assert jobs.request_cancellation(job_id) == 'cancelled'
    restore, _ = _start(app, fake_types[jobs.SLOT_RESTORE], created)
    for kind in (fake_types[jobs.SLOT_BACKUP], 'audit_verify', fake_types[jobs.SLOT_RESTORE]):
        with pytest.raises(jobs.SlotBusy) as busy:
            _start(app, kind, created)
        assert busy.value.job['id'] == restore
    with app.app_context():
        assert jobs.request_cancellation(restore) == 'cancelled'
    again, _ = _start(app, fake_types[jobs.SLOT_BACKUP], created)
    with app.app_context():
        assert jobs.request_cancellation(again) == 'cancelled'


def test_the_unique_index_alone_refuses_a_second_active_job(app, fake_types, created, monkeypatch):
    monkeypatch.setattr(runner, 'dispatch_job', lambda job_id: None)
    monkeypatch.setattr(store, '_conflict', lambda *a: None)
    first, _ = _start(app, fake_types[jobs.SLOT_BACKUP], created)
    with pytest.raises(jobs.SlotBusy) as busy:
        _start(app, fake_types[jobs.SLOT_BACKUP], created)
    assert busy.value.job['id'] == first
    with app.app_context():
        assert jobs.request_cancellation(first) == 'cancelled'


def test_an_unknown_slot_is_refused():
    with pytest.raises(ValueError):
        jobs.register(JobType(kind='test_bad', slot='nowhere', permission='admin:system',
                              run=_fake_run, label='Bad'))


# -- the scheduler process's runner ----------------------------------------------------

class _Scheduler:
    def __init__(self, leads=True):
        self.leads = leads

    def holds_lock(self):
        return self.leads

    def _in_maintenance(self):
        return False


def _create_pending(app, kind, created, node_id=None):
    with app.app_context():
        jt = jobs.job_type(kind)
        job_id = store.create_job(db.session, kind=kind, slot=jt.slot, exclusive=False,
                              exclusive_slots=jobs.EXCLUSIVE_SLOTS, now=jobs._now(),
                              node_id=node_id)
    created.append(job_id)
    return job_id


def test_the_runner_recovers_orphans_on_its_first_pass_then_takes_jobs(app, fake_types, created):
    orphan = _create_pending(app, fake_types[jobs.SLOT_RESTORE], created)
    with app.app_context():
        store.claim_job(db.session, orphan, 'previous-process', jobs._now())
    jr = runner.JobRunner(app, _Scheduler())
    with app.app_context():
        jr.run_pass()
        assert _row(orphan)['reason'] == 'executor_lost'
        waiting = _create_pending(app, fake_types[jobs.SLOT_BACKUP], created)
        jr.run_pass()
    assert jr.join(10)
    with app.app_context():
        row = _row(waiting)
    assert (row['state'], row['executor']) == ('succeeded', jr.executor)


def test_a_runner_that_does_not_lead_takes_only_its_own_node_jobs(app, fake_types, created,
                                                                monkeypatch):
    import utils.ha
    monkeypatch.setattr(utils.ha, 'ha_enabled', lambda: True)
    other = _create_pending(app, fake_types[jobs.SLOT_BACKUP], created, node_id='another-node')
    jr = runner.JobRunner(app, _Scheduler(leads=False))
    with app.app_context():
        jr.run_pass()
        assert _row(other)['state'] == 'pending'
        jobs.request_cancellation(other)
        mine = _create_pending(app, fake_types[jobs.SLOT_BACKUP], created, node_id=jobs._node_id())
        unbound = _create_pending(app, 'audit_verify', created)
        jr.run_pass()
    assert jr.join(10)
    with app.app_context():
        assert _row(mine)['state'] == 'succeeded'
        assert _row(unbound)['state'] == 'pending'  # the leader's
        jobs.request_cancellation(unbound)


def test_a_job_whose_thread_died_unconcluded_is_concluded_by_its_runner(app, fake_types, created,
                                                                       monkeypatch):
    monkeypatch.setattr(runner, 'run_job', lambda *a, **k: None)  # dies without concluding
    job_id = _create_pending(app, fake_types[jobs.SLOT_BACKUP], created)
    jr = runner.JobRunner(app, _Scheduler())
    jr._recovered = True
    with app.app_context():
        jr.run_pass()
        assert jr.join(5)
        assert _row(job_id)['state'] == 'running'
        jr.run_pass()
        assert _row(job_id)['reason'] == 'executor_lost'


def test_purge_keeps_thirty_days_and_the_latest_of_each_kind(app, fake_types, created, monkeypatch):
    monkeypatch.setattr(runner, 'dispatch_job', lambda job_id: None)
    kind = fake_types[jobs.SLOT_BACKUP]

    def finished(days_ago):
        job_id, _ = _start(app, kind, created)
        with app.app_context():
            jobs.request_cancellation(job_id)
            at = jobs._now() - timedelta(days=days_ago)
            db.session.execute(update(T).where(T.c.id == job_id).values(created_at=at, finished_at=at))
            db.session.commit()
        return job_id
    oldest, old, latest = finished(40), finished(35), finished(31)
    with app.app_context():
        store.purge_finished(db.session, jobs._now())
        # The latest of its kind stays, however old
        assert _row(oldest) is None and _row(old) is None and _row(latest) is not None
    recent = finished(2)
    with app.app_context():
        store.purge_finished(db.session, jobs._now())
        assert _row(latest) is None and _row(recent) is not None


def test_the_start_sweep_keeps_active_jobs_files_only(app, fake_types, created, monkeypatch,
                                                      tmp_path):
    monkeypatch.setattr(runner, 'dispatch_job', lambda job_id: None)
    active_id, active_name = _start(app, fake_types[jobs.SLOT_BACKUP], created, with_file=True)
    unknown = store.file_name_for('0' * 8 + '-0000-0000-0000-' + '0' * 12, '.upload')
    directory = store.jobs_tmp_dir()
    with open(os.path.join(directory, unknown), 'w') as handle:
        handle.write('left over')
    target = tmp_path / 'outside'
    target.write_text('not ours')
    linked = store.file_name_for('1' * 8 + '-0000-0000-0000-' + '1' * 12)
    os.symlink(target, os.path.join(directory, linked))
    try:
        with app.app_context():
            store.sweep_job_files(db.session)
            db.session.rollback()
        assert os.path.exists(os.path.join(directory, active_name))
        assert not os.path.exists(os.path.join(directory, unknown))
        assert target.read_text() == 'not ours'
    finally:
        os.unlink(os.path.join(directory, linked))
        with app.app_context():
            jobs.request_cancellation(active_id)


# -- the verification by pages ------------------------------------------------------------

def test_pages_change_nothing_in_the_report(app, monkeypatch):
    import services.audit.core as core
    _audit_rows(app, 5)
    with app.app_context():
        whole = AuditService.verify_integrity()
        monkeypatch.setattr(core, 'VERIFY_PAGE', 2)
        pages = []
        paged = AuditService.verify_integrity(on_page=pages.append)
    assert paged == whole
    assert pages and pages == sorted(pages) and pages[-1] <= whole['checked']


def test_a_purge_during_the_walk_starts_it_again(app, monkeypatch):
    import services.audit.core as core
    walks = []
    real = core.verify_chain

    def counting(logs, whole_table):
        walks.append(whole_table)
        return dict(real(logs, whole_table), walk=len(walks))
    monkeypatch.setattr(core, 'verify_chain', counting)
    firsts = iter([5, 9, 9, 9])  # before, after the first walk (purged), around the second
    monkeypatch.setattr(core, '_first_entry_id', lambda conditions: next(firsts))
    with app.app_context():
        report = AuditService.verify_integrity()
    assert report['walk'] == 2 and len(walks) == 2
