"""Single-scheduler lock (#139 root cause): only one process runs the loop."""
import errno
import json
import logging
import os
import threading
import time
import types
from datetime import timedelta

import pytest

from services import scheduler_service
from services.scheduler_service import SchedulerService, start_scheduler


@pytest.fixture
def data_dir(tmp_path, monkeypatch):
    monkeypatch.setattr('config.settings.DATA_DIR', str(tmp_path), raising=False)
    monkeypatch.setattr(scheduler_service, 'LOCK_RETRY_SECONDS', 0.05)
    return tmp_path


@pytest.fixture
def sched(data_dir):
    made = []

    def make():
        made.append(SchedulerService(wake_interval=3600))
        return made[-1]
    yield make
    for s in made:
        s.stop(timeout=5)
        if s._thread is not None:
            s._thread.join(5)
        s._release_lock()


def _wait(predicate, timeout=5.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.01)
    return predicate()


def test_acquire_holds_the_lock_and_names_the_holder(sched):
    first, second = sched(), sched()
    assert first._acquire_singleton_lock() is True
    assert first._owns_lock and first._owner_pid == os.getpid()
    with open(first._lock_path) as f:
        assert f.read().strip() == str(os.getpid())
    assert second._acquire_singleton_lock() is False
    assert not second._owns_lock


def test_release_frees_the_lock(sched):
    first, second = sched(), sched()
    first._acquire_singleton_lock()
    first._release_lock()
    assert not first._owns_lock
    assert second._acquire_singleton_lock() is True


def test_a_pid_left_in_the_file_never_blocks(sched, data_dir):
    # A live pid (init) written by an earlier version or a killed holder
    (data_dir / 'scheduler.lock').write_text('1')
    assert sched()._acquire_singleton_lock() is True


def test_forked_copy_does_not_release_the_holders_lock(sched):
    first, second = sched(), sched()
    first._acquire_singleton_lock()
    first._owner_pid = os.getpid() + 1  # what a forked child inherits
    first._release_lock()
    assert second._acquire_singleton_lock() is False


def test_a_waiting_scheduler_takes_over_when_the_holder_relinquishes(sched):
    holder, waiting = sched(), sched()
    holder.start()
    assert _wait(lambda: holder._owns_lock)
    waiting.start()
    time.sleep(0.2)
    assert not waiting._owns_lock
    holder.relinquish()
    assert _wait(lambda: waiting._owns_lock, timeout=2)


def test_the_lock_is_kept_until_the_running_task_ends(sched):
    holder, waiting = sched(), sched()
    started, finish = threading.Event(), threading.Event()

    def task():
        started.set()
        finish.wait(5)
    holder.register_task('slow', task, interval=3600)
    holder.tasks['slow']._created_at -= timedelta(seconds=60)
    holder.start()
    assert started.wait(5)
    waiting.start()
    holder.relinquish()
    time.sleep(0.3)
    assert not waiting._owns_lock  # never two runs of the scheduled tasks at once
    finish.set()
    assert _wait(lambda: waiting._owns_lock, timeout=2)


def _app(testing=False):
    return types.SimpleNamespace(config={'TESTING': testing})


def test_under_gunicorn_only_the_scheduler_process_runs_the_loop(sched, monkeypatch):
    scheduler = sched()
    monkeypatch.setattr(scheduler_service, '_scheduler', scheduler)
    monkeypatch.setenv(scheduler_service.SUPERVISED_ENV, '1')
    assert start_scheduler(_app()) is False
    assert scheduler._thread is None


def test_without_gunicorn_the_process_runs_the_loop(sched, monkeypatch):
    scheduler = sched()
    monkeypatch.setattr(scheduler_service, '_scheduler', scheduler)
    monkeypatch.delenv(scheduler_service.SUPERVISED_ENV, raising=False)
    assert start_scheduler(_app()) is True
    assert _wait(lambda: scheduler._owns_lock)


