"""Nothing of a release is public before its smoke is green.

The smoke runs on what the tag run built: the images pushed untagged, pulled by digest, and the packages
taken from the run's artifacts. Image tags, the Docker Hub page and the GitHub release come after it.
"""
import fnmatch
import hashlib
import os
import re
import subprocess

import pytest

from tests.workflow_support import ROOT, evaluate, github_context, load, render

SMOKE = './.github/workflows/release-smoke.yml'
STD = 'sha256:' + 'a' * 64
FIPS = 'sha256:' + 'b' * 64
RC_TAG = github_context('push', 'refs/tags/v3.0-rc1')
STABLE_TAG = github_context('push', 'refs/tags/v3.0')
BRANCH = github_context('workflow_dispatch', 'refs/heads/feature/x')
REHEARSAL = {'version': '3.0', 'dry_run': True}
STATUS = re.compile(r'\b(success|failure|cancelled|always)\s*\(')
PUBLISHING = ('imagetools create', 'dockerhub-description', 'action-gh-release', 'gh release', 'helm push')


def _jobs():
    return load('build-release.yml')['jobs']


def _needs(job):
    needs = job.get('needs', [])
    return needs if isinstance(needs, list) else [needs]


def _closure(jobs, name):
    seen, todo = set(), list(_needs(jobs[name]))
    while todo:
        n = todo.pop()
        if n not in seen:
            seen.add(n)
            todo += _needs(jobs[n])
    return seen


def _smoke_caller(jobs):
    callers = [n for n, j in jobs.items() if j.get('uses') == SMOKE]
    assert len(callers) == 1, callers
    return callers[0]


def _publishers(jobs):
    """Jobs that tag an image, edit the Docker Hub page, write a GitHub release or push the chart."""
    out = set()
    for name, job in jobs.items():
        text = ' '.join(str(s.get('run', '')) + ' ' + str(s.get('uses', '')) for s in job.get('steps', []))
        if any(p in text for p in PUBLISHING):
            out.add(name)
    return out


def test_the_publishing_jobs_are_the_expected_ones():
    # Guards the detection itself: a publisher it missed would escape the order tests below
    assert _publishers(_jobs()) == {'docker-manifest', 'docker-fips-manifest', 'release', 'publish-chart'}


def test_every_publication_waits_for_the_smoke_and_the_smoke_for_none():
    jobs = _jobs()
    smoke = _smoke_caller(jobs)
    publishers = _publishers(jobs)
    for name in publishers:
        assert smoke in _closure(jobs, name), name
    assert not publishers & _closure(jobs, smoke)


def test_a_red_fips_smoke_also_holds_the_standard_image():
    """The smoke is one call: any of its jobs failing fails the call, which both manifests wait for."""
    jobs = _jobs()
    smoke = _smoke_caller(jobs)
    for name in ('docker-manifest', 'docker-fips-manifest', 'release'):
        assert smoke in _closure(jobs, name), name
    called = load('release-smoke.yml')['jobs']
    assert 'smoke-fips' in called
    for name, job in called.items():
        assert not job.get('continue-on-error') and 'if' not in job, name


def _simulate(github, smoke_result, inputs=None):
    """Result of each job of a run, as GitHub decides it: a job whose `if` names no status function
    also needs every dependency to have succeeded. The build jobs succeed; the smoke gives `smoke_result`."""
    jobs = _jobs()
    smoke = _smoke_caller(jobs)
    results, pending = {}, list(jobs)
    while pending:
        before = len(pending)
        for name in list(pending):
            needs = _needs(jobs[name])
            if any(n not in results for n in needs):
                continue
            pending.remove(name)
            prerelease = 'true' if '-rc' in github['ref'] else 'false'
            ctx = {'github': github, 'inputs': inputs or {},
                   'needs': {n: {'result': results[n], 'outputs': {'prerelease': prerelease}} for n in needs}}
            cond = jobs[name].get('if')
            all_ok = all(results[n] == 'success' for n in needs)
            if cond is None or not STATUS.search(str(cond)):
                runs = all_ok and (cond is None or bool(evaluate(cond, ctx)))
            else:
                status = 'success' if all_ok else 'failure'
                runs = bool(evaluate(cond, ctx, status=status))
            results[name] = (smoke_result if name == smoke else 'success') if runs else 'skipped'
        assert len(pending) < before, f'needs cycle or unknown job among {pending}'
    return results


@pytest.mark.parametrize('github', [RC_TAG, STABLE_TAG], ids=['rc', 'stable'])
def test_a_green_smoke_publishes_after_it(github):
    results = _simulate(github, 'success')
    for name in _publishers(_jobs()) - {'publish-chart'}:
        assert results[name] == 'success', name
    # The chart goes out with a stable release only
    assert results['publish-chart'] == ('skipped' if github is RC_TAG else 'success')
    assert results['smoke-failed'] == 'skipped'


