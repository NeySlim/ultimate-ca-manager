"""A restore job's checkpoints inside its loops of rows, on the engine the session app runs on.

A cancellation asked in the middle of a loop is taken before the loop ends, nothing is
restored, and the progress reported meanwhile counts the rows written. The row checkpoint is
braked by time: between two reports a row costs a clock read, never a database round trip.
PostgreSQL application: listed in scripts/ci/pg-app-tests.txt.
"""
import io
import os
import threading
import time
import types
import uuid

import pytest
from flask import g
from sqlalchemy import func, select

from models import BackgroundJob, db
from services import jobs
from services.backup import manifest
from services.jobs import restore as restore_job
from services.jobs import runner, store

T = BackgroundJob.__table__
PASSWORD = 'Restore-Rows-Password-9'
PREFIX = 'restore-rows-group-'
GROUPS = 3000
HOLD_AT = 1000


def _groups_here():
    from models.group import Group
    found = db.session.execute(select(func.count(Group.id)).where(
        Group.name.like(f'{PREFIX}%'))).scalar()
    db.session.rollback()
    return found


def _drop_groups():
    from models.group import Group
    Group.query.filter(Group.name.like(f'{PREFIX}%')).delete(synchronize_session=False)
    db.session.commit()


@pytest.fixture
def archive(app):
    """An archive of the groups alone holding GROUPS groups; the instance has lost them."""
    from models.group import Group
    from services.backup_service import BackupService
    with app.app_context():
        _drop_groups()
        db.session.add_all([Group(name=f'{PREFIX}{i:05d}') for i in range(GROUPS)])
        db.session.commit()
        blob = BackupService().create_backup(
            PASSWORD, include={name: name == 'groups' for name in manifest.SECTIONS})
        _drop_groups()
    yield blob
    with app.app_context():
        _drop_groups()


@pytest.fixture
def created(app):
    ids = []
    yield ids
    with app.app_context():
        for job_id in ids:
            runner.join_local(job_id, 60)
        db.session.execute(T.delete().where(T.c.id.in_(ids)))
        db.session.commit()
    restore_job.remove_state()


def _start(app, blob, created):
    with app.test_request_context():
        g.current_user = types.SimpleNamespace(id=4344, username='restore-rows-requester')
        g.user_id = 4344
        job_id = str(uuid.uuid4())
        name = restore_job.write_archive(job_id, io.BytesIO(blob))
        created.append(job_id)
        jobs.start_job(restore_job.KIND, params=restore_job.params_of('r.ucmbkp', 'r.ucmbkp'),
                       secret=PASSWORD, file_name=name, job_id=job_id)
    return job_id, name


class RowHold:
    """Counts the group rows the run writes, each a little slow; stops the run at HOLD_AT."""

    def __init__(self, monkeypatch):
        self.steps, self.rows, self.after = [], 0, 0
        self.reached, self.release = threading.Event(), threading.Event()
        hold = self
        real_check, real_row = restore_job._Run.checkpoint, restore_job._Run.row

        def checkpoint(run, step):
            hold.steps.append(step)
            return real_check(run, step)

        def row(run, applied=0, total=None):
            if applied and hold.steps and hold.steps[-1] == 'rbac':
                hold.rows += 1
                if hold.reached.is_set():
                    hold.after += 1
                time.sleep(0.001)
                if hold.rows == HOLD_AT:
                    hold.reached.set()
                    assert hold.release.wait(30)
            return real_row(run, applied, total)
        monkeypatch.setattr(restore_job._Run, 'checkpoint', checkpoint)
        monkeypatch.setattr(restore_job._Run, 'row', row)
        monkeypatch.setattr(restore_job, 'CHECK_SECONDS', 0.05)


def _reported(app, job_id):
    """(done, total) as a reader sees it: the row, or the local state the SQLite run keeps."""
    with app.app_context():
        if db.engine.dialect.name == 'sqlite':
            progress = (restore_job.read_state() or {}).get('view', {}).get('progress') or {}
            return progress.get('done'), progress.get('total')
        with db.engine.connect() as conn:
            row = store.job_row(conn, job_id)
        return row['progress_done'], row['progress_total']


