"""Image publication of Build & Release: nothing is pushed to a public registry outside a tag run (a
rehearsal pushes to its own), `latest` goes only to a stable version that is the highest published
one, and the line tag (`3`, `3-fips`) to the highest stable of its major (scripts/ci/release_version.py)."""
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
REHEARSAL = {'version': '3.0', 'dry_run': True}

pytestmark = pytest.mark.skipif(shutil.which('bash') is None, reason='bash is required')


def _jobs():
    return load('build-release.yml')['jobs']


def _cli(version, tags, cmd='latest'):
    return subprocess.run([sys.executable, str(SCRIPT), cmd, version], input='\n'.join(tags),
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


@pytest.mark.parametrize('tags, version, expected', [
    (['refs/tags/v2.254.4', 'refs/tags/v3.0'], '3.0', '3'),
    (['refs/tags/v3.0', 'refs/tags/v3.1-rc1'], '3.1-rc1', ''),                  # never a RC
    (['refs/tags/v3.0', 'refs/tags/v3.1'], '3.0', ''),                         # overtaken in its major
    (['refs/tags/v3.0', 'refs/tags/v3.1', 'refs/tags/v2.254.5'], '2.254.5', '2'),  # a higher major does not count
    (['refs/tags/v2.254.4', 'refs/tags/v3.0', 'refs/tags/v2.254.5'], '2.254.4', ''),
    (['refs/tags/v3.0', 'refs/tags/v3.1-rc1'], '3.0', '3'),                     # a RC above does not count
    (['refs/tags/v3.9', 'refs/tags/v3.10'], '3.9', ''),                        # numeric, not text order
    (['refs/tags/v3.0', 'refs/tags/vnext', 'refs/tags/v3'], '3.0', '3'),       # foreign tags ignored
    ([], '3.0', '3'),
])
def test_the_line_rule(tags, version, expected):
    result = _cli(version, tags, 'line')
    assert result.returncode == 0, result.stderr
    assert result.stdout == expected + '\n'


def test_the_line_rule_refuses_an_invalid_version():
    assert _cli('3.0;id', ['refs/tags/v3.0'], 'line').returncode == 1


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


def _decide(job, step_id='latest'):
    steps = [s for s in _jobs()[job]['steps'] if s.get('id') == step_id]
    assert len(steps) == 1, job
    return steps[0]


def _run_decide(tmp_path, job, version, ref, tags, exit_code=0, inputs=None, step_id='latest'):
    step = _decide(job, step_id)
    bindir = _fake_git(tmp_path, tags, exit_code)
    out = tmp_path / 'gh_output'
    env = {k: render(v, {'needs': {'build-deb': {'outputs': {'version': version}}}, 'inputs': inputs or {}})
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
@pytest.mark.parametrize('version, tags, expected', [
    ('3.0', ['refs/tags/v2.254.1'], 'true'),
    ('2.254.5', ['refs/tags/v3.0'], 'false'),
    ('3.0-rc1', ['refs/tags/v2.254.1'], 'false'),
])
def test_a_rehearsal_on_a_branch_decides_as_its_tag_run_would(tmp_path, job, version, tags, expected):
    proc, out = _run_decide(tmp_path, job, version, 'refs/heads/feature/x', tags, inputs=REHEARSAL)
    assert proc.returncode == 0, proc.stderr
    assert out == f'latest={expected}'


@pytest.mark.parametrize('job', [j for j, _ in MANIFESTS] + ['release'])
def test_an_unreachable_remote_decides_nothing(tmp_path, job):
    proc, out = _run_decide(tmp_path, job, '3.0', 'refs/tags/v3.0', [], exit_code=128)
    assert proc.returncode != 0
    assert not out


# The line tag is decided like `latest`: tag runs and rehearsals only, from the published tags
@pytest.mark.parametrize('job', [j for j, _ in MANIFESTS])
@pytest.mark.parametrize('version, ref, tags, inputs, expected', [
    ('3.0', 'refs/tags/v3.0', ['refs/tags/v2.254.4', 'refs/tags/v3.0'], None, '3'),
    ('2.254.5', 'refs/tags/v2.254.5', ['refs/tags/v3.0', 'refs/tags/v2.254.5'], None, '2'),
    ('3.0', 'refs/tags/v3.0', ['refs/tags/v3.0', 'refs/tags/v3.1'], None, ''),
    ('3.1-rc1', 'refs/tags/v3.1-rc1', ['refs/tags/v3.0', 'refs/tags/v3.1-rc1'], None, ''),
    ('3.0', 'refs/heads/feature/x', ['refs/tags/v2.254.4'], None, ''),          # not a tag run
    ('3.0', 'refs/heads/feature/x', ['refs/tags/v2.254.4'], REHEARSAL, '3'),    # a rehearsal decides as its tag
    ('3.0-rc1', 'refs/heads/feature/x', [], {'version': '3.0-rc1', 'dry_run': True}, ''),
])
def test_the_line_step_reads_the_published_tags(tmp_path, job, version, ref, tags, inputs, expected):
    proc, out = _run_decide(tmp_path, job, version, ref, tags, inputs=inputs, step_id='line')
    assert proc.returncode == 0, proc.stderr
    assert out == f'line={expected}'


@pytest.mark.parametrize('job', [j for j, _ in MANIFESTS])
def test_an_unreachable_remote_decides_no_line(tmp_path, job):
    proc, out = _run_decide(tmp_path, job, '3.0', 'refs/tags/v3.0', [], exit_code=128, step_id='line')
    assert proc.returncode != 0
    assert not out


def test_the_manifest_jobs_can_run_the_parser():
    for job, _ in MANIFESTS:
        steps = _jobs()[job]['steps']
        idx = min(i for i, s in enumerate(steps) if s.get('id') in ('latest', 'line'))
        checkouts = [s for s in steps[:idx] if str(s.get('uses', '')).startswith('actions/checkout@')]
        assert checkouts, job
        sparse = (checkouts[0].get('with') or {}).get('sparse-checkout')
        assert sparse is None or 'scripts/ci' in str(sparse).split(), job


# ---- the tags the manifests and the release apply ------------------------------------------------

def _meta_tags(job, latest, version='3.0', line=''):
    meta = next(s for s in _jobs()[job]['steps'] if s.get('id') == 'meta')
    ctx = {'github': TAG_RUN, 'steps': {'latest': {'outputs': {'latest': latest}}, 'line': {'outputs': {'line': line}}},
           'needs': {'build-deb': {'outputs': {'version': version}}}}
    return [render(line.strip(), ctx) for line in meta['with']['tags'].splitlines() if line.strip()]


def _enabled(lines):
    """The tags docker/metadata-action applies: a raw value, unless `enable` renders false."""
    tags = []
    for entry in lines:
        opts = dict(kv.split('=', 1) for kv in entry.removeprefix('type=raw,').split(','))
        if opts.get('enable', 'true') == 'true':
            tags.append(opts['value'])
    return tags


@pytest.mark.parametrize('job, suffix', [('docker-manifest', ''), ('docker-fips-manifest', '-fips')])
@pytest.mark.parametrize('version, latest, line, expected', [
    ('3.0', 'true', '3', ['3.0', 'latest', '3']),
    ('2.254.5', 'false', '2', ['2.254.5', '2']),       # the 2.x line keeps its own tag after 3.0
    ('3.0', 'false', '', ['3.0']),                     # overtaken in its major
    ('3.0-rc1', 'false', '', ['3.0-rc1']),             # a RC: its version only
])
def test_the_line_image_tag_follows_its_step(job, suffix, version, latest, line, expected):
    tags = _enabled(_meta_tags(job, latest, version, line))
    assert sorted(tags) == sorted(t + suffix if t != 'latest' else 'latest' + suffix for t in expected)


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


# ---- nothing is pushed to a public registry outside a tag run ------------------------------------

@pytest.mark.parametrize('job', ['docker-manifest', 'docker-fips-manifest', 'release', 'release-smoke'])
def test_the_publishing_jobs_also_run_in_a_rehearsal(job):
    """Their publishing steps carry the guard instead (test_workflow_rehearsal.py)."""
    assert 'if' not in _jobs()[job], job


def _push_steps():
    for job in ('build-docker', 'build-docker-fips'):
        steps = [s for s in _jobs()[job]['steps'] if s.get('id') == 'push']
        assert len(steps) == 1, job
        yield job, steps[0]


def _rehearse_steps():
    for job in ('build-docker', 'build-docker-fips'):
        steps = [s for s in _jobs()[job]['steps'] if s.get('id') == 'rehearse']
        assert len(steps) == 1, job
        yield job, steps[0]


def _names(step):
    outputs = render(step['with']['outputs'], {'env': {'REGISTRY': 'ghcr.io'},
                                               'steps': {'image': {'outputs': {'name': 'o/r'}}}})
    opts = outputs.split(',')
    assert opts.count('push=true') == 1 and not step['with'].get('push'), outputs
    return outputs


@pytest.mark.parametrize('ctx, inputs, published', [(TAG_RUN, {}, True), (BRANCH_RUN, REHEARSAL, False)],
                         ids=['tag', 'rehearsal'])
def test_a_rehearsal_pushes_to_its_own_registry_and_a_tag_run_to_the_public_ones(ctx, inputs, published):
    for (job, push), (_, rehearse) in zip(_push_steps(), _rehearse_steps()):
        assert bool(evaluate(push['if'], {'github': ctx, 'inputs': inputs})) is published, job
        assert bool(evaluate(rehearse['if'], {'github': ctx, 'inputs': inputs})) is not published, job
        assert '"name=ghcr.io/o/r,neyslim/ultimate-ca-manager"' in _names(push), job
        assert _names(rehearse).startswith('type=image,name=localhost:5000/o/r,'), job


@pytest.mark.parametrize('ctx, inputs, repository', [
    (TAG_RUN, {}, 'ghcr.io/o/r'), (BRANCH_RUN, REHEARSAL, 'localhost:5000/o/r')], ids=['tag', 'rehearsal'])
def test_the_digest_of_the_push_that_ran_is_handed_over(ctx, inputs, repository):
    """A tag run hands over the digest pushed to the registry, a rehearsal that of its own registry."""
    for job in ('build-docker', 'build-docker-fips'):
        steps = {s.get('name'): s for s in _jobs()[job]['steps']}
        built = steps['Digest of the build']
        pushed = 'push' if not inputs else 'rehearse'
        sctx = {'github': ctx, 'inputs': inputs, 'env': {'REGISTRY': 'ghcr.io'},
                'steps': {'image': {'outputs': {'name': 'o/r'}}, pushed: {'outputs': {'digest': 'sha256:' + 'a' * 64}}}}
        assert render(built['env']['DIGEST'], sctx) == 'sha256:' + 'a' * 64, job
        assert render(built['env']['REPOSITORY'], sctx) == repository, job
        for name in ('Export digest', 'Upload digest'):
            assert 'if' not in steps[name], (job, name)
        assert steps['Export digest']['env']['DIGEST'] == '${{ steps.built.outputs.digest }}'

