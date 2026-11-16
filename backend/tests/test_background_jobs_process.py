"""Background jobs across processes: a killed executor, two processes racing for a slot,
and the HA lease on PostgreSQL with two connections.

The child processes load only the model and services/jobs/store.py on a database of their
own (never the application, its settings nor the host's): each asserts it.
"""
import os
import signal
import subprocess
import sys
import time
from datetime import timedelta

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from models.background_job import BackgroundJob
from services.jobs import store
from utils.datetime_utils import utc_now

BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PG_URL = os.getenv('UCM_TEST_PG_URL')
EXCLUSIVE = frozenset({'restore'})

CHILD = r'''
import os, sys, time
sys.path.insert(0, sys.argv[1])
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from services.jobs import store
from utils.datetime_utils import utc_now
assert 'config.settings' not in sys.modules and 'app' not in sys.modules
url, schema, mode, job_id, marker = sys.argv[2:7]
args = {'options': f'-csearch_path={schema}'} if schema != '-' else {}
engine = create_engine(url, connect_args=args)
with Session(engine) as session:
    if mode in ('kill', 'exit'):
        assert store.claim_job(session, job_id, f'child/{os.getpid()}', utc_now()) is not None
        with engine.begin() as conn:
            store.write_progress(conn, job_id, f'child/{os.getpid()}', 1, 10, 'working')
        open(marker, 'w').write('taken')
        if mode == 'exit':
            os._exit(0)  # a stop past the grace: no conclusion
        time.sleep(120)
    else:  # race: create a job of this slot once the go file appears
        slot = mode
        while not os.path.exists(marker):
            time.sleep(0.005)
        try:
            made = store.create_job(session, kind='test_' + slot, slot=slot, exclusive=slot == 'restore',
                                exclusive_slots={'restore'}, now=utc_now())
            print('ok', made)
        except store.SlotBusy:
            print('busy')
'''


def _env():
    env = {k: v for k, v in os.environ.items() if not k.startswith('GIT_')}
    env['PYTHONPATH'] = BACKEND
    return env


@pytest.fixture(params=['sqlite', pytest.param('postgresql', marks=pytest.mark.postgres)])
def database(request, tmp_path):
    """(url, schema or '-', engine) of a database holding only background_jobs."""
    if request.param == 'sqlite':
        url, schema = f'sqlite:///{tmp_path / "jobs.db"}', '-'
        engine = create_engine(url)
    else:
        if not PG_URL:
            pytest.skip('UCM_TEST_PG_URL not set')
        url, schema = PG_URL, f"jobs_proc_{os.getenv('PYTEST_XDIST_WORKER', 'main')}"
        admin = create_engine(PG_URL)
        with admin.begin() as conn:
            conn.execute(text(f'DROP SCHEMA IF EXISTS {schema} CASCADE'))
            conn.execute(text(f'CREATE SCHEMA {schema}'))
        admin.dispose()
        engine = create_engine(url, connect_args={'options': f'-csearch_path={schema}'})
    BackgroundJob.__table__.create(engine)
    yield url, schema, engine
    engine.dispose()
    if request.param == 'postgresql':
        admin = create_engine(PG_URL)
        with admin.begin() as conn:
            conn.execute(text(f'DROP SCHEMA IF EXISTS {schema} CASCADE'))
        admin.dispose()


def _child(database, mode, job_id, marker):
    url, schema, _ = database
    return subprocess.Popen([sys.executable, '-I', '-c', CHILD, BACKEND, url, schema, mode, job_id,
                             str(marker)], env=_env(), stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE, text=True)


def _stop(child):
    if child.poll() is None:
        child.kill()
    child.communicate(timeout=10)


def _wait_for(path, child, timeout=20):
    deadline = time.monotonic() + timeout
    while not os.path.exists(path):
        if child.poll() is not None:
            raise AssertionError(child.communicate()[1])
        assert time.monotonic() < deadline, 'the child never took the job'
        time.sleep(0.05)


def _create(session, kind, slot, file_name=None, now=None):
    return store.create_job(session, kind=kind, slot=slot, exclusive=slot in EXCLUSIVE,
                        exclusive_slots=EXCLUSIVE, now=now or utc_now(), file_name=file_name,
                        secret='encrypted-elsewhere')


@pytest.mark.parametrize('kind, slot, lines', [('test_backup', 'backup', 1),
                                               ('test_restore', 'restore', 1),
                                               ('audit_verify', 'audit_verify', 0)])
