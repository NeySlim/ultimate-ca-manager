"""A pass skipped because another node holds its lease asks for one retry: the scheduler
runs it once the lease is over, a single pending retry however many passes were skipped."""
from datetime import datetime, timedelta

import pytest

from services import scheduler_service
from services.scheduler_service import SchedulerService


@pytest.fixture
def clock(monkeypatch):
    state = {'now': datetime(2044, 1, 1, 12, 0)}
    monkeypatch.setattr(scheduler_service, 'utc_now', lambda: state['now'])
    return state


def _scheduler_with(task, clock):
    s = SchedulerService(wake_interval=60, node_id='retry-test')
    s.register_task('pass', task, interval=86400)
    s.tasks['pass']._created_at = clock['now'] - timedelta(minutes=5)
    return s


def test_a_skipped_pass_runs_once_after_the_lease(clock):
    runs = []

    def task():
        runs.append(clock['now'])
        if len(runs) == 1:
            return {'status': 'skipped', 'reason': 'held elsewhere', 'retry_in': 600}
    s = _scheduler_with(task, clock)
    t = s.tasks['pass']
    s._run_task(t)
    clock['now'] += timedelta(seconds=599)
    assert not t.should_run()
    clock['now'] += timedelta(seconds=1)
    assert t.should_run()
    s._run_task(t)
    # Done: the next pass is the regular one, a day later
    clock['now'] += timedelta(hours=1)
    assert not t.should_run()
    assert len(runs) == 2


def test_passes_skipped_twice_leave_one_retry(clock):
    runs = []

    def task():
        runs.append(clock['now'])
        return {'status': 'skipped', 'reason': 'held elsewhere', 'retry_in': 600} if len(runs) <= 2 else None
    s = _scheduler_with(task, clock)
    t = s.tasks['pass']
    s._run_task(t)
    clock['now'] += timedelta(seconds=60)
    s._run_task(t)  # run by hand meanwhile, skipped too: the retry moves, it is not added
    clock['now'] += timedelta(seconds=599)
    assert not t.should_run()
    clock['now'] += timedelta(seconds=1)
    assert t.should_run()
    s._run_task(t)
    for _ in range(3):
        clock['now'] += timedelta(minutes=10)
        assert not t.should_run()
    assert len(runs) == 3


def test_a_retry_shows_as_the_next_run(clock):
    s = _scheduler_with(lambda: {'status': 'skipped', 'retry_in': 90}, clock)
    s._run_task(s.tasks['pass'])
    assert s.tasks['pass'].to_dict()['next_run'] == (clock['now'] + timedelta(seconds=90)).isoformat() + 'Z'


def test_a_disabled_task_does_not_retry(clock):
    """Regression lock, not a proof: it also passes without the retry code (a disabled task never runs)."""
    s = _scheduler_with(lambda: {'status': 'skipped', 'retry_in': 60}, clock)
    s._run_task(s.tasks['pass'])
    s.disable_task('pass')
    clock['now'] += timedelta(minutes=5)
    assert not s.tasks['pass'].should_run()
