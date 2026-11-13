"""Release version chain: grammar, conversions, notes, `latest`, installed-instance updates.

The workflow steps are the real `run:` blocks of the YAML, executed in bash; nothing compares text.
"""
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
# A commit hook exports GIT_DIR and friends: scratch repositories must not inherit them.
for _k in [k for k in os.environ if k.startswith('GIT_')]:
    os.environ.pop(_k)

ACCEPTED = ['2.254', '2.254-rc1', '2.254.1', '2.254.1-rc2']
REFUSED = ['2.254-1', '2.254.1.1', 'v2.254.1', '2.254.1-dev', '2.254.', '2.254.1\n', '2.254.0', '', '2']

pytestmark = pytest.mark.skipif(BASH is None, reason='bash is required')


def _load():
    spec = importlib.util.spec_from_file_location('release_version', SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


rv = _load()


def _cli(*args, stdin=None):
    return subprocess.run(['python3', str(SCRIPT), *args], input=stdin, capture_output=True, text=True)


def _step(workflow, job, name, index=0):
    data = yaml.safe_load((WORKFLOWS / workflow).read_text())
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
def test_the_script_accepts_the_four_forms(v):
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
    smoke = yaml.safe_load((WORKFLOWS / 'release-smoke.yml').read_text())
    for job, body in smoke['jobs'].items():
        step = next(s for s in body['steps'] if s.get('name') == 'Resolve version')
        out[job] = _run_step(step, ROOT, {'GITHUB_OUTPUT': str(out_file), 'EVENT_NAME': 'workflow_dispatch',
                                          'INPUT_VERSION': version, 'INPUT_IMAGE': 'x/ucm'}).returncode
    assert len(out) == 5
    return out


@pytest.mark.parametrize('v', ACCEPTED)
def test_every_validation_accepts(tmp_path, v):
    assert set(_validations(tmp_path, v).values()) == {0}


@pytest.mark.parametrize('v', [r for r in REFUSED if r not in ('', '2.254.1\n')])
def test_every_validation_refuses(tmp_path, v):
    assert 0 not in _validations(tmp_path, v).values()


# ---- 2. conversions ----------------------------------------------------------------------------

@pytest.mark.parametrize('v,deb,tar,fv,npm', [
    ('2.254', '2.254', '2.254', '2.254', '2.254.0'),
    ('2.254-rc1', '2.254~rc1', '2.254_rc1', '2.254.rc1', '2.254.0-rc1'),
    ('2.254.1', '2.254.1', '2.254.1', '2.254.1', '2.254.1'),
    ('2.254.1-rc2', '2.254.1~rc2', '2.254.1_rc2', '2.254.1.rc2', '2.254.1-rc2'),
])
def test_conversions(v, deb, tar, fv, npm):
    assert _cli('deb', v).stdout.strip() == deb
    assert _cli('rpm', v).stdout.strip() == deb
    assert _cli('tar', v).stdout.strip() == tar
    assert _cli('file', v).stdout.strip() == fv
    assert _cli('npm', v).stdout.strip() == npm
    assert re.fullmatch(r'\d+\.\d+\.\d+(-rc\d+)?', npm)


@pytest.mark.skipif(shutil.which('dpkg') is None, reason='dpkg is required')
def test_dpkg_ranks_the_converted_versions():
    order = [rv.deb_version(v) for v in ('2.254', '2.254.1-rc1', '2.254.1', '2.254.2')]
    for lo, hi in zip(order, order[1:]):
        assert subprocess.run(['dpkg', '--compare-versions', lo, 'lt', hi]).returncode == 0, (lo, hi)


@pytest.mark.skipif(shutil.which('rpm') is None, reason='rpm is required')
def test_rpm_ranks_the_converted_versions():
    def vercmp(a, b):
        out = subprocess.run(['rpm', '--eval', f'%{{lua: print(rpm.vercmp("{a}","{b}"))}}'],
                             capture_output=True, text=True).stdout.strip()
        return int(out)
    order = [rv.rpm_version(v) for v in ('2.254', '2.254.1-rc1', '2.254.1', '2.254.2')]
    for lo, hi in zip(order, order[1:]):
        assert vercmp(lo, hi) == -1, (lo, hi)
    # A RC sorts before its own stable, as 2.254~rc1 does against 2.254 today.
    assert vercmp(rv.rpm_version('2.254-rc1'), rv.rpm_version('2.254')) == -1


# ---- 3. release notes --------------------------------------------------------------------------

CHANGELOG = """# Changelog

## [Unreleased]

## [2.254.1] - 2026-11-20

### Security
- Fixed the thing.

## [2.254] - 2026-11-13

### Added
- Something else.

## [2.253] - 2026-11-11
- Older.
"""


def test_a_three_segment_section_is_extracted_alone(tmp_path):
    (tmp_path / 'CHANGELOG.md').write_text(CHANGELOG)
    out = _cli('notes', '2.254.1', str(tmp_path / 'CHANGELOG.md')).stdout
    assert 'Fixed the thing.' in out and 'Something else' not in out and '2.254' not in out
    out = _cli('notes', '2.254', str(tmp_path / 'CHANGELOG.md')).stdout
    assert 'Something else.' in out and 'Fixed the thing.' not in out and 'Older' not in out


def test_the_fallback_heading_does_not_bite_on_a_longer_version():
    text = '## 2.254.1\n- three\n\n## 2.254\n- two\n'
    assert 'two' in rv.changelog_section('2.254', text) and 'three' not in rv.changelog_section('2.254', text)
    assert 'three' in rv.changelog_section('2.254.1', text) and 'two' not in rv.changelog_section('2.254.1', text)


@pytest.mark.parametrize('v', ACCEPTED)
def test_the_release_notes_step_names_the_published_files(tmp_path, v):
    """The real notes step, run on a scratch tree: install links name the files the build publishes."""
    work = tmp_path / 'w'
    (work / 'scripts').mkdir(parents=True)
    (work / 'scripts' / 'ci').symlink_to(ROOT / 'scripts' / 'ci')
    (work / 'CHANGELOG.md').write_text(f'## [{v}] - 2026-11-30\n- Marker.\n\n## [2.200] - 2026-01-01\n- Old.\n')
    step = _step('build-release.yml', 'release', 'Generate release notes')
    result = _run_step(step, work, subst={'${{ needs.build-deb.outputs.version }}': v,
                                          '${{ github.repository }}': 'o/r'})
    assert result.returncode == 0, result.stderr
    notes = (work / 'notes.md').read_text()
    for name in rv.asset_names(v).values():
        assert name in notes, name
    assert f'releases/download/v{v}/' in notes and 'Marker.' in notes


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


@pytest.mark.parametrize('branches,tag_on,version,accepted', [
    (['main', 'test'], 'main', '2.254.1', True),
    (['main', 'test'], 'test', '2.254.1-rc1', True),
    (['main', 'test'], 'test', '2.254.1', False),
    (['main', 'test', 'v2.x'], 'v2.x', '2.254.2', True),
    (['main', 'test', 'v2.x'], 'v2.x', '2.254.2-rc1', True),
    (['main', 'test', 'v2.x'], 'main', '2.254.2', True),
    (['main', 'test', 'v2.x'], 'v2.x', '2.255', False),
    (['main', 'test', 'v2.x'], 'v2.x', '1.0.1', False),
    (['main', 'test', 'v1.x'], 'v1.x', '1.0.1', True),
    (['main', 'test', 'backport/v2.x'], 'main', '2.254.1', True),
    (['main', 'test', 'v2.x'], 'nowhere', '2.254.2', False),
    (['main', 'test'], 'nowhere', '2.254.2', False),
])
def test_a_tag_sits_on_its_release_branch_or_its_maintenance_branch(tmp_path, branches, tag_on, version, accepted):
    work = _tagged_checkout(tmp_path, branches, tag_on)
    step = _step('build-release.yml', 'validate-tag', 'Ensure tag points to the correct release branch')
    result = _run_step(step, work, {'GITHUB_REF': f'refs/tags/v{version}'})
    assert (result.returncode == 0) is accepted, result.stdout + result.stderr


@pytest.mark.parametrize('name,version', [('v2.x', '2.254.2'), ('main', '2.254.2'), ('main', '2.255'), ('test', '2.254.2-rc1')])
def test_a_tag_named_like_a_release_branch_opens_nothing(tmp_path, name, version):
    """A tag `v2.x` or `main` pushed on any commit is not the branch of that name."""
    work = _tagged_checkout(tmp_path, ['main', 'test', 'v2.x'], 'nowhere')
    subprocess.run(['git', 'tag', name], cwd=work, check=True)
    subprocess.run(['git', 'push', '-q', 'origin', f'refs/tags/{name}'], cwd=work, check=True)
    step = _step('build-release.yml', 'validate-tag', 'Ensure tag points to the correct release branch')
    result = _run_step(step, work, {'GITHUB_REF': f'refs/tags/v{version}'})
    assert result.returncode != 0, result.stdout + result.stderr
    assert 'Refusing to build release from an unexpected commit' in result.stdout


# ---- 4. latest ---------------------------------------------------------------------------------

@pytest.mark.parametrize('published,tag,expected', [
    (['v2.253', 'v2.254'], '2.254.1', 'true'),
    (['v2.254', 'v9.0'], '2.254.2', 'false'),
    (['v2.254', 'v2.254.1-rc1'], '2.254.1-rc1', 'false'),
    (['v9.0'], '9.1', 'true'),
    (['v2.254', 'v2.254.1', 'v2.254.2-rc1', 'v9.0-rc1'], '2.254.1', 'true'),
    (['v2.254.1'], '2.254', 'false'),
    (['v2.254', 'v2.254.1'], '2.254.1', 'true'),
    (['v2.9', 'v2.10'], '2.9', 'false'),
])
def test_latest_table(published, tag, expected):
    assert _cli('latest', tag, stdin='\n'.join(published)).stdout.strip() == expected


def _origin_with_tags(tmp_path, tags):
    bare = tmp_path / 'origin.git'
    work = tmp_path / 'work'
    git = ['git', '-c', 'user.name=t', '-c', 'user.email=t@t']
    subprocess.run(['git', 'init', '-q', '--bare', str(bare)], check=True)
    subprocess.run(['git', 'init', '-q', str(work)], check=True)
    subprocess.run([*git, 'commit', '-q', '--allow-empty', '-m', 'x'], cwd=work, check=True)
    subprocess.run(['git', 'remote', 'add', 'origin', str(bare)], cwd=work, check=True)
    for t in tags:
        subprocess.run(['git', 'tag', t], cwd=work, check=True)
    subprocess.run(['git', 'push', '-q', 'origin', '--tags'], cwd=work, check=True)
    (work / 'scripts').mkdir()
    (work / 'scripts' / 'ci').symlink_to(ROOT / 'scripts' / 'ci')
    return work


@pytest.mark.parametrize('job', ['docker-manifest', 'docker-fips-manifest', 'release'])
@pytest.mark.parametrize('tags,version,expected', [
    (['v2.253', 'v2.254', 'v2.254.1'], '2.254.1', 'true'),
    (['v2.254', 'v9.0', 'v2.254.2'], '2.254.2', 'false'),
    (['v2.254', 'v2.254.1-rc1'], '2.254.1-rc1', 'false'),
])
def test_the_latest_step_reads_the_remote_tags(tmp_path, job, tags, version, expected):
    work = _origin_with_tags(tmp_path, tags)
    out = tmp_path / 'gh_output'
    step = _step('build-release.yml', job, 'Decide latest')
    result = _run_step(step, work, {'GITHUB_OUTPUT': str(out), 'VERSION': version, 'GITHUB_REF': f'refs/tags/v{version}'})
    assert result.returncode == 0, result.stderr
    assert out.read_text().strip() == f'latest={expected}'


@pytest.mark.parametrize('job', ['docker-manifest', 'docker-fips-manifest', 'release'])
def test_a_branch_run_never_takes_latest(tmp_path, job):
    work = _origin_with_tags(tmp_path, ['v2.253'])
    out = tmp_path / 'gh_output'
    step = _step('build-release.yml', job, 'Decide latest')
    result = _run_step(step, work, {'GITHUB_OUTPUT': str(out), 'VERSION': '2.254', 'GITHUB_REF': 'refs/heads/dev'})
    assert result.returncode == 0, result.stderr
    assert out.read_text().strip() == 'latest=false'


@pytest.mark.parametrize('job', ['docker-manifest', 'docker-fips-manifest', 'release'])
def test_a_run_of_another_tag_never_takes_latest(tmp_path, job):
    work = _origin_with_tags(tmp_path, ['v2.253', 'v2.254'])
    out = tmp_path / 'gh_output'
    step = _step('build-release.yml', job, 'Decide latest')
    result = _run_step(step, work, {'GITHUB_OUTPUT': str(out), 'VERSION': '2.254.2', 'GITHUB_REF': 'refs/tags/v2.254'})
    assert result.returncode == 0, result.stderr
    assert out.read_text().strip() == 'latest=false'


def test_an_unreachable_remote_never_decides_latest(tmp_path):
    work = _origin_with_tags(tmp_path, ['v2.254'])
    subprocess.run(['git', 'remote', 'set-url', 'origin', str(tmp_path / 'missing.git')], cwd=work, check=True)
    step = _step('build-release.yml', 'docker-manifest', 'Decide latest')
    result = _run_step(step, work, {'GITHUB_OUTPUT': str(tmp_path / 'o'), 'VERSION': '2.254.1', 'GITHUB_REF': 'refs/tags/v2.254.1'})
    assert result.returncode != 0


def _evaluate(expr, outputs):
    """Evaluate the only expression forms the workflow uses: ref, ref ==/!= 'lit', !ref."""
    expr = expr.strip()
    ref = r'steps\.latest\.outputs\.latest'
    if re.fullmatch(ref, expr):
        return outputs
    m = re.fullmatch(ref + r"\s*(==|!=)\s*'([^']*)'", expr)
    if m:
        return (outputs == m.group(2)) if m.group(1) == '==' else (outputs != m.group(2))
    m = re.fullmatch(r'!\s*' + ref, expr)
    if m:
        return outputs not in ('true', True)
    raise AssertionError(f'unsupported expression: {expr}')


def _render(text, outputs):
    def one(m):
        v = _evaluate(m.group(1), outputs)
        return str(v).lower() if isinstance(v, bool) else v
    return re.sub(r'\$\{\{(.*?)\}\}', one, text)


@pytest.mark.parametrize('latest', ['true', 'false'])
def test_the_image_and_release_tags_follow_the_step(latest):
    data = yaml.safe_load((WORKFLOWS / 'build-release.yml').read_text())
    for job, tag in (('docker-manifest', 'latest'), ('docker-fips-manifest', 'latest-fips')):
        meta = next(s for s in data['jobs'][job]['steps'] if s.get('id') == 'meta')
        line = next(ln for ln in meta['with']['tags'].splitlines() if f'value={tag},' in ln)
        assert _render(line.strip(), latest).endswith(f'enable={latest}'), line
    rel = next(s for s in data['jobs']['release']['steps'] if s.get('name') == 'Create release')
    assert _render(str(rel['with']['make_latest']), latest) == latest


# ---- 5. an installed instance ------------------------------------------------------------------

def _release(tag, kind='deb'):
    fv = rv.file_version(tag)
    names = rv.asset_names(tag)
    if kind == 'deb':
        assets = [names['deb']]
    else:
        assets = [names['rpm'], names['rpm_el9']]
    return {'tag_name': f'v{tag}', 'draft': False, 'prerelease': '-rc' in tag, 'body': '',
            'assets': [{'name': n, 'browser_download_url': f'http://x/{n}'} for n in assets] + [
                {'name': f'ucm_{fv}_all.deb.sha256', 'browser_download_url': 'http://x/s'}][:kind == 'deb']}


@pytest.fixture
def instance(monkeypatch):
    def setup(current, releases, deb=True, el=None):
        monkeypatch.setattr(updates, 'get_current_version', lambda: current)
        monkeypatch.setitem(updates._releases_cache, 'data', releases)
        monkeypatch.setitem(updates._releases_cache, 'ts', time.time())
        monkeypatch.setattr(updates.os.path, 'exists',
                            lambda p: p == ('/usr/bin/dpkg' if deb else '/usr/bin/rpm'))
        monkeypatch.setattr(updates, '_el_release', lambda: el)
        monkeypatch.delenv('UCM_DOCKER', raising=False)
    return setup


def test_stable_channel_offers_the_maintenance_release(instance):
    instance('2.254', [_release('2.254'), _release('2.254.1'), _release('2.254.1-rc1')])
    result = updates.check_for_updates(channel='stable')
    assert (result['update_available'], result['latest_version']) == (True, '2.254.1')


def test_only_the_rc_channel_sees_a_maintenance_rc(instance):
    instance('2.254', [_release('2.254'), _release('2.254.1-rc1')])
    assert updates.check_for_updates(channel='stable')['update_available'] is False
    result = updates.check_for_updates(channel='rc')
    assert (result['update_available'], result['latest_version']) == (True, '2.254.1-rc1')


def test_a_maintenance_instance_is_not_offered_the_base_release(instance):
    instance('2.254.1', [_release('2.254'), _release('2.254.1')])
    assert updates.check_for_updates(channel='stable')['update_available'] is False


def test_the_rc_of_a_maintenance_release_sits_between_the_two(instance):
    assert updates.compare_versions('2.254.1-rc1', '2.254') == 1
    assert updates.compare_versions('2.254.1-rc1', '2.254.1') == -1


@pytest.mark.parametrize('tag', ['2.254.1', '2.254.1-rc1'])
@pytest.mark.parametrize('kind,deb,el,asset', [('deb', True, None, 'deb'), ('rpm', False, None, 'rpm'),
                                               ('rpm', False, '9', 'rpm_el9')])
def test_the_requested_package_is_the_published_one(instance, tag, kind, deb, el, asset):
    instance('2.254', [_release('2.254'), _release(tag, kind)], deb=deb, el=el)
    result = updates.check_for_updates(channel='rc')
    assert result['latest_version'] == tag
    assert result['package_name'] == rv.asset_names(tag)[asset]


# ---- 6. version files and helper scripts -------------------------------------------------------

def test_version_files_agree():
    version = (ROOT / 'VERSION').read_text().strip()
    assert re.fullmatch(r'\d+\.\d+(\.\d+)?-dev', version)
    npm = re.sub(r'^(\d+\.\d+)-', r'\1.0-', version)
    pkg = json.loads((ROOT / 'frontend' / 'package.json').read_text())
    lock = json.loads((ROOT / 'frontend' / 'package-lock.json').read_text())
    assert pkg['version'] == lock['version'] == lock['packages']['']['version'] == npm


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


@pytest.mark.skipif(shutil.which('node') is None, reason='node is required')
@pytest.mark.parametrize('v,npm,chart', [
    ('2.254', '2.254.0', True), ('2.254.1', '2.254.1', True), ('2.254.2-rc1', '2.254.2-rc1', False),
    ('2.254.1-dev', '2.254.1-dev', False), ('2.254-dev', '2.254.0-dev', False),
])
def test_bump_version_updates_every_file(tmp_path, v, npm, chart):
    root = _scratch_tree(tmp_path)
    r = subprocess.run([BASH, str(root / 'scripts' / 'bump-version.sh'), v], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    lock = json.loads((root / 'frontend' / 'package-lock.json').read_text())
    assert (root / 'VERSION').read_text().strip() == v
    assert json.loads((root / 'frontend' / 'package.json').read_text())['version'] == npm
    assert lock['version'] == lock['packages']['']['version'] == npm
    assert (f'appVersion: "{v}"' in (root / 'charts/ucm/Chart.yaml').read_text()) is chart


def test_bump_version_refuses_a_version_the_release_grammar_refuses(tmp_path):
    root = _scratch_tree(tmp_path)
    r = subprocess.run([BASH, str(root / 'scripts' / 'bump-version.sh'), '2.254-1'], capture_output=True, text=True)
    assert r.returncode != 0
    assert not (root / 'VERSION').exists()


def test_npm_form_of_a_dev_version_and_tags_still_refuse_dev():
    assert _cli('npm', '2.254.1-dev').stdout.strip() == '2.254.1-dev'
    assert _cli('npm', '2.254-dev').stdout.strip() == '2.254.0-dev'
    assert _cli('validate', '2.254.1-dev').returncode != 0
    assert _cli('deb', '2.254.1-dev').returncode != 0


def test_wiki_versions_follow_a_three_segment_release(tmp_path):
    wiki = tmp_path / 'wiki'
    wiki.mkdir()
    (wiki / 'Installation-Guide.md').write_text('')
    (wiki / 'Home.md').write_text(
        '![v](https://img/version-2.254-brightgreen)\n'
        'docker pull neyslim/ultimate-ca-manager:2.254\n'
        'wget https://h/releases/download/v2.254/ucm_2.254_all.deb\n'
        'wget https://h/releases/download/v2.254/ucm-el9-2.254-1.el9.noarch.rpm\n'
        '| Latest Stable | 2.254 |\n')
    subprocess.run(['git', 'init', '-q'], cwd=wiki, check=True)
    subprocess.run(['git', 'add', '-A'], cwd=wiki, check=True)
    subprocess.run(['git', '-c', 'user.name=t', '-c', 'user.email=t@t', 'commit', '-qm', 'x'], cwd=wiki, check=True)
    r = subprocess.run([BASH, str(ROOT / 'scripts' / 'update-wiki-versions.sh'), '2.254.1', str(wiki)],
                       capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    text = (wiki / 'Home.md').read_text()
    assert 'version-2.254.1-brightgreen' in text and 'manager:2.254.1\n' in text
    assert 'v2.254.1/ucm_2.254.1_all.deb' in text and 'ucm-el9-2.254.1-1.el9.noarch.rpm' in text
    assert '| Latest Stable | 2.254.1 |' in text and '2.254.1.1' not in text


def test_the_watcher_matches_a_three_segment_target():
    src = (ROOT / 'packaging' / 'scripts' / 'ucm-watcher.sh').read_text()
    func = re.search(r'^versions_match\(\) \{.*?^\}', src, re.S | re.M).group(0)
    def match(d, t):
        return subprocess.run([BASH, '-c', f'{func}\nversions_match "$1" "$2"', 'x', d, t]).returncode == 0
    assert match('2.254.1', '2.254.1') and match('2.254.1~rc1', '2.254.1-rc1') and match('2.254.1-1', '2.254.1')
    assert not match('2.254', '2.254.1') and not match('2.254.1', '2.254')
    assert not match('2.254.1-1', '2.254')


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


def test_smoke_release_refuses_a_version_that_only_starts_the_same(monkeypatch):
    assert 'version mismatch' in _health_run(monkeypatch, '2.254.1', '2.254')
    assert 'version mismatch' in _health_run(monkeypatch, '2.254', '2.254.1')


def test_smoke_release_accepts_the_exact_version(monkeypatch):
    assert 'version mismatch' not in _health_run(monkeypatch, '2.254.1', '2.254.1')


# ---- 7. the manual publisher follows the same rules ---------------------------------------------

def _publish(tmp_path, tags, version, changelog, *flags):
    work = _origin_with_tags(tmp_path, tags)
    (work / 'scripts' / 'release_publish.sh').write_text((ROOT / 'scripts' / 'release_publish.sh').read_text())
    (work / 'CHANGELOG.md').write_text(changelog)
    fake = tmp_path / 'bin'
    fake.mkdir()
    log = tmp_path / 'gh.args'
    gh = fake / 'gh'
    gh.write_text(
        '#!/bin/sh\n'
        f'if [ "$1 $2" = "release view" ] && [ ! -e "{log}" ]; then exit 1; fi\n'
        'if [ "$1 $2" = "release create" ]; then\n'
        f'  for a in "$@"; do echo "$a"; done > "{log}"\n'
        '  while [ $# -gt 0 ]; do [ "$1" = "--notes-file" ] && '
        f'cp "$2" "{log}.notes"; shift; done\n'
        'fi\n')
    gh.chmod(0o755)
    env = {**os.environ, 'PATH': f'{fake}:{os.environ["PATH"]}'}
    result = subprocess.run([BASH, 'scripts/release_publish.sh', version, *flags], cwd=work, env=env,
                            capture_output=True, text=True)
    return result, log


PUBLISH_CHANGELOG = ('## [2x254x1]\n- Dots are literal.\n\n## [2.254.1] - 2026-12-01\n- Fixed a.b thing.\n\n'
             '## [2.254] - 2026-11-13\n- Older entry.\n')


@pytest.mark.parametrize('tags,version,latest', [
    (['v2.253', 'v2.254', 'v2.254.1'], '2.254.1', 'true'),
    (['v2.254', 'v2.254.1', 'v9.0'], '2.254.1', 'false'),
])
def test_release_publish_passes_the_latest_rule_and_the_section(tmp_path, tags, version, latest):
    result, log = _publish(tmp_path, tags, version, PUBLISH_CHANGELOG)
    assert result.returncode == 0, result.stderr
    args = log.read_text().splitlines()
    assert f'--latest={latest}' in args
    notes = pathlib.Path(str(log) + '.notes').read_text()
    assert 'Fixed a.b thing.' in notes and 'Older entry' not in notes and 'Dots are literal' not in notes


@pytest.mark.parametrize('flag', ['--draft', '--pre'])
def test_release_publish_never_marks_a_draft_or_a_prerelease_latest(tmp_path, flag):
    result, log = _publish(tmp_path, ['v2.253', 'v2.254', 'v2.254.1'], '2.254.1', PUBLISH_CHANGELOG, flag)
    assert result.returncode == 0, result.stderr
    assert '--latest=false' in log.read_text().splitlines()

