"""Build & Release rehearsal: a `dry_run` dispatch plays the whole chain and publishes nothing.

Every step that publishes (registry push, image tag, Docker Hub page, GitHub release, chart push) or
holds a credential is found from the parsed YAML, and its job and step conditions are evaluated for
each kind of run: none may run in a rehearsal, all run on a tag.
"""
import os
import re
import shutil
import subprocess

import pytest
import yaml

from tests.workflow_support import ROOT, evaluate, github_context, load, render, triggers

GUARD = "startsWith(github.ref, 'refs/tags/') && !inputs.dry_run"
STATUS = re.compile(r'\b(success|failure|cancelled|always)\s*\(')

TAG_PUSH = (github_context('push', 'refs/tags/v3.0'), {})
REDO_ON_TAG = (github_context('workflow_dispatch', 'refs/tags/v3.0'), {'version': '3.0', 'dry_run': False})
REHEARSALS = {
    'branch': (github_context('workflow_dispatch', 'refs/heads/feature/x'), {'version': '3.0', 'dry_run': True}),
    'tag': (github_context('workflow_dispatch', 'refs/tags/v3.0-rc1'), {'version': '3.0-rc1', 'dry_run': True}),
}
PUBLISHING_ACTIONS = ('softprops/action-gh-release', 'peter-evans/dockerhub-description', 'docker/login-action')
PUBLISHING_COMMANDS = re.compile(
    r'\bgh\s+(release|api)\b|\bdocker\s+(push|login)\b|\bimagetools\s+create\b|\bhelm\s+(push|registry)\b'
    r'|\bgit\s+(push|tag)\b|\b(crane|skopeo|oras)\b|hub\.docker\.com')
# What the classifier must find: a step it missed would escape every guard test below
EXPECTED = {
    ('build-docker', 'Log in to GitHub Container Registry'), ('build-docker', 'Log in to Docker Hub'),
    ('build-docker', 'Push by digest'),
    ('build-docker-fips', 'Log in to GitHub Container Registry'), ('build-docker-fips', 'Log in to Docker Hub'),
    ('build-docker-fips', 'Push by digest'),
    ('docker-manifest', 'Log in to GitHub Container Registry'), ('docker-manifest', 'Log in to Docker Hub'),
    ('docker-manifest', 'Create manifest lists'), ('docker-manifest', 'Update Docker Hub description'),
    ('docker-fips-manifest', 'Log in to GitHub Container Registry'),
    ('docker-fips-manifest', 'Log in to Docker Hub'), ('docker-fips-manifest', 'Create manifest lists'),
    ('release', 'Delete existing release assets'), ('release', 'Create release'),
    ('release', 'Force-update release body'),
    ('publish-chart', 'Push the chart to the OCI registry'),
}


def _jobs():
    return load('build-release.yml')['jobs']


def _needs(job):
    needs = job.get('needs', [])
    return needs if isinstance(needs, list) else [needs]


def _strings(node):
    if isinstance(node, dict):
        for v in node.values():
            yield from _strings(v)
    elif isinstance(node, list):
        for v in node:
            yield from _strings(v)
    else:
        yield str(node)


def _pushes_remotely(step, github, inputs):
    """A build-push step whose rendered outputs push to a registry other than the job's own."""
    if not str(step.get('uses', '')).startswith('docker/build-push-action@'):
        return False
    with_ = step.get('with', {})
    ctx = {'github': github, 'inputs': inputs, 'env': {'REGISTRY': 'ghcr.io'},
           'steps': {'image': {'outputs': {'name': 'o/r'}}}, 'matrix': {'arch': 'amd64'},
           'needs': {'build-deb': {'outputs': {'version': '3.0'}}}}
    if str(with_.get('push', '')).lower() == 'true':
        return True
    outputs = render(with_.get('outputs', ''), ctx)
    if 'push=true' not in outputs.split(','):
        return False
    names = re.search(r'"?name=([^"]*?)"?(?:,push-by-digest|,name-canonical|,push=|$)', outputs).group(1)
    return any(not n.startswith('localhost:') for n in names.split(','))


