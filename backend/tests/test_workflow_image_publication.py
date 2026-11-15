"""Image publication of Build & Release: nothing is pushed outside a tag run, and `latest` goes only
to a stable version that is the highest published one (scripts/ci/release_version.py)."""
import os
import shutil
import stat
import subprocess
import sys

import pytest

from tests.workflow_support import ROOT, evaluate, github_context, load, render

SCRIPT = ROOT / 'scripts' / 'ci' / 'release_version.py'
MANIFESTS = (('docker-manifest', 'latest'), ('docker-fips-manifest', 'latest-fips'))
BRANCH_RUN = github_context('workflow_dispatch', 'refs/heads/feature/x')
TAG_RUN = github_context('push', 'refs/tags/v3.0')

pytestmark = pytest.mark.skipif(shutil.which('bash') is None, reason='bash is required')


def _jobs():
    return load('build-release.yml')['jobs']


def _cli(version, tags):
    return subprocess.run([sys.executable, str(SCRIPT), 'latest', version], input='\n'.join(tags),
                          capture_output=True, text=True)


# ---- the rule ------------------------------------------------------------------------------------

@pytest.mark.parametrize('tags, version, expected', [
    (['refs/tags/v2.254.1', 'refs/tags/v3.0'], '3.0', 'true'),
    (['refs/tags/v3.0', 'refs/tags/v3.1'], '3.1', 'true'),
    (['refs/tags/v3.0', 'refs/tags/v3.1-rc1'], '3.1-rc1', 'false'),         # never a RC
    (['refs/tags/v3.0', 'refs/tags/v3.1-rc1', 'refs/tags/v3.0'], '3.0', 'true'),  # a RC above does not count
    (['refs/tags/v2.254.1', 'refs/tags/v3.0', 'refs/tags/v2.254.2'], '2.254.2', 'false'),  # older line
    (['refs/tags/v2.254.1', 'refs/tags/v3.0-rc1', 'refs/tags/v2.254.2'], '2.254.2', 'true'),
    (['refs/tags/v3.0', 'refs/tags/v3.1', 'refs/tags/v3.0'], '3.0', 'false'),   # a rebuild of an older tag
    (['refs/tags/v3.9', 'refs/tags/v3.10'], '3.9', 'false'),                # numeric, not text order
    (['refs/tags/v3.0', 'refs/tags/vnext', 'refs/tags/v4.0.0'], '3.0', 'true'),  # foreign tags ignored
])
def test_the_latest_rule(tags, version, expected):
    result = _cli(version, tags)
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == expected


def test_the_rule_refuses_an_invalid_version():
    assert _cli('3.0;id', ['refs/tags/v3.0']).returncode == 1


# ---- the step that applies it, run for real against a stand-in git -------------------------------

def _fake_git(tmp_path, tags, exit_code=0):
    bindir = tmp_path / 'bin'
    bindir.mkdir()
    listing = tmp_path / 'tags.txt'
    listing.write_text(''.join(f'{"0" * 40}\t{t}\n' for t in tags))
    git = bindir / 'git'
    git.write_text('#!/bin/sh\n'
                   f'echo "$@" >> "{tmp_path}/git.calls"\n'
                   f'[ "$1" = ls-remote ] || exit 99\n'
                   f'cat "{listing}"\n'
                   f'exit {exit_code}\n')
    git.chmod(git.stat().st_mode | stat.S_IEXEC)
    return bindir


def _decide(job):
    steps = [s for s in _jobs()[job]['steps'] if s.get('id') == 'latest']
    assert len(steps) == 1, job
    return steps[0]


def _run_decide(tmp_path, job, version, ref, tags, exit_code=0):
    step = _decide(job)
    bindir = _fake_git(tmp_path, tags, exit_code)
    out = tmp_path / 'gh_output'
    env = {k: render(v, {'needs': {'build-deb': {'outputs': {'version': version}}}})
           for k, v in (step.get('env') or {}).items()}
    proc = subprocess.run(['bash', '-e', '-c', step['run']], cwd=ROOT, capture_output=True, text=True,
                          env={**env, 'PATH': f"{bindir}:{os.environ['PATH']}", 'GITHUB_REF': ref,
                               'GITHUB_OUTPUT': str(out)})
    return proc, out.read_text().strip() if out.exists() else None


@pytest.mark.parametrize('job', [j for j, _ in MANIFESTS] + ['release'])
@pytest.mark.parametrize('version, tags, expected', [
    ('3.0', ['refs/tags/v2.254.1', 'refs/tags/v3.0'], 'true'),
    ('2.254.2', ['refs/tags/v3.0', 'refs/tags/v2.254.2'], 'false'),
    ('3.1-rc1', ['refs/tags/v3.0', 'refs/tags/v3.1-rc1'], 'false'),
])
def test_the_step_reads_the_published_tags(tmp_path, job, version, tags, expected):
    proc, out = _run_decide(tmp_path, job, version, f'refs/tags/v{version}', tags)
    assert proc.returncode == 0, proc.stderr
    assert out == f'latest={expected}'
    assert 'ls-remote' in (tmp_path / 'git.calls').read_text()


