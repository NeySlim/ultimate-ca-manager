"""Release version chain: grammar, conversions, notes, branch guard, version files.

The workflow steps are the real `run:` blocks of the YAML, executed in bash; nothing compares text.
"""
import functools
import importlib.util
import json
import os
import pathlib
import re
import shutil
import subprocess
import sys
import time

import pytest
import yaml

from services import updates

ROOT = pathlib.Path(__file__).resolve().parents[2]
SCRIPT = ROOT / 'scripts' / 'ci' / 'release_version.py'
WORKFLOWS = ROOT / '.github' / 'workflows'
BASH = shutil.which('bash')


@pytest.fixture(autouse=True)
def _no_inherited_git_environment(monkeypatch):
    """A commit hook exports GIT_DIR and friends: scratch repositories must not inherit them."""
    for key in [k for k in os.environ if k.startswith('GIT_')]:
        monkeypatch.delenv(key)

# Major.Build for this line, X.Y.Z for the maintenance releases of the previous one
ACCEPTED = ['3.0', '3.1', '3.0-rc1', '2.254.2', '2.254.2-rc1']
REFUSED = ['3.0.0', '2.254-1', 'v3', 'v3.0', '', '3', '3.0-dev', '3.0.', '3.0-rc', '3.0-beta1', '03.0',
           '3.0.1.1', '3.0\n']

pytestmark = pytest.mark.skipif(BASH is None, reason='bash is required')


