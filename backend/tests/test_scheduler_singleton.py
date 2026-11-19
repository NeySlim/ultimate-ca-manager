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