@pytest.mark.parametrize('github', [RC_TAG, STABLE_TAG], ids=['rc', 'stable'])
def test_a_red_smoke_publishes_nothing_and_says_what_is_left(github):
    results = _simulate(github, 'failure')
    for name in _publishers(_jobs()):
        assert results[name] == 'skipped', name
    assert results['smoke-failed'] == 'success'


def test_a_rehearsal_smokes_and_reaches_the_publishing_jobs_whose_steps_it_skips():
    """The steps that publish carry the guard (test_workflow_rehearsal.py); the chart job is all publication."""
    results = _simulate(BRANCH, 'success', REHEARSAL)
    jobs = _jobs()
    for name in _publishers(jobs) - {'publish-chart'} | {_smoke_caller(jobs), 'smoke-targets'}:
        assert results[name] == 'success', name
    assert results['publish-chart'] == results['smoke-failed'] == 'skipped'
    assert _simulate(BRANCH, 'failure', REHEARSAL)['smoke-failed'] == 'skipped'


def test_the_failure_message_names_what_is_left():
    job = _jobs()['smoke-failed']
    text = ' '.join(str(s.get('run', '')) for s in job['steps'])
    assert '::error::' in text and 'untagged' in text
    patterns = [str(s['with']['pattern']) for s in job['steps'] if 'pattern' in s.get('with', {})]
    for name in ('std-digest-amd64', 'std-digest-arm64', 'fips-digest-amd64', 'fips-digest-arm64'):
        assert any(fnmatch.fnmatch(name, p) for p in patterns), name
    assert not any(fnmatch.fnmatch('deb-package', p) for p in patterns)
    # It reports, it deletes nothing
    assert not re.search(r'\b(delete|rm|untag)\b.*(gh|docker|crane|skopeo|curl)|gh api .*-X\s*DELETE', text)


# ---- what the smoke receives -------------------------------------------------------------------

def _call_inputs(github=RC_TAG, inputs=None):
    jobs = _jobs()
    job = jobs[_smoke_caller(jobs)]
    ctx = {'github': {**github, 'sha': 'c' * 40}, 'inputs': inputs or {}, 'needs': {
        'build-deb': {'outputs': {'version': '3.0-rc1'}},
        'smoke-targets': {'outputs': {'image-digest': STD, 'fips-image-digest': FIPS}}}}
    return {k: (render(v, ctx) if isinstance(v, str) else v) for k, v in job['with'].items()}


def test_the_call_hands_over_the_digests_and_the_run_artifacts():
    inputs = _call_inputs()
    assert inputs['version'] == '3.0-rc1'
    assert inputs['image-digest'] == STD and inputs['fips-image-digest'] == FIPS
    assert str(inputs['from-run']).lower() == 'true'
    assert str(inputs['rehearsal']).lower() == 'false' and inputs['ref'] == ''
    assert not [v for v in inputs.values() if 'releases/download' in str(v) or ':3.0' in str(v)]


def test_a_rehearsal_call_hands_over_its_commit_and_its_saved_images():
    inputs = _call_inputs(BRANCH, REHEARSAL)
    assert str(inputs['rehearsal']).lower() == 'true' and inputs['ref'] == 'c' * 40
    checkout = load('release-smoke.yml')['jobs']['smoke-sqlite']['steps'][0]
    assert render(checkout['with']['ref'], {'inputs': {**inputs, 'version': '3.0'}}) == 'c' * 40


@pytest.mark.parametrize('job, digest, local', [
    ('smoke-sqlite', STD, 'ucm-rehearsal:standard'), ('smoke-postgres', STD, 'ucm-rehearsal:standard'),
    ('smoke-fips', FIPS, 'ucm-rehearsal:fips')])
def test_a_rehearsal_call_boots_the_image_its_run_saved(tmp_path, job, digest, local):
    proc, out = _resolve(tmp_path, job, {**_call_inputs(BRANCH, REHEARSAL), 'rehearsal': True})
    assert proc.returncode == 0, proc.stderr
    assert out['ref'] == local
    steps = load('release-smoke.yml')['jobs'][job]['steps']
    pull = next(s for s in steps if s.get('name') == 'Pull Docker image')
    take = next(s for s in steps if s.get('name') == 'Take the image of the rehearsal')
    load_ = next(s for s in steps if s.get('name') == 'Load the image of the rehearsal')
    for inputs, rehearsal in (({'rehearsal': True}, True), ({'rehearsal': False}, False), ({}, False)):
        assert bool(evaluate(pull['if'], {'inputs': inputs})) is not rehearsal
        assert bool(evaluate(take['if'], {'inputs': inputs})) is rehearsal
        assert bool(evaluate(load_['if'], {'inputs': inputs})) is rehearsal
    prefix = 'fips' if job == 'smoke-fips' else 'std'
    assert take['with']['name'] == f'{prefix}-image-amd64'
    # The variant saved under that local tag is the one this job boots
    build = 'build-docker-fips' if job == 'smoke-fips' else 'build-docker'
    save = next(s for s in _jobs()[build]['steps'] if s.get('name') == 'Save the image for the rehearsal smoke')
    assert f'docker tag "$REF" {local}' in save['run']