def _load():
    spec = importlib.util.spec_from_file_location('release_version', SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _cli(*args, stdin=None):
    return subprocess.run([sys.executable, str(SCRIPT), *args], input=stdin, capture_output=True, text=True)


@functools.lru_cache(maxsize=None)
def _workflow(name):
    return yaml.safe_load((WORKFLOWS / name).read_text())


def _step(workflow, job, name, index=0):
    data = _workflow(workflow)
    steps = [s for s in data['jobs'][job]['steps'] if s.get('name') == name]
    return steps[index]


def _run_step(step, cwd, env=None, subst=None):
    script = step['run']
    for old, new in (subst or {}).items():
        script = script.replace(old, new)
    full = {**os.environ, **{k: str(v) for k, v in (step.get('env') or {}).items() if '${{' not in str(v)},
            **(env or {})}
    return subprocess.run([BASH, '-e', '-c', script], cwd=cwd, env=full, capture_output=True, text=True)


# ---- 1. grammar, by every validation of the repository -------------------------------------------

@pytest.mark.parametrize('v', ACCEPTED)
def test_the_script_accepts_the_release_forms(v):
    assert _cli('validate', v).returncode == 0


@pytest.mark.parametrize('v', REFUSED)
def test_the_script_refuses_the_rest(v):
    assert _cli('validate', v).returncode == 1


def _validations(tmp_path, version):
    """Runs each real validation step of the repository with `version`; returns {label: returncode}."""
    out = {}
    out_file = tmp_path / 'gh_output'
    env = {'GITHUB_OUTPUT': str(out_file), 'INPUT_VERSION': version}
    out['build-deb'] = _run_step(_step('build-release.yml', 'build-deb', 'Extract version'), ROOT, env).returncode
    out['validate-tag'] = _run_step(_step('build-release.yml', 'validate-tag', 'Validate the tag grammar'), ROOT,
                                    {'GITHUB_REF': f'refs/tags/v{version}'}).returncode
    smoke = _workflow('release-smoke.yml')
    for job, body in smoke['jobs'].items():
        step = next(s for s in body['steps'] if s.get('name') == 'Resolve version')
        out[job] = _run_step(step, ROOT, {'GITHUB_OUTPUT': str(out_file), 'EVENT_NAME': 'workflow_dispatch',
                                          'INPUT_VERSION': version, 'INPUT_IMAGE': 'x/ucm'}).returncode
    assert len(out) == 6
    return out


@pytest.mark.parametrize('v', ACCEPTED)
def test_every_validation_accepts(tmp_path, v):
    assert set(_validations(tmp_path, v).values()) == {0}


@pytest.mark.parametrize('v', [r for r in REFUSED if r not in ('', '3.0\n')])
def test_every_validation_refuses(tmp_path, v):
    assert 0 not in _validations(tmp_path, v).values()


# ---- 2. conversions ----------------------------------------------------------------------------

@pytest.mark.parametrize('v,deb,tar,fv,npm', [
    ('3.0', '3.0', '3.0', '3.0', '3.0.0'),
    ('3.1', '3.1', '3.1', '3.1', '3.1.0'),
    ('3.0-rc1', '3.0~rc1', '3.0_rc1', '3.0.rc1', '3.0.0-rc1'),
    ('2.254.2', '2.254.2', '2.254.2', '2.254.2', '2.254.2'),
    ('2.254.2-rc1', '2.254.2~rc1', '2.254.2_rc1', '2.254.2.rc1', '2.254.2-rc1'),
])
def test_conversions(v, deb, tar, fv, npm):
    assert _cli('deb', v).stdout.strip() == deb
    assert _cli('rpm', v).stdout.strip() == deb
    assert _cli('tar', v).stdout.strip() == tar
    assert _cli('file', v).stdout.strip() == fv
    assert _cli('npm', v).stdout.strip() == npm
    assert re.fullmatch(r'\d+\.\d+\.\d+(-rc\d+)?', npm)


def _stamp(tmp_path, job, version):
    """The real `Stamp release version` step of *job*, run on copies of the two npm files."""
    work = tmp_path / job
    (work / 'frontend').mkdir(parents=True)
    (work / 'scripts').mkdir()
    (work / 'scripts' / 'ci').symlink_to(ROOT / 'scripts' / 'ci')
    for f in ('package.json', 'package-lock.json'):
        shutil.copy(ROOT / 'frontend' / f, work / 'frontend' / f)
    step = _step('build-release.yml', job, 'Stamp release version')
    r = _run_step(step, work, subst={'${{ steps.version.outputs.version }}': version,
                                     '${{ needs.build-deb.outputs.version }}': version})
    assert r.returncode == 0, r.stderr
    pkg = json.loads((work / 'frontend' / 'package.json').read_text())
    lock = json.loads((work / 'frontend' / 'package-lock.json').read_text())
    return (work / 'VERSION').read_text(), pkg['version'], lock['version'], lock['packages']['']['version']


@pytest.mark.skipif(shutil.which('node') is None, reason='node is required')
@pytest.mark.parametrize('job', ['build-deb', 'build-rpm', 'build-docker', 'build-docker-fips'])
@pytest.mark.parametrize('v,npm', [('3.0', '3.0.0'), ('3.0-rc1', '3.0.0-rc1'), ('2.254.2', '2.254.2')])
def test_every_stamp_step_writes_the_npm_form(tmp_path, job, v, npm):
    assert _stamp(tmp_path, job, v) == (v, npm, npm, npm)


@pytest.mark.skipif(shutil.which('dpkg') is None, reason='dpkg is required')
def test_dpkg_ranks_the_converted_versions():
    order = [_load().deb_version(v) for v in ('2.254.2-rc1', '2.254.2', '3.0-rc1', '3.0', '3.1')]
    for lo, hi in zip(order, order[1:]):
        assert subprocess.run(['dpkg', '--compare-versions', lo, 'lt', hi]).returncode == 0, (lo, hi)


# ---- 3. release notes --------------------------------------------------------------------------

CHANGELOG = """# Changelog

## [Unreleased]

### Added
- Next thing.

## [3.0] - 2026-12-20

### Added
- Phare thing.

## [2.254.1] - 2026-11-14
- Maintenance fix.

## [2.254] - 2026-11-13
- Last 2.x.
"""


def _notes(tmp_path, version, text=CHANGELOG):
    (tmp_path / 'CHANGELOG.md').write_text(text)
    return _cli('notes', version, str(tmp_path / 'CHANGELOG.md'))


def test_a_rc_takes_the_unreleased_section(tmp_path):
    r = _notes(tmp_path, '3.1-rc1')
    assert r.returncode == 0, r.stderr
    assert 'Next thing.' in r.stdout and 'Phare thing' not in r.stdout and 'Maintenance' not in r.stdout


def test_a_stable_takes_its_own_section(tmp_path):
    r = _notes(tmp_path, '3.0')
    assert r.returncode == 0, r.stderr
    assert 'Phare thing.' in r.stdout and 'Next thing' not in r.stdout and 'Maintenance' not in r.stdout


def test_a_three_segment_section_is_extracted_alone(tmp_path):
    r = _notes(tmp_path, '2.254.1')
    assert 'Maintenance fix.' in r.stdout and 'Last 2.x' not in r.stdout
    r = _notes(tmp_path, '2.254')
    assert 'Last 2.x.' in r.stdout and 'Maintenance' not in r.stdout


@pytest.mark.parametrize('version,text', [
    ('3.1', CHANGELOG),
    ('3.1-rc1', CHANGELOG.replace('## [Unreleased]', '## [Later]')),
    ('3.1-rc1', CHANGELOG.replace('### Added\n- Next thing.\n', '', 1)),
])
def test_a_missing_or_empty_section_fails_explicitly(tmp_path, version, text):
    r = _notes(tmp_path, version, text)
    assert r.returncode == 1 and r.stdout == ''
    assert 'CHANGELOG' in r.stderr


def test_the_fallback_heading_does_not_bite_on_a_longer_version():
    rv = _load()
    text = '## 2.254.1\n- three\n\n## 2.254\n- two\n'
    assert 'two' in rv.changelog_section('2.254', text) and 'three' not in rv.changelog_section('2.254', text)
    assert 'three' in rv.changelog_section('2.254.1', text) and 'two' not in rv.changelog_section('2.254.1', text)


@pytest.mark.parametrize('version,expected', [
    ('3.2', ['3.1', '3.0']),
    ('3.1-rc1', ['3.0']),
    ('3.0', []),
    ('3.0-rc2', []),
    ('2.254.2', ['2.254.1', '2.254']),
])
def test_the_history_stays_on_the_line_of_the_version(version, expected):
    text = ('## [Unreleased]\n- u\n\n## [3.1] - d\n- a\n\n## [3.0] - d\n- b\n\n'
            '## [2.254.1] - d\n- c\n\n## [2.254] - d\n- e\n\n## [2.253] - d\n- f\n')
    heads = re.findall(r'^## \[([^\]]+)\]', _load().changelog_history(version, text), re.M)
    assert heads == [h for h in expected]


def _notes_step(tmp_path, v, changelog):
    work = tmp_path / 'w'
    (work / 'scripts').mkdir(parents=True)
    (work / 'scripts' / 'ci').symlink_to(ROOT / 'scripts' / 'ci')
    (work / 'CHANGELOG.md').write_text(changelog)
    step = _step('build-release.yml', 'release', 'Generate release notes')
    result = _run_step(step, work, subst={'${{ needs.build-deb.outputs.version }}': v,
                                          '${{ github.repository }}': 'o/r'})
    return result, work / 'notes.md'


@pytest.mark.parametrize('v', ACCEPTED)
def test_the_release_notes_step_names_the_published_files(tmp_path, v):
    """The real notes step, run on a scratch tree: install links name the files the build publishes."""
    changelog = (f'## [Unreleased]\n- Marker.\n\n' if '-rc' in v else f'## [{v}] - 2026-11-30\n- Marker.\n\n')
    result, notes = _notes_step(tmp_path, v, changelog + '## [2.200] - 2026-01-01\n- Old.\n')
    assert result.returncode == 0, result.stderr
    text = notes.read_text()
    for name in _load().asset_names(v).values():
        assert name in text, name
    assert f'releases/download/v{v}/' in text and 'Marker.' in text
    # 2.200 belongs to another line than every accepted version but 2.254.N
    assert ('Old.' in text) is v.startswith('2.')


@pytest.mark.parametrize('v,changelog', [('3.0', '## [Unreleased]\n- x\n'), ('3.0-rc1', '## [2.254] - d\n- x\n')])
def test_the_release_notes_step_fails_without_its_section(tmp_path, v, changelog):
    result, notes = _notes_step(tmp_path, v, changelog)
    assert result.returncode != 0
    assert 'CHANGELOG' in result.stdout + result.stderr


# ---- 3b. the branch a tag must sit on -------------------------------------------------------------

def _tagged_checkout(tmp_path, branches, tag_on):
    """A checkout at a tagged commit, as the validate-tag job has it: one commit per branch of
    *branches* on the origin, HEAD on the tip of *tag_on* (or on a commit no branch holds)."""
    bare, work = tmp_path / 'origin.git', tmp_path / 'work'
    git = ['git', '-c', 'user.name=t', '-c', 'user.email=t@t']
    subprocess.run(['git', 'init', '-q', '--bare', str(bare)], check=True)
    subprocess.run(['git', 'init', '-q', str(work)], check=True)
    subprocess.run(['git', 'remote', 'add', 'origin', str(bare)], cwd=work, check=True)
    for branch in branches:
        subprocess.run(['git', 'checkout', '-q', '--orphan', branch], cwd=work, check=True)
        subprocess.run([*git, 'commit', '-q', '--allow-empty', '-m', branch], cwd=work, check=True)
        subprocess.run(['git', 'push', '-q', 'origin', branch], cwd=work, check=True)
    if tag_on in branches:
        subprocess.run(['git', 'checkout', '-q', '--detach', tag_on], cwd=work, check=True)
    else:
        subprocess.run(['git', 'checkout', '-q', '--orphan', 'elsewhere'], cwd=work, check=True)
        subprocess.run([*git, 'commit', '-q', '--allow-empty', '-m', 'elsewhere'], cwd=work, check=True)
    return work


def _guard(work, version):
    step = _step('build-release.yml', 'validate-tag', 'Ensure tag points to the correct release branch')
    return _run_step(step, work, {'GITHUB_REF': f'refs/tags/v{version}'})


@pytest.mark.parametrize('branches,tag_on,version,accepted', [
    (['main', 'test'], 'main', '3.0', True),
    (['main', 'test'], 'test', '3.0-rc1', True),
    (['main', 'test'], 'test', '3.0', False),
    (['main', 'test'], 'main', '3.0-rc1', False),
    (['main', 'test'], 'nowhere', '3.0', False),
    # A v2.x tag is built by the workflow of the v2.x branch, which carries its own guard
    (['main', 'test', 'v2.x'], 'v2.x', '2.254.2', False),
    (['main', 'test', 'v2.x'], 'v2.x', '2.254.2-rc1', False),
])
def test_a_tag_sits_on_its_release_branch(tmp_path, branches, tag_on, version, accepted):
    result = _guard(_tagged_checkout(tmp_path, branches, tag_on), version)
    assert (result.returncode == 0) is accepted, result.stdout + result.stderr


@pytest.mark.parametrize('name,version', [('main', '3.0'), ('test', '3.0-rc1')])
def test_a_tag_named_like_a_release_branch_opens_nothing(tmp_path, name, version):
    """A tag `main` or `test` pushed on any commit is not the branch of that name."""
    work = _tagged_checkout(tmp_path, ['main', 'test'], 'nowhere')
    subprocess.run(['git', 'tag', name], cwd=work, check=True)
    subprocess.run(['git', 'push', '-q', 'origin', f'refs/tags/{name}'], cwd=work, check=True)
    result = _guard(work, version)
    assert result.returncode != 0, result.stdout + result.stderr
    assert 'Refusing to build release from an unexpected commit' in result.stdout


@pytest.mark.parametrize('ref', ['refs/heads/foo/refs/heads/main', 'refs/tags/refs/heads/main'])
def test_a_ref_that_only_ends_like_the_branch_opens_nothing(tmp_path, ref):
    work = _tagged_checkout(tmp_path, ['test'], 'nowhere')
    subprocess.run(['git', 'push', '-q', 'origin', f'HEAD:{ref}'], cwd=work, check=True)
    result = _guard(work, '3.0')
    assert result.returncode != 0, result.stdout + result.stderr


def test_an_unreachable_remote_never_validates_a_tag(tmp_path):
    work = _tagged_checkout(tmp_path, ['main', 'test'], 'main')
    subprocess.run(['git', 'remote', 'set-url', 'origin', str(tmp_path / 'missing.git')], cwd=work, check=True)
    assert _guard(work, '3.0').returncode != 0


# ---- 4. an installed instance ------------------------------------------------------------------

def _release(tag):
    fv = _load().file_version(tag)
    return {'tag_name': f'v{tag}', 'draft': False, 'prerelease': '-rc' in tag, 'body': '',
            'assets': [{'name': f'ucm_{fv}_all.deb', 'browser_download_url': f'http://x/ucm_{fv}_all.deb'}]}


@pytest.fixture
def instance(monkeypatch):
    def setup(current, releases):
        monkeypatch.setattr(updates, 'get_current_version', lambda: current)
        monkeypatch.setitem(updates._releases_cache, 'data', releases)
        monkeypatch.setitem(updates._releases_cache, 'ts', time.time())
        monkeypatch.setattr(updates.os.path, 'exists', lambda p: p == '/usr/bin/dpkg')
        monkeypatch.delenv('UCM_DOCKER', raising=False)
    return setup


def test_a_later_maintenance_release_of_the_previous_line_is_not_offered(instance):
    instance('3.0', [_release('3.0'), _release('2.254.2'), _release('2.254.3-rc1')])
    assert updates.check_for_updates(channel='rc')['update_available'] is False


def test_the_last_previous_line_release_is_offered_the_new_line(instance):
    instance('2.254.2', [_release('2.254.2'), _release('3.0')])
    result = updates.check_for_updates(channel='stable')
    assert (result['update_available'], result['latest_version']) == (True, '3.0')


# ---- 5. version files and the bump script ------------------------------------------------------

@pytest.mark.parametrize('version,npm', [
    ('3.0-dev', '3.0.0-dev'), ('3.1-dev', '3.1.0-dev'), ('2.254.2-dev', '2.254.2-dev'),
    ('3.0-rc1', '3.0.0-rc1'), ('3.0', '3.0.0'), ('2.254.2', '2.254.2'),
])
def test_npm_form_of_each_branch_version(version, npm):
    assert _cli('npm', version).stdout.strip() == npm


@pytest.mark.parametrize('version', ['3.0.0-dev', '3.0-dev-dev', '3.0-rc1-dev', '3.0-1', 'v3.0-dev', ''])
def test_npm_form_refuses_another_grammar(version):
    assert _cli('npm', version).returncode == 1


def test_a_dev_version_is_never_a_tag():
    assert _cli('validate', '3.0-dev').returncode == 1
    assert _cli('deb', '3.0-dev').returncode == 1


def test_version_files_agree():
    npm = _cli('npm', (ROOT / 'VERSION').read_text().strip()).stdout.strip()
    pkg = json.loads((ROOT / 'frontend' / 'package.json').read_text())
    lock = json.loads((ROOT / 'frontend' / 'package-lock.json').read_text())
    assert npm and pkg['version'] == lock['version'] == lock['packages']['']['version'] == npm


def _scratch_tree(tmp_path):
    root = tmp_path / 'tree'
    for rel in ('scripts', 'frontend', 'charts/ucm'):
        (root / rel).mkdir(parents=True)
    shutil.copy(ROOT / 'scripts' / 'bump-version.sh', root / 'scripts')
    (root / 'scripts' / 'ci').symlink_to(ROOT / 'scripts' / 'ci')
    shutil.copy(ROOT / 'frontend' / 'package.json', root / 'frontend')
    shutil.copy(ROOT / 'frontend' / 'package-lock.json', root / 'frontend')
    shutil.copy(ROOT / 'charts' / 'ucm' / 'Chart.yaml', root / 'charts' / 'ucm')
    return root


def _chart(root):
    return yaml.safe_load((root / 'charts/ucm/Chart.yaml').read_text())


@pytest.mark.skipif(shutil.which('node') is None, reason='node is required')
@pytest.mark.parametrize('v,npm,chart_app', [
    ('3.0', '3.0.0', '3.0'), ('3.1', '3.1.0', '3.1'), ('3.0-rc1', '3.0.0-rc1', '3.0-rc1'),
    ('2.254.2', '2.254.2', '2.254.2'), ('2.254.2-rc1', '2.254.2-rc1', '2.254.2-rc1'),
    # No image is published for a -dev version: appVersion is left as it is
    ('3.1-dev', '3.1.0-dev', None), ('2.254.3-dev', '2.254.3-dev', None),
])
def test_bump_version_updates_every_file(tmp_path, v, npm, chart_app):
    root = _scratch_tree(tmp_path)
    before = _chart(root)
    r = subprocess.run([BASH, str(root / 'scripts' / 'bump-version.sh'), v], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    lock = json.loads((root / 'frontend' / 'package-lock.json').read_text())
    assert (root / 'VERSION').read_text().strip() == v
    assert json.loads((root / 'frontend' / 'package.json').read_text())['version'] == npm
    assert lock['version'] == lock['packages']['']['version'] == npm
    after = _chart(root)
    assert after['appVersion'] == (chart_app or before['appVersion'])
    # The chart version follows chart changes, not the application
    assert after['version'] == before['version']


@pytest.mark.parametrize('v', ['2.254-1', '3.0.0', 'v3', ''])
def test_bump_version_refuses_a_version_the_release_grammar_refuses(tmp_path, v):
    root = _scratch_tree(tmp_path)
    pkg = (root / 'frontend' / 'package.json').read_text()
    r = subprocess.run([BASH, str(root / 'scripts' / 'bump-version.sh'), v], capture_output=True, text=True)
    assert r.returncode != 0
    assert not (root / 'VERSION').exists()
    assert (root / 'frontend' / 'package.json').read_text() == pkg


# ---- 6. smoke_release compares the reported version exactly -------------------------------------

def _smoke_module():
    spec = importlib.util.spec_from_file_location('smoke_release', ROOT / 'scripts' / 'smoke_release.py')
    mod = importlib.util.module_from_spec(spec)
    sys.modules['smoke_release'] = mod
    spec.loader.exec_module(mod)
    return mod


def _health_run(monkeypatch, reported, expected):
    mod = _smoke_module()
    body = json.dumps({'status': 'ok', 'version': reported}).encode()
    monkeypatch.setattr(mod, '_request', lambda *a, **k: (200, {}, body))
    # The run stops at the login step once the version check has passed.
    with pytest.raises(AssertionError) as exc:
        mod.smoke_one(mod.Target('t', 'https://x'), expected, 'u', 'p', allow_rc=True)
    return str(exc.value)


@pytest.mark.parametrize('reported,expected', [('3.10', '3.1'), ('3.1', '3.10'), ('3.0-rc1', '3.0')])
def test_smoke_release_refuses_a_version_that_only_starts_the_same(monkeypatch, reported, expected):
    assert 'version mismatch' in _health_run(monkeypatch, reported, expected)


def test_smoke_release_accepts_the_exact_version(monkeypatch):
    assert 'version mismatch' not in _health_run(monkeypatch, '3.1', '3.1')


# ---- 7. the manual publisher takes the same section ---------------------------------------------

def _publish(tmp_path, version, changelog, *flags):
    """Notes the script hands to `gh release edit` (it only edits a release the workflow created)."""
    bare, work = tmp_path / 'origin.git', tmp_path / 'work'
    # Under the pre-commit hook GIT_DIR points at the real repository: never hand it down
    clean = {k: v for k, v in os.environ.items() if not k.startswith('GIT_')}
    git = ['git', '-c', 'user.name=t', '-c', 'user.email=t@t']
    subprocess.run(['git', 'init', '-q', '--bare', str(bare)], check=True, env=clean)
    subprocess.run(['git', 'init', '-q', str(work)], check=True, env=clean)
    subprocess.run([*git, 'commit', '-q', '--allow-empty', '-m', 'x'], cwd=work, check=True, env=clean)
    subprocess.run(['git', 'remote', 'add', 'origin', str(bare)], cwd=work, check=True, env=clean)
    subprocess.run(['git', 'tag', f'v{version}'], cwd=work, check=True, env=clean)
    subprocess.run(['git', 'push', '-q', 'origin', '--tags'], cwd=work, check=True, env=clean)
    (work / 'scripts').mkdir()
    (work / 'scripts' / 'ci').symlink_to(ROOT / 'scripts' / 'ci')
    shutil.copy(ROOT / 'scripts' / 'release_publish.sh', work / 'scripts')
    (work / 'CHANGELOG.md').write_text(changelog)
    fake = tmp_path / 'bin'
    fake.mkdir()
    log = tmp_path / 'gh.args'
    (fake / 'gh').write_text(
        '#!/bin/sh\n'
        'if [ "$1 $2" = "release edit" ]; then\n'
        f'  for a in "$@"; do echo "$a"; done > "{log}"\n'
        f'  while [ $# -gt 0 ]; do [ "$1" = "--notes-file" ] && cp "$2" "{log}.notes"; shift; done\n'
        'fi\n')
    (fake / 'gh').chmod(0o755)
    env = {**clean, 'PATH': f'{fake}:{os.environ["PATH"]}'}
    result = subprocess.run([BASH, 'scripts/release_publish.sh', version, '--edit', *flags], cwd=work, env=env,
                            capture_output=True, text=True)
    notes = pathlib.Path(str(log) + '.notes')
    return result, (notes.read_text() if notes.exists() else None)


PUBLISH_CHANGELOG = ('## [Unreleased]\n- Coming next.\n\n## [3x0]\n- Dots are literal.\n\n'
                     '## [3.0] - 2026-12-01\n- Fixed a.b thing.\n\n## [2.254] - 2026-11-13\n- Older entry.\n')


@pytest.mark.parametrize('version,marker', [('3.0', 'Fixed a.b thing.'), ('3.1-rc1', 'Coming next.')])
def test_release_publish_takes_the_section_of_the_workflow(tmp_path, version, marker):
    result, notes = _publish(tmp_path, version, PUBLISH_CHANGELOG)
    assert result.returncode == 0, result.stderr
    assert marker in notes
    for other in ('Fixed a.b thing.', 'Coming next.', 'Older entry', 'Dots are literal'):
        assert other == marker or other not in notes


def test_release_publish_refuses_a_missing_section(tmp_path):
    result, notes = _publish(tmp_path, '3.2', PUBLISH_CHANGELOG)
    assert result.returncode != 0 and notes is None


# ---- 8. the release notes prescribe the FIPS stream of the installation guide ----------------------

def _pro_streams(text):
    return set(re.findall(r'sudo pro enable ([a-z-]+)', text))


def test_the_release_notes_enable_the_ubuntu_stream_of_the_guide(tmp_path):
    result, notes = _notes_step(tmp_path, '3.0', '## [3.0] - 2026-12-01\n- Marker.\n')
    assert result.returncode == 0, result.stderr
    guide = (ROOT / 'docs' / 'installation' / 'README.md').read_text()
    # The `fips` stream ships the binaries certified under CMVP #5115; `fips-updates` does not
    assert _pro_streams(notes.read_text()) == _pro_streams(guide) == {'fips'}
