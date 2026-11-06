"""Single-scheduler lock (#139 root cause): only one process runs the loop."""
import os
import threading
import time
import types

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
    holder.tasks['slow']._created_at -= __import__('datetime').timedelta(seconds=60)
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


def test_the_gunicorn_master_only_registers(sched, monkeypatch):
    scheduler = sched()
    monkeypatch.setattr(scheduler_service, '_scheduler', scheduler)
    monkeypatch.setenv(scheduler_service.IN_WORKER_ENV, '1')
    assert start_scheduler(_app()) is False
    assert scheduler._thread is None
    assert start_scheduler(_app(), in_worker=True) is True
    assert _wait(lambda: scheduler._owns_lock)


def test_without_gunicorn_the_process_runs_the_loop(sched, monkeypatch):
    scheduler = sched()
    monkeypatch.setattr(scheduler_service, '_scheduler', scheduler)
    monkeypatch.delenv(scheduler_service.IN_WORKER_ENV, raising=False)
    assert start_scheduler(_app()) is True
    assert _wait(lambda: scheduler._owns_lock)


def test_no_loop_under_tests(sched, monkeypatch):
    scheduler = sched()
    monkeypatch.setattr(scheduler_service, '_scheduler', scheduler)
    monkeypatch.delenv(scheduler_service.IN_WORKER_ENV, raising=False)
    assert start_scheduler(_app(testing=True), in_worker=True) is False
    assert scheduler._thread is None
