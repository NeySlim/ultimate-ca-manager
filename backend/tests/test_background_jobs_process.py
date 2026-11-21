"""Background jobs across processes: a killed executor, two processes racing for a slot,
and the HA lease on PostgreSQL with two connections.

The child processes load only the model and services/jobs/store.py on a database of their
own (never the application, its settings nor the host's): each asserts it. The scheduler
process tests run scheduler_main on a SQLite data directory under tmp_path.
"""
import os
import shutil
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
    if mode == 'store':  # a run that decrypted its archive's sections into a store, then dies
        # The module alone, by its path: its package would load the application's settings
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            'section_store', os.path.join(sys.argv[1], 'services', 'backup', 'section_store.py'))
        section_store = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(section_store)
        SectionStore, owned_by = section_store.SectionStore, section_store.owned_by
        assert store.claim_job(session, job_id, f'child/{os.getpid()}', utc_now()) is not None
        with owned_by(job_id):
            sections = SectionStore(directory=os.environ['UCM_TEST_STORE_DIR'])
        sections.add_part('certificates', 0, [{'refid': 'r', 'crt': 'x' * 4096}] * 64)
        sections.seal()
        assert 'config.settings' not in sys.modules
        open(marker, 'w').write(sections._dir)
        time.sleep(120)
    elif mode in ('kill', 'exit'):
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


