"""The one-process suite runs at night and on demand, never on a push.

Every push is validated in one process before it leaves: a push run would only play it a second time.
"""
import pytest

from tests.workflow_support import evaluate, github_context, load, render

LINE_BRANCH = 'dev'
# Frozen at the last 3.0 release candidate once merged into dev: it must start nothing any more
RETIRED_BRANCH = 'sextant'


def _job():
    return load('tests.yml')['jobs']['test-backend-sequential']


def _ctx(event, ref):
    return {'github': github_context(event, ref), 'steps': {'deterministic': {'outcome': 'success'}}}


@pytest.mark.parametrize('event, ref, runs', [
    ('workflow_dispatch', f'refs/heads/{LINE_BRANCH}', True),
    ('push', f'refs/heads/{LINE_BRANCH}', False),
    ('push', 'refs/heads/test', False),
    ('push', 'refs/heads/main', False),
    ('schedule', 'refs/heads/main', True),
    ('workflow_dispatch', 'refs/heads/feature/x', True),
    ('push', 'refs/heads/feature/x', False),
    ('pull_request', 'refs/heads/dev', False),
])
def test_when_the_sequential_job_runs(event, ref, runs):
    assert bool(evaluate(_job()['if'], _ctx(event, ref))) is runs


def _checkout_ref(event, ref, sha='c0ffee'):
    step = next(s for s in _job()['steps'] if str(s.get('uses', '')).startswith('actions/checkout@'))
    ctx = _ctx(event, ref)
    ctx['github'].update(sha=sha)
    return evaluate(step['with']['ref'], ctx)


def test_a_manual_run_of_the_line_branch_tests_its_own_commit():
    """Not the branch: a job that waited in its group would find a newer tip there."""
    assert _checkout_ref('workflow_dispatch', f'refs/heads/{LINE_BRANCH}', 'a1b2c3') == 'a1b2c3'
    assert _checkout_ref('workflow_dispatch', 'refs/heads/main', 'd4e5f6') == 'd4e5f6'


def test_the_nightly_run_tests_dev():
    assert _checkout_ref('schedule', 'refs/heads/main') == 'dev'


def _random_step():
    return next(s for s in _job()['steps'] if 'random order' in str(s.get('name', '')))


@pytest.mark.parametrize('event, ref, runs', [
    ('workflow_dispatch', f'refs/heads/{LINE_BRANCH}', True),
    ('push', f'refs/heads/{LINE_BRANCH}', False),
    ('schedule', 'refs/heads/main', True),
    ('push', 'refs/heads/test', False),
    ('workflow_dispatch', 'refs/heads/feature/x', False),
    ('workflow_dispatch', f'refs/heads/{RETIRED_BRANCH}', False),
])
def test_the_random_order_report_follows_the_same_runs(event, ref, runs):
    step = _random_step()
    assert bool(evaluate(step['if'], _ctx(event, ref))) is runs
    assert step.get('continue-on-error') is True  # a report, not a gate


def _run(ref, sha, event='push'):
    ctx = _ctx(event, ref)
    ctx['github'].update(workflow='Tests', sha=sha)
    return ctx


def _run_concurrency(ref, sha, event='push'):
    conc = load('tests.yml')['concurrency']
    ctx = _run(ref, sha, event)
    return render(conc['group'], ctx), bool(evaluate(conc['cancel-in-progress'], ctx))


def _job_concurrency(ref, sha, event='push'):
    conc = _job()['concurrency']
    ctx = _run(ref, sha, event)
    cancel = conc['cancel-in-progress']
    return render(conc['group'], ctx), bool(evaluate(cancel, ctx) if isinstance(cancel, str) else cancel)


@pytest.mark.parametrize('ref', [f'refs/heads/{LINE_BRANCH}', 'refs/heads/test', 'refs/heads/main'])
def test_a_newer_push_never_cancels_nor_queues_the_run(ref):
    """One group per commit: the fast jobs of a new push start at once, the old run is not cancelled."""
    (g1, cancel1), (g2, _) = _run_concurrency(ref, 'a1'), _run_concurrency(ref, 'b2')
    assert g1 != g2 and cancel1 is False


