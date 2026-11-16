"""The one-process suite runs on the integration branch of the 3.0 line.

A schedule only runs from the default branch's copy of the workflow, so this line gets the run
on each push of its integration branch instead, superseded runs being cancelled.
"""
import pytest

from tests.workflow_support import evaluate, github_context, load, render

LINE_BRANCH = 'sextant'


def _job():
    return load('tests.yml')['jobs']['test-backend-sequential']


def _ctx(event, ref):
    return {'github': github_context(event, ref), 'steps': {'deterministic': {'outcome': 'success'}}}


@pytest.mark.parametrize('event, ref, runs', [
    ('push', f'refs/heads/{LINE_BRANCH}', True),
    ('push', 'refs/heads/test', True),
    ('push', 'refs/heads/main', True),
    ('schedule', 'refs/heads/main', True),
    ('workflow_dispatch', 'refs/heads/feature/x', True),
    ('push', 'refs/heads/feature/x', False),
    ('pull_request', 'refs/heads/dev', False),
])
def test_when_the_sequential_job_runs(event, ref, runs):
    assert bool(evaluate(_job()['if'], _ctx(event, ref))) is runs


def _checkout_ref(event, ref):
    step = next(s for s in _job()['steps'] if str(s.get('uses', '')).startswith('actions/checkout@'))
    return evaluate(step['with']['ref'], _ctx(event, ref))


def test_a_push_of_the_line_branch_tests_that_branch():
    assert _checkout_ref('push', f'refs/heads/{LINE_BRANCH}') == f'refs/heads/{LINE_BRANCH}'


def _random_step():
    return next(s for s in _job()['steps'] if 'random order' in str(s.get('name', '')))


@pytest.mark.parametrize('event, ref, runs', [
    ('push', f'refs/heads/{LINE_BRANCH}', True),
    ('schedule', 'refs/heads/main', True),
    ('push', 'refs/heads/test', False),
    ('workflow_dispatch', 'refs/heads/dev', False),
])
def test_the_random_order_report_follows_the_same_runs(event, ref, runs):
    step = _random_step()
    assert bool(evaluate(step['if'], _ctx(event, ref))) is runs
    assert step.get('continue-on-error') is True  # a report, not a gate


def _push(ref, sha):
    ctx = _ctx('push', ref)
    ctx['github'].update(workflow='Tests', sha=sha)
    return ctx


def _run_concurrency(ref, sha):
    conc = load('tests.yml')['concurrency']
    ctx = _push(ref, sha)
    return render(conc['group'], ctx), bool(evaluate(conc['cancel-in-progress'], ctx))


def _job_concurrency(ref, sha):
    conc = _job()['concurrency']
    ctx = _push(ref, sha)
    cancel = conc['cancel-in-progress']
    return render(conc['group'], ctx), bool(evaluate(cancel, ctx) if isinstance(cancel, str) else cancel)


@pytest.mark.parametrize('ref', [f'refs/heads/{LINE_BRANCH}', 'refs/heads/test', 'refs/heads/main'])
def test_a_newer_push_never_cancels_nor_queues_the_run(ref):
    """One group per commit: the fast jobs of a new push start at once, the old run is not cancelled."""
    (g1, cancel1), (g2, _) = _run_concurrency(ref, 'a1'), _run_concurrency(ref, 'b2')
    assert g1 != g2 and cancel1 is False


def test_a_feature_branch_push_still_replaces_its_previous_run():
    (g1, cancel), (g2, _) = _run_concurrency('refs/heads/feature/x', 'a1'), _run_concurrency('refs/heads/feature/x', 'b2')
    assert g1 == g2 and cancel is True


def test_one_sequential_run_at_a_time_on_the_line_branch_and_it_finishes():
    ref = f'refs/heads/{LINE_BRANCH}'
    (g1, cancel), (g2, _) = _job_concurrency(ref, 'a1'), _job_concurrency(ref, 'b2')
    # Same group: the newest waits and replaces an older waiting one; the running one is never cancelled
    assert g1 == g2 and cancel is False


@pytest.mark.parametrize('ref', ['refs/heads/test', 'refs/heads/main'])
def test_every_release_commit_keeps_its_sequential_run(ref):
    (g1, _), (g2, _) = _job_concurrency(ref, 'a1'), _job_concurrency(ref, 'b2')
    assert g1 != g2


def test_only_the_sequential_job_has_its_own_group():
    jobs = load('tests.yml')['jobs']
    assert [name for name, job in jobs.items() if 'concurrency' in job] == ['test-backend-sequential']


def test_the_job_leaves_the_first_pass_its_time_whatever_the_random_one_takes():
    """The first pass ran 66 minutes when this was written: the job's limit, less the whole
    limit of the random-order pass, must still cover it with room to grow."""
    assert _job()['timeout-minutes'] - _random_step()['timeout-minutes'] >= 100