@pytest.mark.parametrize('job', [j for j, _ in MANIFESTS] + ['release'])
def test_the_step_never_gives_latest_without_a_tag(tmp_path, job):
    proc, out = _run_decide(tmp_path, job, '3.0', 'refs/heads/feature/x', ['refs/tags/v2.254.1'])
    assert proc.returncode == 0, proc.stderr
    assert out == 'latest=false'


@pytest.mark.parametrize('job', [j for j, _ in MANIFESTS] + ['release'])
def test_an_unreachable_remote_decides_nothing(tmp_path, job):
    proc, out = _run_decide(tmp_path, job, '3.0', 'refs/tags/v3.0', [], exit_code=128)
    assert proc.returncode != 0
    assert not out


def test_the_manifest_jobs_can_run_the_parser():
    for job, _ in MANIFESTS:
        steps = _jobs()[job]['steps']
        idx = next(i for i, s in enumerate(steps) if s.get('id') == 'latest')
        checkouts = [s for s in steps[:idx] if str(s.get('uses', '')).startswith('actions/checkout@')]
        assert checkouts, job
        sparse = (checkouts[0].get('with') or {}).get('sparse-checkout')
        assert sparse is None or 'scripts/ci' in str(sparse).split(), job


# ---- the tags the manifests and the release apply ------------------------------------------------

def _meta_tags(job, latest, version='3.0'):
    meta = next(s for s in _jobs()[job]['steps'] if s.get('id') == 'meta')
    ctx = {'github': TAG_RUN, 'steps': {'latest': {'outputs': {'latest': latest}}},
           'needs': {'build-deb': {'outputs': {'version': version}}}}
    return [render(line.strip(), ctx) for line in meta['with']['tags'].splitlines() if line.strip()]


@pytest.mark.parametrize('job, tag', MANIFESTS)
@pytest.mark.parametrize('latest', ['true', 'false'])
def test_the_latest_image_tag_follows_the_step(job, tag, latest):
    lines = _meta_tags(job, latest)
    assert f'type=raw,value={tag},enable={latest}' in lines, lines
    suffix = '-fips' if 'fips' in job else ''
    assert f'type=raw,value=3.0{suffix}' in lines, lines


@pytest.mark.parametrize('latest', ['true', 'false'])
def test_the_github_release_marks_latest_by_the_same_rule(latest):
    rel = next(s for s in _jobs()['release']['steps'] if s.get('name') == 'Create release')
    ctx = {'github': TAG_RUN, 'steps': {'latest': {'outputs': {'latest': latest}}}}
    assert render(rel['with']['make_latest'], ctx) == latest


# ---- nothing is pushed outside a tag run ---------------------------------------------------------

@pytest.mark.parametrize('job', ['docker-manifest', 'docker-fips-manifest', 'release', 'release-smoke'])
@pytest.mark.parametrize('ctx, runs', [(BRANCH_RUN, False), (TAG_RUN, True)])
def test_publishing_jobs_run_on_a_tag_only(job, ctx, runs):
    cond = _jobs()[job].get('if')
    assert cond is not None, job
    assert bool(evaluate(cond, {'github': ctx, 'needs': {}})) is runs, job


def _push_steps():
    for job in ('build-docker', 'build-docker-fips'):
        steps = [s for s in _jobs()[job]['steps'] if s.get('id') == 'push']
        assert len(steps) == 1, job
        yield job, steps[0]


@pytest.mark.parametrize('ctx, pushed', [(BRANCH_RUN, False), (TAG_RUN, True)])
def test_a_branch_run_builds_the_images_without_pushing_them(ctx, pushed):
    for job, step in _push_steps():
        with_ = step['with']
        assert not with_.get('push'), job
        outputs = render(with_['outputs'], {'github': ctx, 'env': {'REGISTRY': 'ghcr.io'},
                                            'steps': {'image': {'outputs': {'name': 'o/r'}}}})
        opts = outputs.split(',')
        assert opts.count(f'push={str(pushed).lower()}') == 1, (job, outputs)
        assert not [o for o in opts if o.startswith('push=') and o != f'push={str(pushed).lower()}'], outputs
        # The job itself still runs on a branch: the build is the check
        assert 'if' not in _jobs()[job] or evaluate(_jobs()[job]['if'], {'github': BRANCH_RUN}), job
