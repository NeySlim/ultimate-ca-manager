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


# ---- 4. latest ---------------------------------------------------------------------------------

@pytest.mark.parametrize('published,tag,expected', [
    (['v2.253', 'v2.254'], '2.254.1', 'true'),
    (['v2.254', 'v3.0'], '2.254.2', 'false'),
    (['v2.254', 'v2.254.1-rc1'], '2.254.1-rc1', 'false'),
    (['v3.0'], '3.1', 'true'),
    (['v2.254', 'v2.254.1', 'v2.254.2-rc1', 'v3.0-rc1'], '2.254.1', 'true'),
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
    (['v2.254', 'v3.0', 'v2.254.2'], '2.254.2', 'false'),
    (['v2.254', 'v2.254.1-rc1'], '2.254.1-rc1', 'false'),
])
def test_the_latest_step_reads_the_remote_tags(tmp_path, job, tags, version, expected):
    work = _origin_with_tags(tmp_path, tags)
    out = tmp_path / 'gh_output'
    step = _step('build-release.yml', job, 'Decide latest')
    result = _run_step(step, work, {'GITHUB_OUTPUT': str(out), 'VERSION': version})
    assert result.returncode == 0, result.stderr
    assert out.read_text().strip() == f'latest={expected}'


def test_an_unreachable_remote_never_decides_latest(tmp_path):
    work = _origin_with_tags(tmp_path, ['v2.254'])
    subprocess.run(['git', 'remote', 'set-url', 'origin', str(tmp_path / 'missing.git')], cwd=work, check=True)
    step = _step('build-release.yml', 'docker-manifest', 'Decide latest')
    result = _run_step(step, work, {'GITHUB_OUTPUT': str(tmp_path / 'o'), 'VERSION': '2.254.1'})
    assert result.returncode != 0


def test_the_image_and_release_tags_follow_the_step():
    data = yaml.safe_load((WORKFLOWS / 'build-release.yml').read_text())
    for job, tag in (('docker-manifest', 'latest'), ('docker-fips-manifest', 'latest-fips')):
        meta = next(s for s in data['jobs'][job]['steps'] if s.get('id') == 'meta')
        line = next(ln for ln in meta['with']['tags'].splitlines() if f'value={tag},' in ln)
        assert 'steps.latest.outputs.latest' in line
    rel = next(s for s in data['jobs']['release']['steps'] if s.get('name') == 'Create release')
    assert 'steps.latest.outputs.latest' in str(rel['with']['make_latest'])


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
    shutil.copy(ROOT / 'frontend' / 'package.json', root / 'frontend')
    shutil.copy(ROOT / 'frontend' / 'package-lock.json', root / 'frontend')
    shutil.copy(ROOT / 'charts' / 'ucm' / 'Chart.yaml', root / 'charts' / 'ucm')
    return root


@pytest.mark.skipif(shutil.which('node') is None, reason='node is required')
@pytest.mark.parametrize('v,chart', [('2.254', True), ('2.254.1', True), ('2.254.1-rc1', False)])
def test_bump_version_updates_every_file(tmp_path, v, chart):
    root = _scratch_tree(tmp_path)
    r = subprocess.run([BASH, str(root / 'scripts' / 'bump-version.sh'), v], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    lock = json.loads((root / 'frontend' / 'package-lock.json').read_text())
    assert (root / 'VERSION').read_text().strip() == v
    assert json.loads((root / 'frontend' / 'package.json').read_text())['version'] == v
    assert lock['version'] == lock['packages']['']['version'] == v
    assert (f'appVersion: "{v}"' in (root / 'charts/ucm/Chart.yaml').read_text()) is chart


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