SECRET = re.compile(r'\$\{\{[^}]*\bsecrets\.')
QUOTED = re.compile(r'"(?:[^"\\]|\\.)*"|\'[^\']*\'')


def _commands(run):
    """The script without its quoted strings: a message naming `git tag` runs nothing."""
    return QUOTED.sub('""', str(run or ''))


def _holds_secret(step):
    return any(SECRET.search(t) for t in _strings(step))


def _is_publishing(step):
    return (str(step.get('uses', '')).startswith(PUBLISHING_ACTIONS)
            or bool(PUBLISHING_COMMANDS.search(_commands(step.get('run'))))
            or _holds_secret(step)
            or _pushes_remotely(step, *TAG_PUSH))


def _publishing_steps():
    for name, job in _jobs().items():
        for step in job.get('steps', []):
            if _is_publishing(step):
                yield name, step


def _simulate(github, inputs):
    """Result of each job, as GitHub decides it: a job whose `if` names no status function also needs
    every dependency to have succeeded. Every job that runs succeeds."""
    jobs = _jobs()
    results, pending = {}, list(jobs)
    while pending:
        before = len(pending)
        for name in list(pending):
            needs = _needs(jobs[name])
            if any(n not in results for n in needs):
                continue
            pending.remove(name)
            ctx = {'github': github, 'inputs': inputs,
                   'needs': {n: {'result': results[n], 'outputs': {'prerelease': 'false'}} for n in needs}}
            cond = jobs[name].get('if')
            all_ok = all(results[n] == 'success' for n in needs)
            if cond is None or not STATUS.search(str(cond)):
                runs = all_ok and (cond is None or bool(evaluate(cond, ctx)))
            else:
                runs = bool(evaluate(cond, ctx, status='success' if all_ok else 'failure'))
            results[name] = 'success' if runs else 'skipped'
        assert len(pending) < before, pending
    return results


def _step_runs(job, step, github, inputs):
    results = _simulate(github, inputs)
    if results[job] != 'success':
        return False
    cond = step.get('if')
    return cond is None or bool(evaluate(cond, {'github': github, 'inputs': inputs, 'matrix': {'arch': 'amd64'}}))


def test_the_dispatch_is_a_rehearsal_unless_said_otherwise():
    dry = triggers(load('build-release.yml'))['workflow_dispatch']['inputs']['dry_run']
    assert dry['type'] == 'boolean' and dry['default'] is True


def test_the_publishing_steps_are_the_expected_ones():
    assert {(j, s['name']) for j, s in _publishing_steps()} == EXPECTED


@pytest.mark.parametrize('kind', REHEARSALS)
def test_no_publishing_step_runs_in_a_rehearsal(kind):
    github, inputs = REHEARSALS[kind]
    ran = [(j, s['name']) for j, s in _publishing_steps() if _step_runs(j, s, github, inputs)]
    assert not ran


@pytest.mark.parametrize('run', [TAG_PUSH, REDO_ON_TAG], ids=['tag-push', 'dispatch-on-tag'])
def test_every_publishing_step_runs_on_a_tag(run):
    skipped = [(j, s['name']) for j, s in _publishing_steps() if not _step_runs(j, s, *run)]
    assert not skipped


def test_every_publishing_step_carries_the_one_guard():
    jobs = _jobs()
    for job, step in _publishing_steps():
        conds = [str(c) for c in (jobs[job].get('if'), step.get('if')) if c]
        assert any(GUARD in c for c in conds), (job, step['name'], conds)


@pytest.mark.parametrize('kind', REHEARSALS)
def test_a_rehearsal_plays_every_job_but_the_publishing_ones(kind):
    results = _simulate(*REHEARSALS[kind])
    skipped = {n for n, r in results.items() if r != 'success'}
    assert skipped == {'publish-chart', 'smoke-failed'}


@pytest.mark.parametrize('kind', REHEARSALS)
def test_a_rehearsal_pushes_its_images_to_its_own_registry_only(kind):
    github, inputs = REHEARSALS[kind]
    for job in ('build-docker', 'build-docker-fips'):
        steps = [s for s in _jobs()[job]['steps'] if str(s.get('uses', '')).startswith('docker/build-push-action@')]
        running = [s for s in steps if _step_runs(job, s, github, inputs)]
        assert [s.get('id') for s in running if 'push=true' in str(s['with'].get('outputs', ''))] == ['rehearse']
        assert not any(_pushes_remotely(s, github, inputs) for s in running), job