def test_no_loop_under_tests(sched, monkeypatch):
    scheduler = sched()
    monkeypatch.setattr(scheduler_service, '_scheduler', scheduler)
    monkeypatch.delenv(scheduler_service.SUPERVISED_ENV, raising=False)
    assert start_scheduler(_app(testing=True)) is False
    assert scheduler._thread is None


def test_a_filesystem_without_flock_falls_back_to_a_pid_file(sched, data_dir, monkeypatch, caplog):
    def no_lock(fd, op):
        raise OSError(errno.ENOLCK, 'No locks available')
    monkeypatch.setattr(scheduler_service.fcntl, 'flock', no_lock)
    first, second = sched(), sched()
    assert first._acquire_singleton_lock() is True
    assert (data_dir / 'scheduler.pid').read_text() == str(os.getpid())
    (data_dir / 'scheduler.pid').write_text('1')  # held by a live process
    caplog.clear()
    with caplog.at_level(logging.ERROR, logger='services.scheduler_service'):
        assert second._acquire_singleton_lock() is False
        assert second._acquire_singleton_lock() is False
    assert len([r for r in caplog.records if 'No flock' in r.message]) == 1
    (data_dir / 'scheduler.pid').write_text('2147483646')  # its process is gone
    assert second._acquire_singleton_lock() is True
    second._release_lock()
    assert not (data_dir / 'scheduler.pid').exists()


def test_a_busy_flock_is_not_a_missing_one(sched, data_dir):
    first, second = sched(), sched()
    first._acquire_singleton_lock()
    assert second._acquire_singleton_lock() is False
    assert not second._flock_unsupported and not (data_dir / 'scheduler.pid').exists()


def test_the_grace_period_counts_from_the_scheduler_process_start(sched):
    scheduler = sched()
    scheduler.register_task('t', lambda: None, interval=60)
    scheduler.tasks['t']._created_at -= timedelta(hours=1)  # registered when the master booted
    assert scheduler.tasks['t'].should_run()
    scheduler.rearm_grace()
    assert not scheduler.tasks['t'].should_run()


def _pair(sched, monkeypatch, task):
    """The scheduler process's scheduler and a web worker's copy of the same tasks."""
    monkeypatch.setenv(scheduler_service.SUPERVISED_ENV, '1')
    monkeypatch.setattr(scheduler_service, 'REQUEST_POLL_SECONDS', 0.05)
    loop, worker = sched(), sched()
    for s in (loop, worker):
        s.register_task('t', task, interval=3600)
    return loop, worker


def test_a_worker_shows_what_the_scheduler_process_published(sched, monkeypatch):
    loop, worker = _pair(sched, monkeypatch, lambda: {'status': 'skipped', 'reason': 'nothing'})
    loop.tasks['t']._created_at -= timedelta(seconds=60)
    loop.start()
    assert _wait(lambda: worker.get_task_status('t')['run_count'] == 1)
    status = worker.get_all_tasks_status()['t']
    assert status['last_status'] == 'skipped' and status['last_run']
    assert worker.tasks['t'].run_count == 0  # its own copy never ran


def test_run_now_from_a_worker_runs_in_the_scheduler_process(sched, monkeypatch):
    ran_in = []
    loop, worker = _pair(sched, monkeypatch, lambda: ran_in.append(threading.current_thread().name))
    loop.start()
    assert _wait(lambda: loop._owns_lock)
    status = worker.run_task_now('t')
    assert ran_in == ['SchedulerService'] and status['run_count'] == 1 and not status.get('queued')
    assert not os.listdir(scheduler_service._data_path(scheduler_service.REQUESTS_DIR))


def test_run_now_says_queued_when_the_run_outlasts_the_wait(sched, monkeypatch):
    loop, worker = _pair(sched, monkeypatch, lambda: None)
    monkeypatch.setattr(scheduler_service, 'RUN_NOW_WAIT_SECONDS', 0.3)
    status = worker.run_task_now('t')  # no scheduler process running
    assert status['queued'] is True and status['run_count'] == 0


