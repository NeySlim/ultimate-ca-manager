"""Single-scheduler lock (#139 root cause): only one process runs the loop."""
import os
import pytest

from services.scheduler_service import SchedulerService


@pytest.fixture
def sched(tmp_path, monkeypatch):
    monkeypatch.setattr('config.settings.DATA_DIR', str(tmp_path), raising=False)
    return SchedulerService(wake_interval=60)


def test_acquire_creates_lock_with_pid(sched):
    assert sched._acquire_singleton_lock() is True
    assert sched._owns_lock and sched._owner_pid == os.getpid()
    with open(sched._lock_path) as f:
        assert f.read().strip() == str(os.getpid())


def test_release_removes_lock(sched):
    sched._acquire_singleton_lock()
    path = sched._lock_path
    sched._release_lock()
    assert not os.path.exists(path)
    assert not sched._owns_lock


def test_live_other_owner_blocks(sched):
    # Pre-write the lock with a live, different pid (init/pid 1 is always alive).
    sched._lock_path = str(sched._lock_path) if sched._lock_path else None
    from config.settings import DATA_DIR
    path = os.path.join(str(DATA_DIR), 'scheduler.lock')
    with open(path, 'w') as f:
        f.write('1')
    assert sched._acquire_singleton_lock() is False
    assert not sched._owns_lock


def test_stale_lock_is_reclaimed(sched):
    from config.settings import DATA_DIR
    path = os.path.join(str(DATA_DIR), 'scheduler.lock')
    with open(path, 'w') as f:
        f.write('2147483646')  # a pid that is not running
    assert sched._acquire_singleton_lock() is True
    assert sched._owner_pid == os.getpid()


def test_forked_worker_does_not_release_masters_lock(sched):
    sched._acquire_singleton_lock()
    path = sched._lock_path
    # Simulate a forked worker: inherited _owns_lock but a different owner pid.
    sched._owner_pid = os.getpid() + 1
    sched._release_lock()
    assert os.path.exists(path)  # master's lock untouched