def test_no_step_of_a_rehearsal_holds_a_secret():
    for kind, (github, inputs) in REHEARSALS.items():
        for name, job in _jobs().items():
            for step in job.get('steps', []):
                if _holds_secret(step):
                    assert not _step_runs(name, step, github, inputs), (kind, name, step.get('name'))


# ---- the mode check ------------------------------------------------------------------------------

def _mode(event, ref, inputs):
    step = next(s for s in _jobs()['validate-tag']['steps'] if s.get('name') == 'Check the run mode')
    env = {k: render(v, {'inputs': inputs}) for k, v in step['env'].items()}
    return subprocess.run(['bash', '-e', '-c', step['run']], capture_output=True, text=True,
                          env={**env, 'GITHUB_EVENT_NAME': event, 'GITHUB_REF': ref, 'PATH': os.environ['PATH']})


@pytest.mark.parametrize('event, ref, inputs, ok', [
    ('push', 'refs/tags/v3.0-rc1', {}, True),
    ('workflow_dispatch', 'refs/heads/feature/x', {'version': '3.0', 'dry_run': True}, True),
    ('workflow_dispatch', 'refs/tags/v3.0', {'version': '3.1', 'dry_run': True}, True),
    ('workflow_dispatch', 'refs/tags/v3.0', {'version': '3.0', 'dry_run': False}, True),
    # Only a tag publishes, and only its own version
    ('workflow_dispatch', 'refs/heads/feature/x', {'version': '3.0', 'dry_run': False}, False),
    ('workflow_dispatch', 'refs/tags/v3.0', {'version': '3.1', 'dry_run': False}, False),
    ('workflow_dispatch', 'refs/heads/v3.0', {'version': '3.0', 'dry_run': False}, False),
])
def test_the_mode_check(event, ref, inputs, ok):
    assert (_mode(event, ref, inputs).returncode == 0) is ok


def test_the_mode_check_runs_before_anything_else():
    jobs = _jobs()
    first = jobs['validate-tag']['steps'][0]
    assert first['name'] == 'Check the run mode' and 'if' not in first and 'if' not in jobs['validate-tag']
    for name, job in jobs.items():
        if name != 'validate-tag' and not _needs(job):
            pytest.fail(f'{name} does not wait for the mode check')


# ---- the rehearsal keeps what a release would publish --------------------------------------------

def test_the_rehearsal_keeps_the_release_in_the_run_artifacts():
    steps = {s.get('name'): s for s in _jobs()['release']['steps']}
    record, upload = steps['Record the rehearsed release'], steps['Upload the rehearsed release']
    github, inputs = REHEARSALS['branch']
    assert _step_runs('release', record, github, inputs) and _step_runs('release', upload, github, inputs)
    assert not _step_runs('release', upload, *TAG_PUSH)
    paths = upload['with']['path'].splitlines()
    assert '${{ runner.temp }}/rehearsal/notes.md' in paths and '${{ runner.temp }}/rehearsal/release.txt' in paths
    for name in ('notes.md', 'full-stop-migrations.json', 'sbom-index.json'):
        assert name in record['run'], name


def test_the_release_flags_a_prerelease_from_the_version():
    steps = {s.get('name'): s for s in _jobs()['release']['steps']}
    create = steps['Create release']
    assert render(create['with']['prerelease'], {'steps': {'kind': {'outputs': {'prerelease': 'true'}}}}) == 'true'
    run = render(steps['Decide prerelease']['run'], {})
    for version, expected in (('3.0-rc1', 'true'), ('3.0', 'false'), ('2.254.5', 'false')):
        out = subprocess.run(['bash', '-e', '-c', run.replace('$VERSION', version).replace('>> "$GITHUB_OUTPUT"', '')],
                             cwd=ROOT, capture_output=True, text=True)
        assert out.stdout.strip() == f'prerelease={expected}', out.stderr