def test_a_worker_flags_a_state_no_longer_published(sched, monkeypatch, data_dir):
    loop, worker = _pair(sched, monkeypatch, lambda: None)
    assert worker.state_is_stale()  # nothing published yet
    loop._publish_state()
    assert not worker.state_is_stale() and 'stale' not in worker.get_task_status('t')
    state = json.loads((data_dir / scheduler_service.STATE_FILE).read_text())
    state['published_at'] -= 2 * worker.wake_interval + 1
    (data_dir / scheduler_service.STATE_FILE).write_text(json.dumps(state))
    assert worker.state_is_stale() and worker.get_task_status('t')['stale'] is True


def test_every_pass_is_published_even_with_nothing_due(sched, monkeypatch, data_dir):
    loop, _ = _pair(sched, monkeypatch, lambda: None)
    loop.wake_interval = 0.1
    loop.start()
    path = data_dir / scheduler_service.STATE_FILE
    assert _wait(lambda: path.exists())
    first = json.loads(path.read_text())['published_at']
    assert _wait(lambda: json.loads(path.read_text())['published_at'] > first, timeout=3)


def test_an_unwritable_data_dir_is_reported_once(sched, monkeypatch, caplog):
    loop, _ = _pair(sched, monkeypatch, lambda: None)
    monkeypatch.setattr(scheduler_service, '_data_path', lambda name: f'/nonexistent-ucm/{name}')
    with caplog.at_level(logging.WARNING, logger='services.scheduler_service'):
        loop._publish_state()
        loop._publish_state()
    assert len([r for r in caplog.records if 'not published' in r.message]) == 1


def test_the_api_reports_a_stale_state_and_a_queued_run(app, auth_client, monkeypatch, tmp_path):
    from services.audit import AuditService

    monkeypatch.setattr('config.settings.DATA_DIR', str(tmp_path), raising=False)
    monkeypatch.setenv(scheduler_service.SUPERVISED_ENV, '1')
    monkeypatch.setattr(scheduler_service, 'RUN_NOW_WAIT_SECONDS', 0.2)
    audits = []
    monkeypatch.setattr(AuditService, 'log_action', staticmethod(lambda **kw: audits.append(kw)))
    listed = auth_client.get('/api/v2/system/scheduler').get_json()['data']
    assert listed['stale'] is True  # no scheduler process publishes here
    name = listed['tasks'][0]['name']
    with app.app_context():
        task = scheduler_service.get_scheduler().tasks[name]
        monkeypatch.setattr(task, 'last_error', 'the previous run failed')
    resp = auth_client.post(f'/api/v2/system/scheduler/{name}/run').get_json()
    assert resp['data']['queued'] is True and 'started' in resp['message']
    assert audits[-1]['success'] is True and 'still running' in audits[-1]['details']


def test_a_per_node_task_follows_the_host_lock_outside_ha(sched):
    # Single node: the process holding the host lock runs it, a waiting one does not
    holder, waiting = sched(), sched()
    runs = {'holder': 0, 'waiting': 0}
    for s, name in ((holder, 'holder'), (waiting, 'waiting')):
        s.register_task('local', lambda name=name: runs.__setitem__(name, runs[name] + 1),
                        interval=3600, per_node=True)
        s.tasks['local']._created_at -= timedelta(seconds=60)
    holder.start()
    assert _wait(lambda: runs['holder'] == 1)
    waiting.start()
    time.sleep(0.3)
    assert runs == {'holder': 1, 'waiting': 0}


def test_a_task_says_whether_it_runs_on_every_node(sched):
    s = sched()
    s.register_task('local', lambda: None, interval=60, per_node=True)
    s.register_task('cluster', lambda: None, interval=60)
    assert s.tasks['local'].to_dict()['per_node'] is True
    assert s.tasks['cluster'].to_dict()['per_node'] is False