def test_a_manual_run_of_the_line_branch_is_not_cancelled_by_a_newer_commit_nor_by_its_push():
    ref = f'refs/heads/{LINE_BRANCH}'
    (g1, cancel1), (g2, _) = (_run_concurrency(ref, 'a1', 'workflow_dispatch'),
                              _run_concurrency(ref, 'b2', 'workflow_dispatch'))
    assert g1 != g2 and cancel1 is False
    assert g1 != _run_concurrency(ref, 'a1')[0]  # the push of the same commit runs beside it


def test_a_feature_branch_push_still_replaces_its_previous_run():
    (g1, cancel), (g2, _) = _run_concurrency('refs/heads/feature/x', 'a1'), _run_concurrency('refs/heads/feature/x', 'b2')
    assert g1 == g2 and cancel is True


def test_one_sequential_run_at_a_time_on_the_line_branch_and_it_finishes():
    ref = f'refs/heads/{LINE_BRANCH}'
    (g1, cancel), (g2, _) = (_job_concurrency(ref, 'a1', 'workflow_dispatch'),
                             _job_concurrency(ref, 'b2', 'workflow_dispatch'))
    # Same group: the newest waits and replaces an older waiting one; the running one is never cancelled
    assert g1 == g2 and cancel is False


def test_a_manual_run_of_the_retired_branch_gets_one_group_per_commit():
    ref = f'refs/heads/{RETIRED_BRANCH}'
    (g1, _), (g2, _) = (_job_concurrency(ref, 'a1', 'workflow_dispatch'),
                        _job_concurrency(ref, 'b2', 'workflow_dispatch'))
    assert g1 != g2


def test_only_the_sequential_job_has_its_own_group():
    jobs = load('tests.yml')['jobs']
    assert [name for name, job in jobs.items() if 'concurrency' in job] == ['test-backend-sequential']


def test_the_job_limit_leaves_the_random_pass_its_whole_step():
    """Setup and the first pass took 72 minutes when this was written: with room to grow,
    they must end before the job's limit could cut the random-order pass, which only reports."""
    assert _job()['timeout-minutes'] - _random_step()['timeout-minutes'] >= 105


def test_the_random_pass_stops_itself_before_its_step_is_killed():
    """Killed by the step limit, it would write no summary: neither seed nor replay command."""
    import re
    step = _random_step()
    own = [int(m) for m in re.findall(r'\btimeout (\d+)m pytest ', step['run'])]
    assert len(own) == 1 and own[0] < step['timeout-minutes'], (own, step['timeout-minutes'])


def _pytest_commands(job):
    lines = [line.strip() for step in job['steps'] for line in str(step.get('run', '')).splitlines()]
    return [line for line in lines if line.startswith(('pytest ', 'timeout 40m pytest '))]


def _marker(command):
    import shlex
    words = shlex.split(command)
    return words[words.index('-m') + 1] if '-m' in words else None


def test_the_one_process_runs_leave_the_slow_tests_to_the_shards():
    """An hour of fault scenarios in one process would pass the job's time limit; the shards run them."""
    commands = _pytest_commands(_job())
    assert len(commands) == 2, commands
    markers = {_marker(c) for c in commands}
    assert len(markers) == 1 and None not in markers, commands
    # A command-line -m replaces the one of addopts: the HA bench must stay out by name
    chosen = _collected(['-m', markers.pop(), SLOW_FILE, HA_FILE, PLAIN_TEST])
    assert chosen == [PLAIN_TEST], chosen


SLOW_FILE = 'tests/test_package_leftover_retry_data_link.py'
HA_FILE = 'tests/ha/test_startup.py'
PLAIN_TEST = 'tests/test_workflow_sequential.py::test_only_the_sequential_job_has_its_own_group'


def _collected(arguments):
    import os
    import subprocess
    import sys
    backend = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    out = subprocess.run(
        [sys.executable, '-m', 'pytest', '--collect-only', '-q', '-p', 'no:cacheprovider', *arguments],
        cwd=backend, capture_output=True, text=True, timeout=120)
    return [line for line in out.stdout.splitlines() if '::' in line]


def test_the_shards_still_run_the_slow_tests():
    """No -m on their command, and none from the configuration either: collected as they run."""
    shard = _pytest_commands(load('tests.yml')['jobs']['test-backend'])
    assert shard and all(_marker(c) is None for c in shard), shard
    assert any(line.startswith(SLOW_FILE) for line in _collected([SLOW_FILE]))