def test_the_targets_job_reads_the_amd64_digests_of_both_variants():
    job = _jobs()['smoke-targets']
    assert set(_needs(job)) >= {'build-docker', 'build-docker-fips'}
    names = {s.get('with', {}).get('name') for s in job['steps']}
    assert {'std-digest-amd64', 'fips-digest-amd64'} <= names


def _run_targets(tmp_path, files):
    step = next(s for s in _jobs()['smoke-targets']['steps'] if s.get('id') == 'digests')
    for kind, names in files.items():
        (tmp_path / kind).mkdir()
        for n in names:
            (tmp_path / kind / n).touch()
    out = tmp_path / 'out'
    run = render(step['run'], {'runner': {'temp': str(tmp_path)}})
    proc = subprocess.run(['bash', '-e', '-c', run], cwd=tmp_path, capture_output=True, text=True,
                          env={'GITHUB_OUTPUT': str(out), 'PATH': os.environ['PATH']})
    return proc, out.read_text().splitlines() if out.exists() else []


def test_the_targets_step_gives_one_digest_per_variant(tmp_path):
    proc, lines = _run_targets(tmp_path, {'std': ['a' * 64], 'fips': ['b' * 64]})
    assert proc.returncode == 0, proc.stderr
    assert f'std={STD}' in lines and f'fips={FIPS}' in lines


@pytest.mark.parametrize('files', [
    {'std': [], 'fips': ['b' * 64]},
    {'std': ['a' * 64, 'c' * 64], 'fips': ['b' * 64]},
    {'std': ['a' * 64], 'fips': ['not-a-digest']},
])
def test_the_targets_step_refuses_a_missing_or_odd_digest(tmp_path, files):
    proc, _ = _run_targets(tmp_path, files)
    assert proc.returncode != 0


def _resolve(tmp_path, job, inputs):
    step = next(s for s in load('release-smoke.yml')['jobs'][job]['steps'] if s.get('name') == 'Resolve version')
    env = {k: render(v, {'inputs': inputs}) for k, v in step.get('env', {}).items()}
    out = tmp_path / f'{job}.out'
    proc = subprocess.run(['bash', '-e', '-c', step['run']], cwd=ROOT, capture_output=True, text=True,
                          env={**env, 'GITHUB_OUTPUT': str(out), 'PATH': os.environ['PATH']})
    lines = out.read_text().splitlines() if out.exists() else []
    return proc, dict(line.split('=', 1) for line in lines)


IMAGE_JOBS = (('smoke-sqlite', STD), ('smoke-postgres', STD), ('smoke-fips', FIPS))


@pytest.mark.parametrize('job, digest', IMAGE_JOBS)
def test_a_release_call_pulls_and_boots_the_built_digest(tmp_path, job, digest):
    proc, out = _resolve(tmp_path, job, {**_call_inputs(), 'image': 'neyslim/ultimate-ca-manager'})
    assert proc.returncode == 0, proc.stderr
    assert out['ref'] == f'neyslim/ultimate-ca-manager@{digest}'
    steps = load('release-smoke.yml')['jobs'][job]['steps']
    ctx = {'steps': {'ver': {'outputs': out}}}
    image_steps = [s for s in steps if 'docker pull' in str(s.get('run', '')) or str(s.get('name', '')).startswith('Boot')]
    assert len(image_steps) == 2, job
    for s in image_steps:
        text = render(s['run'], ctx)
        assert f'@{digest}' in text and ':3.0-rc1' not in text, (job, s['name'])


@pytest.mark.parametrize('job, _digest', IMAGE_JOBS)
@pytest.mark.parametrize('digest', ['', '3.0-rc1', 'sha256:xyz'])
def test_a_release_call_refuses_anything_but_a_digest(tmp_path, job, _digest, digest):
    key = 'fips-image-digest' if job == 'smoke-fips' else 'image-digest'
    proc, _ = _resolve(tmp_path, job, {**_call_inputs(), key: digest})
    assert proc.returncode != 0, (job, digest)