class _OneOwnerLock:
    """The leader lock of two nodes, without PostgreSQL: the first to ask holds it."""
    owner = None

    def __init__(self, scheduler):
        self.scheduler = scheduler

    def acquire(self):
        if _OneOwnerLock.owner in (None, self.scheduler):
            _OneOwnerLock.owner = self.scheduler
            return True
        return False

    def still_held(self):
        return _OneOwnerLock.owner is self.scheduler

    def release(self):
        if _OneOwnerLock.owner is self.scheduler:
            _OneOwnerLock.owner = None


def test_in_ha_a_per_node_task_runs_on_every_node_and_a_leader_task_on_one(sched, monkeypatch):
    monkeypatch.setattr(scheduler_service, '_ha', lambda: True)
    monkeypatch.setattr(_OneOwnerLock, 'owner', None)
    for name in ('_heartbeat', '_publish_state', '_took_leadership'):
        monkeypatch.setattr(SchedulerService, name, lambda self, *a, **k: None)
    monkeypatch.setattr(SchedulerService, '_take_requests', lambda self: [])
    monkeypatch.setattr(SchedulerService, '_has_requests', lambda self: False)
    monkeypatch.setattr(SchedulerService, '_singleton_lock', lambda self: _OneOwnerLock(self))
    runs = {}
    nodes = [sched(), sched()]
    for node, s in enumerate(nodes):
        s.wake_interval = 0.05
        for name, per_node in (('local', True), ('cluster', False)):
            s.register_task(name, lambda key=(node, name): runs.__setitem__(key, runs.get(key, 0) + 1),
                            interval=3600, per_node=per_node)
            s.tasks[name]._created_at -= timedelta(seconds=60)
        s.start()
    assert _wait(lambda: runs.get((0, 'local')) and runs.get((1, 'local')))
    time.sleep(0.3)
    assert runs[(0, 'local')] == 1 and runs[(1, 'local')] == 1
    assert runs.get((0, 'cluster'), 0) + runs.get((1, 'cluster'), 0) == 1


def test_a_running_per_node_task_does_not_delay_a_follower_takeover(sched, monkeypatch):
    # The follower keeps retrying the lock and writing its heartbeat while a per-node task runs
    monkeypatch.setattr(scheduler_service, '_ha', lambda: True)
    monkeypatch.setattr(_OneOwnerLock, 'owner', None)
    for name in ('_publish_state', '_took_leadership'):
        monkeypatch.setattr(SchedulerService, name, lambda self, *a, **k: None)
    monkeypatch.setattr(SchedulerService, '_take_requests', lambda self: [])
    monkeypatch.setattr(SchedulerService, '_has_requests', lambda self: False)

    def kept_lock(self):
        # Kept like the PostgreSQL one, so stopping the leader releases it
        if self._leader_lock is None:
            self._leader_lock, self._leader_lock_pid = _OneOwnerLock(self), os.getpid()
        return self._leader_lock
    monkeypatch.setattr(SchedulerService, '_singleton_lock', kept_lock)
    beats = []
    monkeypatch.setattr(SchedulerService, '_heartbeat',
                        lambda self, force=False: beats.append(self))
    leader, follower = sched(), sched()
    release, started, runs = threading.Event(), threading.Event(), []

    def slow():
        runs.append(1)
        started.set()
        release.wait(5)
    leader.wake_interval = follower.wake_interval = 0.05
    leader.start()
    assert _wait(lambda: _OneOwnerLock.owner is leader)
    follower.register_task('local', slow, interval=3600, per_node=True)
    follower.tasks['local']._created_at -= timedelta(seconds=60)
    follower.start()
    try:
        assert started.wait(2)
        before = beats.count(follower)
        leader.stop(timeout=5)
        assert _wait(lambda: _OneOwnerLock.owner is follower, timeout=1.0)
        assert _wait(lambda: beats.count(follower) > before + 2, timeout=1.0)
        assert not release.is_set() and runs == [1]
    finally:
        release.set()
    # The task the node thread still ran is not started again by the new leader
    time.sleep(0.3)
    assert runs == [1]