@pytest.mark.parametrize('job', ['build-docker', 'build-docker-fips'])
def test_the_rehearsal_saves_the_amd64_image_for_its_smoke(job):
    prefix = 'fips' if 'fips' in job else 'std'
    steps = {s.get('name'): s for s in _jobs()[job]['steps']}
    upload = steps['Upload the image for the rehearsal smoke']
    github, inputs = REHEARSALS['branch']
    for arch, saved in (('amd64', True), ('arm64', False)):
        ctx = {'github': github, 'inputs': inputs, 'matrix': {'arch': arch}}
        assert bool(evaluate(upload['if'], ctx)) is saved
    assert not evaluate(upload['if'], {'github': TAG_PUSH[0], 'inputs': {}, 'matrix': {'arch': 'amd64'}})
    assert render(upload['with']['name'], {}) == f'{prefix}-image-amd64'


# ---- the chart -----------------------------------------------------------------------------------

def _chart_step():
    return next(s for s in _jobs()['build-chart']['steps'] if s.get('id') == 'chart')


@pytest.mark.skipif(shutil.which('helm') is None, reason='helm not installed')
@pytest.mark.parametrize('version, chart', [('3.0-rc1', '3.0.0-rc1'), ('3.0', '3.0.0'), ('3.1', '3.1.0')])
def test_the_chart_is_packaged_with_the_release_versions(tmp_path, version, chart):
    work = tmp_path / 'w'
    (work / 'scripts').mkdir(parents=True)
    (work / 'scripts' / 'ci').symlink_to(ROOT / 'scripts' / 'ci')
    shutil.copytree(ROOT / 'charts', work / 'charts')
    out = tmp_path / 'out'
    proc = subprocess.run(['bash', '-e', '-c', _chart_step()['run']], cwd=work, capture_output=True, text=True,
                          env={'VERSION': version, 'GITHUB_OUTPUT': str(out), 'PATH': os.environ['PATH'],
                               'HOME': str(tmp_path)})
    assert proc.returncode == 0, proc.stdout + proc.stderr
    prerelease = 'true' if '-' in version else 'false'
    assert out.read_text().splitlines() == [f'version={chart}', f'prerelease={prerelease}']
    tgz = work / 'chart-out' / f'ucm-{chart}.tgz'
    assert sorted(p.name for p in (work / 'chart-out').iterdir()) == [tgz.name, f'{tgz.name}.sha256']
    shown = yaml.safe_load(subprocess.run(['helm', 'show', 'chart', str(tgz)], capture_output=True, text=True,
                                          check=True, env={'PATH': os.environ['PATH'], 'HOME': str(tmp_path)}).stdout)
    assert (shown['version'], shown['appVersion']) == (chart, version)
    rendered = subprocess.run(['helm', 'template', 't', str(tgz), '--set', 'secrets.secretKey=k'],
                              capture_output=True, text=True, check=True,
                              env={'PATH': os.environ['PATH'], 'HOME': str(tmp_path)}).stdout
    images = {c['image'] for d in yaml.safe_load_all(rendered) if d and d['kind'] == 'Deployment'
              for c in d['spec']['template']['spec']['containers']}
    assert images == {f'neyslim/ultimate-ca-manager:{version}'}


def test_the_chart_is_published_for_a_stable_tag_only_after_the_release():
    job = _jobs()['publish-chart']
    assert 'release' in _needs(job) and 'build-chart' in _needs(job)
    for github, inputs, prerelease, runs in (
            (*TAG_PUSH, 'false', True), (*TAG_PUSH, 'true', False),
            (*REHEARSALS['branch'], 'false', False), (*REHEARSALS['tag'], 'false', False)):
        ctx = {'github': github, 'inputs': inputs, 'needs': {'build-chart': {'outputs': {'prerelease': prerelease}}}}
        assert bool(evaluate(job['if'], ctx)) is runs, (github['ref'], inputs, prerelease)
    push = next(s for s in job['steps'] if s.get('name') == 'Push the chart to the OCI registry')
    assert 'helm push "chart-out/$f" "oci://$REGISTRY/$owner/charts"' in push['run']
    assert load('build-release.yml')['env']['REGISTRY'] == 'ghcr.io'