@pytest.mark.parametrize('job, suffix', [('smoke-sqlite', ''), ('smoke-postgres', ''), ('smoke-fips', '-fips')])
def test_a_manual_smoke_still_pulls_the_published_tag(tmp_path, job, suffix):
    proc, out = _resolve(tmp_path, job, {'version': '3.0', 'image': 'example/ucm'})
    assert proc.returncode == 0, proc.stderr
    assert out['ref'] == f'example/ucm:3.0{suffix}'


# ---- packages: the run's artifacts on a release, the published assets by hand -----------------

def _package_steps():
    steps = load('release-smoke.yml')['jobs']['smoke-packages']['steps']
    take = next(s for s in steps if str(s.get('uses', '')).startswith('actions/download-artifact@'))
    get = next(s for s in steps if s.get('name') == 'Get the package and verify its checksum')
    return take, get


def test_a_release_call_takes_the_packages_from_the_run():
    take, _ = _package_steps()
    assert evaluate(take['if'], {'inputs': {'from-run': True}})
    assert not evaluate(take['if'], {'inputs': {}})
    assert take['with']['pattern'] == '*-package'
    # Every package the release attaches is one the smoke took; the other downloads (image SBOMs
    # and digests) go by a pattern that takes no package artifact
    downloads = [s['with'] for s in _jobs()['release']['steps']
                 if str(s.get('uses', '')).startswith('actions/download-artifact@')]
    released = [w['name'] for w in downloads if 'name' in w]
    assert len(released) == 4 and all(fnmatch.fnmatch(n, take['with']['pattern']) for n in released), released
    others = [w['pattern'] for w in downloads if 'name' not in w]
    assert len(others) + len(released) == len(downloads)
    assert not any(fnmatch.fnmatch(n, p) for n in released for p in others), others
    assert not fnmatch.fnmatch('std-digest-amd64', take['with']['pattern'])
    assert not fnmatch.fnmatch('std-sbom-amd64', take['with']['pattern'])


def _run_get(tmp_path, from_run, pattern, files):
    _, step = _package_steps()
    art = tmp_path / 'run-artifacts'
    art.mkdir()
    for name, body in files.items():
        (art / name).write_bytes(body)
    bindir = tmp_path / 'bin'
    bindir.mkdir()
    gh = bindir / 'gh'
    gh.write_text(f'#!/bin/sh\necho "$@" >> "{tmp_path}/gh.calls"\nexit 1\n')
    gh.chmod(0o755)
    env = {k: render(v, {'inputs': {'from-run': from_run}, 'steps': {'ver': {'outputs': {'version': '3.0-rc1'}}},
                         'matrix': {'pattern': pattern}, 'github': {'token': 't'}})
           for k, v in step.get('env', {}).items()}
    proc = subprocess.run(['bash', '-e', '-c', step['run']], cwd=tmp_path, capture_output=True, text=True,
                          env={**env, 'GITHUB_REPOSITORY': 'o/r', 'PATH': f"{bindir}:{os.environ['PATH']}"})
    return proc, (tmp_path / 'gh.calls').exists()


def _pkg(name, body=b'deb-bytes'):
    # As build-deb writes it: the checksum line carries the published name, "~" turned into "."
    return {name: body, f'{name}.sha256': f'{hashlib.sha256(body).hexdigest()}  {name.replace("~", ".")}\n'.encode()}


def test_a_release_call_checks_the_run_package_under_its_published_name(tmp_path):
    files = {**_pkg('ucm_3.0~rc1_all.deb'), **_pkg('ucm-el9-3.0~rc1-1.el9.noarch.rpm', b'rpm')}
    proc, called_gh = _run_get(tmp_path, True, 'ucm_*_all.deb', files)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert not called_gh
    assert sorted(p.name for p in (tmp_path / 'pkg').iterdir()) == ['ucm_3.0.rc1_all.deb',
                                                                     'ucm_3.0.rc1_all.deb.sha256']


def test_a_release_call_refuses_a_run_package_that_does_not_match_its_checksum(tmp_path):
    files = _pkg('ucm_3.0~rc1_all.deb')
    files['ucm_3.0~rc1_all.deb'] = b'other bytes'
    proc, _ = _run_get(tmp_path, True, 'ucm_*_all.deb', files)
    assert proc.returncode != 0


def test_a_manual_smoke_still_downloads_the_published_asset(tmp_path):
    proc, called_gh = _run_get(tmp_path, False, 'ucm_*_all.deb', _pkg('ucm_3.0~rc1_all.deb'))
    assert called_gh
    assert 'release download v3.0-rc1' in (tmp_path / 'gh.calls').read_text()
    assert proc.returncode != 0  # the stand-in gh fails: nothing is taken from the run instead
