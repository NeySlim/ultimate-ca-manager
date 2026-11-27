"""A release is not complete without its FIPS variant: every FIPS job blocks, and the release waits
for the FIPS manifest; the FIPS image check also runs on the release branches."""
import pytest

from tests.workflow_support import evaluate, github_context, load

FILES = ('build-release.yml', 'release-smoke.yml', 'tests.yml')


def _fips_jobs():
    for f in FILES:
        for name, job in load(f)['jobs'].items():
            if 'fips' in name.lower() or 'fips' in str(job.get('name', '')).lower():
                yield f, name, job


def test_the_fips_jobs_are_the_expected_ones():
    assert {(f, n) for f, n, _ in _fips_jobs()} == {
        ('build-release.yml', 'build-docker-fips'), ('build-release.yml', 'docker-fips-manifest'),
        ('release-smoke.yml', 'smoke-fips'), ('tests.yml', 'build-test-fips')}


def test_no_fips_job_or_step_may_fail_without_failing_the_run():
    soft = []
    for f, name, job in _fips_jobs():
        if job.get('continue-on-error'):
            soft.append(f'{f}:{name}')
        soft += [f"{f}:{name}:{s.get('name') or s.get('uses')}" for s in job.get('steps', [])
                 if s.get('continue-on-error')]
    assert not soft, soft


def test_the_release_waits_for_the_fips_manifest():
    jobs = load('build-release.yml')['jobs']
    assert 'docker-fips-manifest' in jobs['release']['needs']
    assert set(jobs['docker-fips-manifest']['needs']) >= {'build-docker-fips'}


@pytest.mark.parametrize('branch', ['dev', 'main'])
def test_the_fips_image_check_runs_on_each_line_branch(branch):
    job = load('tests.yml')['jobs']['build-test-fips']
    assert evaluate(job['if'], {'github': github_context('push', f'refs/heads/{branch}')})


@pytest.mark.parametrize('event, ref', [('pull_request', 'refs/heads/dev'), ('push', 'refs/heads/feature/x'),
                                         ('push', 'refs/heads/retired'),
                                         ('workflow_dispatch', 'refs/heads/dev')])
def test_the_fips_image_check_stays_off_pull_requests_and_feature_branches(event, ref):
    job = load('tests.yml')['jobs']['build-test-fips']
    assert not evaluate(job['if'], {'github': github_context(event, ref)})