def test_a_cancellation_in_the_middle_of_a_loop_is_taken_before_it_ends(app, archive, created,
                                                                      monkeypatch):
    hold = RowHold(monkeypatch)
    job_id, name = _start(app, archive, created)
    assert hold.reached.wait(60), 'the run never reached the middle of the groups'
    try:
        with app.app_context():
            from services.backup.section_store import store_directory
            directory = store_directory()
        # The sections being read carry the job's id: whoever concludes the job removes them
        owned = [n for n in os.listdir(directory) if n.startswith(f'.ucm_restore_{job_id}.')]
        assert len(owned) == 1, os.listdir(directory)
        done, total = _reported(app, job_id)
        # The progress counts the rows written so far, not only the steps passed
        assert total is not None and total >= len(restore_job.STEPS) + GROUPS
        assert done is not None and done >= HOLD_AT // 2, (done, total)
        with app.app_context():
            assert jobs.request_cancellation(job_id) == 'requested'
    finally:
        hold.release.set()
    assert runner.join_local(job_id, 60)
    with app.app_context():
        row = store.job_row(db.session, job_id)
        db.session.rollback()
        assert (row['state'], row['reason']) == ('cancelled', 'cancelled'), row
        assert row['phase'] not in restore_job.VALIDATED
        assert _groups_here() == 0, 'a cancelled restore left rows behind'
    # Taken inside the loop of groups, long before its last row and before the next step
    assert hold.after < GROUPS - HOLD_AT - 500, hold.after
    assert 'auth' not in hold.steps
    assert not os.path.exists(os.path.join(store.jobs_tmp_dir(), name))
    assert not restore_job.cancel_flagged(job_id)
    assert not os.path.exists(os.path.join(directory, owned[0]))


# -- the brake ------------------------------------------------------------------------------

class _Ctx:
    job_id = str(uuid.uuid4())

    def __init__(self):
        self.reports = []

    def progress(self, done=None, total=None, phase=None):
        self.reports.append((done, total, phase))


def test_the_row_checkpoint_reports_once_per_interval(monkeypatch):
    clock = [1000.0]
    monkeypatch.setattr(restore_job.time, 'monotonic', lambda: clock[0])
    monkeypatch.setattr(restore_job, 'cancel_flagged', lambda job_id: False)
    ctx = _Ctx()
    run = restore_job._Run(ctx, sqlite=False)
    run.row(0, 5000)
    assert len(ctx.reports) == 1
    for _ in range(4000):
        run.row(1)
    assert len(ctx.reports) == 1, 'every row reported: the brake is gone'
    clock[0] += restore_job.CHECK_SECONDS
    run.row(1)
    assert len(ctx.reports) == 2
    done, total, _phase = ctx.reports[-1]
    assert (done, total) == (4001, len(restore_job.STEPS) + 5000)
    # Never complete before the commit's mark says so
    for _ in range(2000):
        run.row(1)
    clock[0] += restore_job.CHECK_SECONDS
    run.row(1)
    assert ctx.reports[-1][:2] == (len(restore_job.STEPS) + 4999, len(restore_job.STEPS) + 5000)


def test_the_row_checkpoint_costs_microseconds_between_two_reports(monkeypatch):
    """The cost a loop pays per row while no report is due (printed for the record)."""
    from services.backup.restore import transaction
    monkeypatch.setattr(restore_job, 'cancel_flagged', lambda job_id: False)
    run = restore_job._Run(_Ctx(), sqlite=False)
    run.row(0, 10)
    rounds = 200_000
    with transaction.progressing(run.checkpoint, run.row):
        started = time.perf_counter()
        for _ in range(rounds):
            transaction.tick(1)
        braked = (time.perf_counter() - started) / rounds
    started = time.perf_counter()
    for _ in range(rounds):
        transaction.tick(1)
    bare = (time.perf_counter() - started) / rounds
    print(f'row checkpoint: {braked * 1e6:.3f} us per row braked, {bare * 1e6:.3f} us without a job')
    assert braked < 20e-6


# -- the sections a run decrypts --------------------------------------------------------------

def test_a_store_names_its_job_and_only_job_stores_are_swept(app, created):
    """A store made for a job carries its id; the sweep removes the stores of final and unknown
    jobs, never a running job's nor one no job made (the start's hourly rule keeps those)."""
    import shutil
    from services.backup.section_store import SectionStore, owned_by
    with app.app_context():
        now = jobs._now()
        running = store.create_job(db.session, kind='audit_verify', slot='audit_verify',
                                   exclusive=False, exclusive_slots={'restore'}, now=now)
        created.append(running)
        assert store.claim_job(db.session, running, 'rows/1/x', now) is not None
        unknown = str(uuid.uuid4())
        stores = {}
        for owner in (running, unknown, None):
            if owner is None:
                stores[owner] = SectionStore()
            else:
                with owned_by(owner):
                    stores[owner] = SectionStore()
        try:
            assert os.path.basename(stores[running]._dir).startswith(f'.ucm_restore_{running}.')
            assert unknown not in os.path.basename(stores[None]._dir)
            store.sweep_job_files(db.session, keep_unknown=True)
            db.session.rollback()
            assert os.path.isdir(stores[running]._dir), 'a running job lost its sections'
            assert not os.path.exists(stores[unknown]._dir)
            assert os.path.isdir(stores[None]._dir)
            assert store.conclude_job(db.session, running, state='failed', reason='error',
                                      from_states=('running',), now=jobs._now())
            assert not os.path.exists(stores[running]._dir)
        finally:
            for one in stores.values():
                shutil.rmtree(one._dir, ignore_errors=True)
