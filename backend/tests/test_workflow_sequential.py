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


def test_a_newer_push_of_the_line_branch_cancels_the_running_one():
    conc = load('tests.yml')['concurrency']
    ctx = _ctx('push', f'refs/heads/{LINE_BRANCH}')
    ctx['github'].update(workflow='Tests', sha='abc123')
    assert evaluate(conc['cancel-in-progress'], ctx) is True
    assert render(conc['group'], ctx) == f'tests-Tests-push-refs/heads/{LINE_BRANCH}'
