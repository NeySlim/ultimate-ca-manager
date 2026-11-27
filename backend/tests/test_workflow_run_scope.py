"""What each run of tests.yml plays: one full run per commit (the push), a manual run adds only
the one-process suite and the HA bench unless `full` is ticked, and the PostgreSQL job in two parts."""
import shlex

import pytest

from tests.workflow_support import evaluate, github_context, load, render, triggers

DISPATCH_ONLY = {'test-backend-sequential', 'test-ha-bench'}
PUSH_ONLY = {'build-test-fips'}


def _jobs():
    return load('tests.yml')['jobs']


def _ctx(event, ref, **inputs):
    return {'github': github_context(event, ref), 'inputs': inputs,
            'steps': {'deterministic': {'outcome': 'success'}}}


def _running(event, ref, **inputs):
    return {name for name, job in _jobs().items() if evaluate(job['if'], _ctx(event, ref, **inputs))}


def test_a_push_of_test_starts_no_run():
    branches = triggers(load('tests.yml'))['push']['branches']
    assert 'test' not in branches
    assert {'main', 'dev', 'v*'} <= set(branches)


def test_every_job_says_when_it_runs():
    assert [name for name, job in _jobs().items() if 'if' not in job] == []


@pytest.mark.parametrize('ref', ['refs/heads/dev', 'refs/heads/main', 'refs/heads/feature/x'])
def test_a_manual_run_without_full_plays_only_what_it_adds(ref):
    assert _running('workflow_dispatch', ref, ha=True, full=False) == DISPATCH_ONLY
    assert _running('workflow_dispatch', ref, ha=False, full=False) == {'test-backend-sequential'}


@pytest.mark.parametrize('ref', ['refs/heads/dev', 'refs/heads/feature/x'])
def test_a_manual_run_with_full_plays_what_a_push_plays_but_the_fips_build(ref):
    pushed = _running('push', 'refs/heads/dev')
    assert pushed == set(_jobs()) - DISPATCH_ONLY
    assert _running('workflow_dispatch', ref, ha=True, full=True) == (pushed - PUSH_ONLY) | DISPATCH_ONLY


def test_pull_requests_and_the_nightly_run_keep_their_jobs():
    assert _running('pull_request', 'refs/pull/1/merge') == set(_jobs()) - DISPATCH_ONLY - PUSH_ONLY
    assert _running('schedule', 'refs/heads/main') == {'test-backend-sequential'}


# The two pytest commands of the single PostgreSQL job before it was split
BEFORE = [
    ['-m', 'postgres', 'tests/'],
    ['tests/test_backup_cross_installation.py', 'tests/test_restore_reference_resolution_pg.py',
     'tests/test_database_migration_matrix.py', 'tests/test_database_migration_scale.py',
     'tests/test_database_admin.py', 'tests/test_migration_runner_pg.py',
     'tests/test_scep_intune_ca_lock_pg.py'],
]


def _pg_parts():
    job = _jobs()['test-backend-postgres']
    parts = job['strategy']['matrix']['include']
    return job, parts


def _pytest_args(job, matrix):
    run = next(s['run'] for s in job['steps'] if 'pytest' in s.get('run', ''))
    text = render(run, {'matrix': matrix}).replace('\\\n', ' ')
    out = []
    for line in text.splitlines():
        words = shlex.split(line, comments=True)
        if words[:1] == ['pytest']:
            out.append([w for w in words[1:] if w != '--tb=short'])
    return out


def test_the_two_postgres_parts_together_run_the_commands_of_before():
    job, parts = _pg_parts()
    assert len(parts) == 2 and job['strategy'].get('fail-fast') is False
    played = [args for part in parts for args in _pytest_args(job, part)]
    assert sorted(played) == sorted(BEFORE)


def test_each_postgres_part_has_its_service_and_the_unprivileged_role():
    job, _ = _pg_parts()
    assert job['services']['postgres']['image'].startswith('postgres:')
    role = next(s['run'] for s in job['steps'] if 'ucm_migtest' in s.get('run', ''))
    assert 'NOSUPERUSER' in role and 'CREATE DATABASE ucm_migtest' in role
    env = next(s['env'] for s in job['steps'] if 'pytest' in s.get('run', ''))
    assert env['UCM_TEST_PG_URL'].startswith('postgresql://ucm_migtest:') and env['UCM_TEST_POSTGRES_URL']
