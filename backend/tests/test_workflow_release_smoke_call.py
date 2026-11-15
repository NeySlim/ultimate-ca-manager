"""The release smoke runs the definition and the scripts of the tag it checks.

Started by `workflow_run`, GitHub would take both from the default branch; called from the build
of the tag, they come from that tag, and every checkout names it.
"""
import os
import subprocess

import pytest

from tests.workflow_support import evaluate, github_context, load, render, triggers

SMOKE = './.github/workflows/release-smoke.yml'
TAG_PUSH = github_context('push', 'refs/tags/v3.0-rc1')


def _strings(node):
    if isinstance(node, dict):
        for k, v in node.items():
            yield str(k)
            yield from _strings(v)
    elif isinstance(node, list):
        for v in node:
            yield from _strings(v)
    else:
        yield str(node)


def _caller(build):
    callers = [(name, job) for name, job in build['jobs'].items() if job.get('uses') == SMOKE]
    assert len(callers) == 1, callers
    return callers[0]


def test_the_smoke_is_called_with_a_version_and_never_follows_another_run():
    on = triggers(load('release-smoke.yml'))
    assert set(on) == {'workflow_call', 'workflow_dispatch'}, sorted(on)
    for trigger in ('workflow_call', 'workflow_dispatch'):
        assert on[trigger]['inputs']['version']['required'] is True, trigger
    assert not [s for s in _strings(load('release-smoke.yml')) if 'workflow_run' in s]


def test_the_build_calls_the_smoke_after_the_release_with_the_built_version():
    build = load('build-release.yml')
    name, job = _caller(build)
    needs = job['needs'] if isinstance(job['needs'], list) else [job['needs']]
    assert 'release' in needs and 'build-deb' in needs
    ctx = {'github': TAG_PUSH, 'needs': {'build-deb': {'outputs': {'version': '3.0-rc1'}}}}
    assert render(job['with']['version'], ctx) == '3.0-rc1'
    # The smoke reads published assets and pulls public images: nothing more than read access
    assert job['permissions'] == {'contents': 'read'}


@pytest.mark.parametrize('event, ref, runs', [
    ('push', 'refs/tags/v3.0-rc1', True),
    ('workflow_dispatch', 'refs/heads/sextant', False),
])
def test_the_call_happens_on_a_tag_build_only(event, ref, runs):
    _, job = _caller(load('build-release.yml'))
    assert bool(evaluate(job['if'], {'github': github_context(event, ref)})) is runs


def test_every_checkout_of_the_smoke_takes_the_tag_of_its_version():
    jobs = load('release-smoke.yml')['jobs']
    checkouts = [(name, step) for name, job in jobs.items() for step in job['steps']
                 if str(step.get('uses', '')).startswith('actions/checkout@')]
    assert len(checkouts) == len(jobs) == 4
    for name, step in checkouts:
        ref = step.get('with', {}).get('ref')
        assert ref, f'{name}: checkout without ref'
        assert render(ref, {'inputs': {'version': '3.0-rc1'}}) == 'refs/tags/v3.0-rc1', name


def test_no_smoke_job_is_gated_on_a_triggering_run():
    for name, job in load('release-smoke.yml')['jobs'].items():
        assert 'if' not in job, name


def _resolve_steps():
    for name, job in load('release-smoke.yml')['jobs'].items():
        steps = [s for s in job['steps'] if s.get('name') == 'Resolve version']
        assert len(steps) == 1, name
        yield name, steps[0]


@pytest.mark.parametrize('version, image, ok', [
    ('3.0-rc1', '', True),
    ('3.0', 'example/ucm', True),
    ('3.0;id', '', False),
    ('', '', False),
    ('3.0', 'Bad Image', False),
])
def test_the_version_step_validates_the_input(tmp_path, version, image, ok):
    for name, step in _resolve_steps():
        out = tmp_path / f'{name}.out'
        env = {k: render(v, {'inputs': {'version': version, 'image': image}, 'github': TAG_PUSH})
               for k, v in step.get('env', {}).items()}
        run = subprocess.run(['bash', '-e', '-c', step['run']], capture_output=True, text=True,
                             env={**env, 'GITHUB_OUTPUT': str(out), 'PATH': os.environ['PATH']})
        uses_image = 'INPUT_IMAGE' in step.get('env', {})
        expect_ok = ok or (not uses_image and version in ('3.0', '3.0-rc1'))
        assert (run.returncode == 0) is expect_ok, (name, run.stdout, run.stderr)
        if expect_ok:
            lines = out.read_text().splitlines()
            assert f'version={version}' in lines, name
            if uses_image:
                assert f"image={image or 'neyslim/ultimate-ca-manager'}" in lines, name