@pytest.mark.parametrize('how', ['kill', 'exit'])
def test_a_killed_executor_is_concluded_by_the_next_start(app, database, tmp_path, kind, slot,
                                                          lines, how):
    _, _, engine = database
    with Session(engine) as session:
        job_id = _create(session, kind, slot)
        name = store.file_name_for(job_id, '.upload')
        session.execute(store.T.update().where(store.T.c.id == job_id).values(file_name=name))
        session.commit()
    with app.app_context():
        directory = store.jobs_tmp_dir()
    os.makedirs(directory, exist_ok=True)
    open(os.path.join(directory, name), 'wb').close()
    marker = tmp_path / 'taken'
    child = _child(database, how, job_id, marker)
    try:
        _wait_for(marker, child)
        if how == 'kill':
            os.kill(child.pid, signal.SIGKILL)
        child.wait(timeout=10)
    finally:
        _stop(child)
    written = []

    def audit_for(kind_):
        if kind_ == 'audit_verify':
            return None

        def write(row, state, reason):
            written.append((row['id'], state, reason))
            session.commit()
            return True
        return write
    with app.app_context(), Session(engine) as session:
        row = store.job_row(session, job_id)
        assert row['state'] == 'running' and row['secret'] is None
        assert store.recover_orphans(session, now=utc_now(), all_running=True, audit_for=audit_for) == 1
        row = store.job_row(session, job_id)
        assert (row['state'], row['reason']) == ('failed', 'executor_lost')
        assert store.recover_orphans(session, now=utc_now(), all_running=True, audit_for=audit_for) == 0
        assert not store.active_jobs(session)
    assert len(written) == lines
    assert not os.path.exists(os.path.join(directory, name))


@pytest.mark.parametrize('first, second', [('backup', 'backup'), ('restore', 'backup'),
                                           ('backup', 'restore'), ('restore', 'restore')])
def test_two_processes_racing_for_a_slot_one_wins(database, tmp_path, first, second):
    _, _, engine = database
    for attempt in range(3):
        go = tmp_path / f'go{attempt}'
        children = [_child(database, slot, '-', go) for slot in (first, second)]
        time.sleep(1.5)  # both loaded and polling
        go.write_text('go')
        outcomes = []
        for child in children:
            out, err = child.communicate(timeout=60)
            assert child.returncode == 0, err
            outcomes.append(out.split()[0])
        assert sorted(outcomes) == ['busy', 'ok'], outcomes
        with Session(engine) as session:
            session.execute(store.T.delete())
            session.commit()


def test_different_slots_run_side_by_side(database):
    _, _, engine = database
    with Session(engine) as session:
        _create(session, 'test_backup', 'backup')
        _create(session, 'audit_verify', 'audit_verify')
        assert len(store.active_jobs(session)) == 2


def test_lease_two_connections(app, database):
    """Node A runs the job; node B leads. A lapsed lease only is concluded by B; a leader that
    changes while A's lease holds leaves the job to A, and A's late moves lose once B won."""
    _, _, engine = database
    with Session(engine) as a, Session(engine) as b, app.app_context():
        now = utc_now()
        job_id = _create(a, 'test_backup', 'backup', now=now)
        # B cannot start a second one while A's is active
        with pytest.raises(store.SlotBusy):
            _create(b, 'test_backup', 'backup', now=now)
        assert store.claim_job(a, job_id, 'node-a/1/x', now) is not None
        assert store.claim_job(b, job_id, 'node-b/1/y', now) is None
        renewed_at = now + timedelta(seconds=store.LEASE_SECONDS - 10)
        with engine.begin() as conn:
            assert store.renew_lease(conn, job_id, 'node-a/1/x', renewed_at)
        # B now leads; past A's first lease but inside the renewed one: left to A
        later = now + timedelta(seconds=store.LEASE_SECONDS + 5)
        assert store.recover_orphans(b, now=later, all_running=False) == 0
        with engine.begin() as conn:
            assert store.write_progress(conn, job_id, 'node-a/1/x', 5) is False
            # Another executor's moves on A's job are refused
            with pytest.raises(store.JobLost):
                store.write_progress(conn, job_id, 'node-b/1/y', 5)
            assert not store.renew_lease(conn, job_id, 'node-b/1/y', later)
        assert not store.conclude_job(b, job_id, state='succeeded', reason='done',
                                      from_states=('running',), now=later, executor='node-b/1/y')
        # A dies: its lease lapses and B concludes; A's late moves all lose
        dead = renewed_at + timedelta(seconds=store.LEASE_SECONDS + 1)
        assert store.recover_orphans(b, now=dead, all_running=False) == 1
        with engine.begin() as conn, pytest.raises(store.JobLost):
            store.write_progress(conn, job_id, 'node-a/1/x', 6)
        with engine.begin() as conn:
            assert not store.renew_lease(conn, job_id, 'node-a/1/x', dead)
        assert not store.conclude_job(a, job_id, state='succeeded', reason='done',
                                      from_states=('running',), now=dead, executor='node-a/1/x')
        assert store.job_row(b, job_id)['reason'] == 'executor_lost'


def test_a_take_read_before_another_one_committed_loses(app, database, monkeypatch):
    """Two executors read the same pending row: the conditional update gives it to one."""
    _, _, engine = database
    with Session(engine) as a, Session(engine) as b:
        job_id = _create(a, 'test_backup', 'backup')
        stale = store.job_row(a, job_id)
        a.rollback()
        assert store.claim_job(a, job_id, 'node-a/1/x', utc_now()) is not None
        monkeypatch.setattr(store, '_job_row', lambda executor, wanted: dict(stale))
        assert store.claim_job(b, job_id, 'node-b/1/y', utc_now()) is None
        monkeypatch.undo()
        assert store.job_row(b, job_id)['executor'] == 'node-a/1/x'