def _ha_pair(monkeypatch, beats=None):
    """Two nodes on the in-memory leader lock, nothing written to a database."""
    monkeypatch.setattr(scheduler_service, '_ha', lambda: True)
    monkeypatch.setattr(_OneOwnerLock, 'owner', None)
    for name in ('_publish_state', '_took_leadership'):
        monkeypatch.setattr(SchedulerService, name, lambda self, *a, **k: None)
    monkeypatch.setattr(SchedulerService, '_has_requests', lambda self: False)

    def kept_lock(self):
        if self._leader_lock is None:
            self._leader_lock, self._leader_lock_pid = _OneOwnerLock(self), os.getpid()
        return self._leader_lock
    monkeypatch.setattr(SchedulerService, '_singleton_lock', kept_lock)
    monkeypatch.setattr(SchedulerService, '_heartbeat',
                        lambda self, force=False: beats.append(self) if beats is not None else None)


def test_a_graceful_stop_waits_for_the_per_node_task_of_a_follower(sched, monkeypatch):
    _ha_pair(monkeypatch)
    monkeypatch.setattr(SchedulerService, '_take_requests', lambda self: [])
    leader, follower = sched(), sched()
    started, done = threading.Event(), threading.Event()

    def slow():
        started.set()
        time.sleep(0.3)
        done.set()
    leader.wake_interval = follower.wake_interval = 0.05
    leader.start()
    assert _wait(lambda: _OneOwnerLock.owner is leader)
    follower.register_task('local', slow, interval=3600, per_node=True)
    follower.tasks['local']._created_at -= timedelta(seconds=60)
    follower.start()
    assert started.wait(2)
    follower.relinquish()
    assert follower.join(2) is True
    assert done.is_set()


class _HookLock:
    """A task's run lock that runs ``hook`` once, just before it is taken."""

    def __init__(self, hook):
        self._lock, self._hook = threading.Lock(), hook

    def acquire(self, blocking=True, timeout=-1):
        hook, self._hook = self._hook, None
        if hook:
            hook()
        return self._lock.acquire(blocking, timeout)

    def release(self):
        self._lock.release()

    def locked(self):
        return self._lock.locked()

    def __enter__(self):
        self.acquire()
        return self

    def __exit__(self, *exc):
        self.release()


def test_a_run_now_on_a_task_the_node_thread_still_runs_never_blocks_the_new_leader(sched, monkeypatch):
    beats = []
    _ha_pair(monkeypatch, beats)
    leader, follower = sched(), sched()
    release, started, runs = threading.Event(), threading.Event(), []
    asked = []

    def take(self):
        if self is follower and not asked:
            asked.append(1)
            return [self.tasks['local']]  # "run now" claimed at the takeover
        return []
    monkeypatch.setattr(SchedulerService, '_take_requests', take)

    def slow():
        runs.append(threading.current_thread().name)
        started.set()
        release.wait(2)
    leader.wake_interval = follower.wake_interval = 0.05
    leader.start()
    assert _wait(lambda: _OneOwnerLock.owner is leader)
    follower.register_task('local', slow, interval=3600, per_node=True)
    follower.tasks['local']._created_at -= timedelta(seconds=60)
    follower.start()
    try:
        assert started.wait(2)
        leader.stop(timeout=5)
        assert _wait(lambda: asked, timeout=1.0)
        before = beats.count(follower)
        assert _wait(lambda: beats.count(follower) > before + 2, timeout=1.0)
        assert runs == ['SchedulerNodeTasks']
    finally:
        release.set()
    # The request is served once the node thread's run is over, by the leader loop
    assert _wait(lambda: len(runs) == 2, timeout=2)
    time.sleep(0.3)
    assert runs == ['SchedulerNodeTasks', 'SchedulerService']