def _child(database, mode, job_id, marker, env=None):
    url, schema, _ = database
    return subprocess.Popen([sys.executable, '-I', '-c', CHILD, BACKEND, url, schema, mode, job_id,
                             str(marker)], env={**_env(), **(env or {})}, stdout=subprocess.PIPE,
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


def test_a_killed_restore_leaves_no_sections_and_a_live_one_keeps_its_own(app, database, tmp_path):
    """The store of a killed run goes when its job is concluded executor_lost, before any
    sweep; the store of a job still running, here or on another node, survives every pass."""
    from services.backup import section_store
    _, _, engine = database
    with app.app_context():
        directory = section_store.store_directory()
    with Session(engine) as session:
        lost = _create(session, 'test_backup', 'backup')
        live = _create(session, 'audit_verify', 'audit_verify')
    children, stores = {}, {}
    try:
        for job_id in (lost, live):
            marker = tmp_path / f'store-{job_id}'
            children[job_id] = _child(database, 'store', job_id, marker,
                                      env={'UCM_TEST_STORE_DIR': directory})
            _wait_for(marker, children[job_id])
            stores[job_id] = marker.read_text()
            assert os.path.isdir(stores[job_id]) and os.listdir(stores[job_id])
        os.kill(children[lost].pid, signal.SIGKILL)
        children[lost].wait(timeout=10)
        with app.app_context(), Session(engine) as session:
            # Its lease lapsed (HA) or the scheduler restarted (one node): the same conclusion
            session.execute(store.T.update().where(store.T.c.id == lost).values(
                lease_expires_at=utc_now() - timedelta(seconds=1)))
            session.commit()
            assert store.recover_orphans(session, now=utc_now(), all_running=False) == 1
            assert store.job_row(session, lost)['reason'] == 'executor_lost'
            assert not os.path.exists(stores[lost]), 'the killed run left its sections'
            assert os.path.isdir(stores[live])
            store.sweep_job_files(session, keep_unknown=False)
            assert os.path.isdir(stores[live]), 'the sweep removed a running job\'s sections'
            # Its executor dead but the job not yet concluded: still active, still kept
            os.kill(children[live].pid, signal.SIGKILL)
            children[live].wait(timeout=10)
            store.sweep_job_files(session, keep_unknown=False)
            assert os.path.isdir(stores[live])
            assert store.conclude_job(session, live, state='failed', reason='executor_lost',
                                      from_states=('running',), now=utc_now())
            assert not os.path.exists(stores[live])
    finally:
        for child in children.values():
            _stop(child)
        for path in stores.values():
            shutil.rmtree(path, ignore_errors=True)


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


_STOPPED_IN_A_MAINTENANCE = r'''
import os
from services import cluster_maintenance
from services.jobs import store
waiting = os.environ['TEST_JOB_WAITING']
real = store.conclude_job


def refused(*args, **kwargs):
    # The run's own conclusion meets a maintenance that never lifts
    if kwargs.get('reason') == store.DONE:
        open(waiting, 'w').write('waiting')
        raise cluster_maintenance.MaintenanceActive('test maintenance')
    return real(*args, **kwargs)


store.conclude_job = refused
cluster_maintenance.blocks_writes = lambda app=None: os.path.exists(waiting)
import scheduler_main  # noqa: E402
os._exit(scheduler_main.exit_code(scheduler_main.main))
'''


def _job_state(url, job_id):
    engine = create_engine(url)
    try:
        with Session(engine) as session:
            row = store.job_row(session, job_id)
            return row and (row['state'], row['reason'], row['executor'])
    finally:
        engine.dispose()


def _until(predicate, child, timeout=60):
    deadline = time.monotonic() + timeout
    while not predicate():
        assert child.poll() is None, 'the scheduler process stopped early'
        assert time.monotonic() < deadline, 'timed out'
        time.sleep(0.1)


@pytest.mark.slow
def test_a_stop_during_the_wait_for_a_maintenance_exits_within_the_grace(tmp_path):
    """SIGTERM while a run waits for the maintenance to conclude: the process exits within
    its grace, the job stays running, and the next start concludes it executor_lost."""
    from tests.test_scheduler_process import _scheduler_env
    env, data = _scheduler_env(tmp_path)
    (tmp_path / 'etc').mkdir()
    env = {k: v for k, v in env.items() if not k.startswith('GIT_')}
    waiting = tmp_path / 'waiting'
    env.update(UCM_CONFIG_DIR=str(tmp_path / 'etc'), TEST_JOB_WAITING=str(waiting),
               UCM_SCHEDULER_GRACEFUL_TIMEOUT='3', UCM_HA='')
    url = f"sqlite:///{data / 'ucm.db'}"
    first = subprocess.Popen([sys.executable, '-c', _STOPPED_IN_A_MAINTENANCE], cwd=BACKEND,
                             env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    second = None
    try:
        _until(lambda: (data / 'scheduler_state.json').exists(), first)
        engine = create_engine(url)
        with Session(engine) as session:
            job_id = _create(session, 'audit_verify', 'audit_verify')
        engine.dispose()
        _until(waiting.exists, first)
        assert _job_state(url, job_id)[:2] == ('running', None)
        stopped_at = time.monotonic()
        first.send_signal(signal.SIGTERM)
        assert first.wait(timeout=15) == 0
        assert time.monotonic() - stopped_at < 3 + 5
        state, reason, executor = _job_state(url, job_id)
        assert (state, reason) == ('running', None) and executor
        second = subprocess.Popen([sys.executable, '-m', 'scheduler_main'], cwd=BACKEND, env=env,
                                  stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        _until(lambda: _job_state(url, job_id)[0] != 'running', second)
        assert _job_state(url, job_id)[:2] == ('failed', 'executor_lost')
        second.send_signal(signal.SIGTERM)
        assert second.wait(timeout=15) == 0
    finally:
        for child in (first, second):
            if child is not None and child.poll() is None:
                child.kill()
                child.wait()


_HELD_IN_A_BACKUP = r'''
import os, time
from services.jobs import backup
taken = os.environ['TEST_BACKUP_TAKEN']
real = backup._reporter


def reporter(ctx):
    # The real export, held at its first section: the lock is taken and the spool open
    inner = real(ctx)

    def progress(done=None, total=None):
        inner(done, total)
        if done is not None:
            open(taken, 'w').write(ctx.job_id)
            time.sleep(300)
    return progress


backup._reporter = reporter
import scheduler_main  # noqa: E402
os._exit(scheduler_main.exit_code(scheduler_main.main))
'''


@pytest.mark.slow
def test_a_backup_whose_scheduler_is_killed_is_lost_once_and_leaves_nothing(tmp_path):
    """kill -9 of the scheduler process during a real backup: the next start concludes it
    executor_lost with one audit line, no archive and no spool remain, the lock is free."""
    import fcntl
    from tests.test_scheduler_process import _scheduler_env
    from utils.encryption import encrypt_value
    env, data = _scheduler_env(tmp_path)
    (tmp_path / 'etc').mkdir()
    env = {k: v for k, v in env.items() if not k.startswith('GIT_')}
    taken = tmp_path / 'taken'
    env.update(UCM_CONFIG_DIR=str(tmp_path / 'etc'), TEST_BACKUP_TAKEN=str(taken), UCM_HA='')
    url = f"sqlite:///{data / 'ucm.db'}"
    backups = data / 'backups'
    first = subprocess.Popen([sys.executable, '-c', _HELD_IN_A_BACKUP], cwd=BACKEND, env=env,
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    second = None
    try:
        _until(lambda: (data / 'scheduler_state.json').exists(), first)
        engine = create_engine(url)
        with Session(engine) as session:
            job_id = store.create_job(
                session, kind='backup', slot='backup', exclusive=False, exclusive_slots=EXCLUSIVE,
                now=utc_now(), params={'route': 'system', 'kdf': None, 'generated': False},
                secret=encrypt_value('Killed-Backup-Password-42'), requester=(None, 'admin', None))
        engine.dispose()
        _until(taken.exists, first)
        assert _job_state(url, job_id)[0] == 'running'
        assert list(backups.glob('.ucm_backup_*.tmp')), 'the export never opened its spool'
        os.kill(first.pid, signal.SIGKILL)
        first.wait(timeout=10)
        assert _job_state(url, job_id)[0] == 'running'
        second = subprocess.Popen([sys.executable, '-m', 'scheduler_main'], cwd=BACKEND, env=env,
                                  stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        _until(lambda: _job_state(url, job_id)[0] != 'running', second)
        assert _job_state(url, job_id)[:2] == ('failed', 'executor_lost')
        engine = create_engine(url)
        with engine.connect() as conn:
            lines = conn.execute(text(
                "SELECT details, success FROM audit_logs WHERE action = 'system_backup' "
                "AND resource_id = :id"), {'id': job_id}).all()
            secret = conn.execute(text('SELECT secret FROM background_jobs WHERE id = :id'),
                                  {'id': job_id}).scalar()
        engine.dispose()
        assert [tuple(line) for line in lines] == [
            ('Backup stopped: the process running it was lost', False)]
        assert secret is None
        assert not list(backups.glob('ucm_backup_*')) and not list(backups.glob('.ucm_backup_*.tmp'))
        with open(backups / '.ucm_backup_operation.lock', 'a') as lock:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)  # raises if still held
            fcntl.flock(lock, fcntl.LOCK_UN)
        second.send_signal(signal.SIGTERM)
        assert second.wait(timeout=15) == 0
    finally:
        for child in (first, second):
            if child is not None and child.poll() is None:
                child.kill()
                child.wait()


_HELD_IN_A_VERIFICATION = r'''
import os, time
from services.jobs import runner
taken = os.environ['TEST_VERIFY_TAKEN']
real = runner.JobContext.progress


def progress(ctx, *args, **kwargs):
    # The real verification, held once its first progress is written: taken and running
    real(ctx, *args, **kwargs)
    open(taken, 'w').write(ctx.job_id)
    time.sleep(300)


runner.JobContext.progress = progress
import scheduler_main  # noqa: E402
os._exit(scheduler_main.exit_code(scheduler_main.main))
'''


@pytest.mark.slow
def test_a_verification_whose_scheduler_is_killed_is_lost_once_without_an_audit_line(tmp_path):
    """kill -9 of the scheduler process during a real audit verification: the next start
    concludes it executor_lost, writes no audit line (none before jobs) and frees the slot."""
    from tests.test_scheduler_process import _scheduler_env
    env, data = _scheduler_env(tmp_path)
    (tmp_path / 'etc').mkdir()
    env = {k: v for k, v in env.items() if not k.startswith('GIT_')}
    taken = tmp_path / 'taken'
    env.update(UCM_CONFIG_DIR=str(tmp_path / 'etc'), TEST_VERIFY_TAKEN=str(taken), UCM_HA='')
    url = f"sqlite:///{data / 'ucm.db'}"
    first = subprocess.Popen([sys.executable, '-c', _HELD_IN_A_VERIFICATION], cwd=BACKEND, env=env,
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    second = None
    try:
        _until(lambda: (data / 'scheduler_state.json').exists(), first)
        engine = create_engine(url)
        with Session(engine) as session:
            job_id = store.create_job(
                session, kind='audit_verify', slot='audit_verify', exclusive=False,
                exclusive_slots=EXCLUSIVE, now=utc_now(), params={'start_id': None, 'end_id': None},
                requester=(None, 'admin', None))
        engine.dispose()
        _until(taken.exists, first)
        assert _job_state(url, job_id)[0] == 'running'
        os.kill(first.pid, signal.SIGKILL)
        first.wait(timeout=10)
        assert _job_state(url, job_id)[0] == 'running'
        second = subprocess.Popen([sys.executable, '-m', 'scheduler_main'], cwd=BACKEND, env=env,
                                  stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        _until(lambda: _job_state(url, job_id)[0] != 'running', second)
        assert _job_state(url, job_id)[:2] == ('failed', 'executor_lost')
        engine = create_engine(url)
        with engine.connect() as conn:
            lines = conn.execute(text('SELECT count(*) FROM audit_logs WHERE resource_id = :id'),
                                 {'id': job_id}).scalar()
            active = conn.execute(text(
                "SELECT count(*) FROM background_jobs WHERE state IN ('pending', 'running')")).scalar()
        engine.dispose()
        assert (lines, active) == (0, 0)
        second.send_signal(signal.SIGTERM)
        assert second.wait(timeout=15) == 0
    finally:
        for child in (first, second):
            if child is not None and child.poll() is None:
                child.kill()
                child.wait()
