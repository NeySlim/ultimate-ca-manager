"""No deliverable of a release goes out without its SBOM: every package and every image platform the
build matrices produce carries one, the manifests and the release check them before anything is
tagged or published, and the checks are the real script, run here on temporary directories."""
import copy
import fnmatch
import os
import pathlib
import shutil
import subprocess
import sys

import pytest

from tests import sbom_support as s
from tests.workflow_support import ROOT, load, render

IMAGE_JOBS = {'build-docker': ('std', 'standard'), 'build-docker-fips': ('fips', 'fips')}
MANIFESTS = {'docker-manifest': ('std', 'standard'), 'docker-fips-manifest': ('fips', 'fips')}


def _jobs():
    return load('build-release.yml')['jobs']


def _uploads(job):
    return [st for st in job.get('steps', []) if str(st.get('uses', '')).startswith('actions/upload-artifact@')]


def _paths(step):
    return [t.strip() for t in str(step['with'].get('path', '')).splitlines() if t.strip()]


def _index(job, pred):
    hits = [i for i, st in enumerate(job['steps']) if pred(st)]
    assert len(hits) == 1, hits
    return hits[0]


def _named(name):
    return lambda st: st.get('name') == name


def _legs(job):
    return job.get('strategy', {}).get('matrix', {}).get('include') or [{}]


# ---- coverage: deduced from the build matrices -------------------------------------------------------

def packages_without_sbom(jobs):
    """Package globs uploaded without their SBOM and its checksum in the same artifact."""
    missing = []
    for name, job in jobs.items():
        for st in _uploads(job):
            paths = _paths(st)
            for g in (p for p in paths if p.endswith(('.deb', '.rpm'))):
                if g + '.cdx.json' not in paths or g + '.cdx.json.sha256' not in paths:
                    missing.append(f'{name}:{g}')
                elif st['with'].get('if-no-files-found') != 'error':
                    missing.append(f'{name}:{g} (an empty upload passes)')
    return missing


def images_without_sbom(jobs):
    """(job, leg) image builds pushing a digest without the SBOM artifact of that leg."""
    missing = []
    for name, job in jobs.items():
        if not any('push-by-digest=true' in str(st.get('with', {}).get('outputs', '')) for st in job.get('steps', [])):
            continue
        prefix = IMAGE_JOBS.get(name, ('?',))[0]
        for leg in _legs(job):
            names = {render(st['with']['name'], {'matrix': leg}) for st in _uploads(job)}
            if f"{prefix}-sbom-{leg.get('arch')}" not in names:
                missing.append(f"{name}:{leg.get('arch')}")
    return missing


def test_the_matrices_give_four_packages_and_four_image_platforms():
    jobs = _jobs()
    pkgs = [g for j in jobs.values() for st in _uploads(j) for g in _paths(st) if g.endswith(('.deb', '.rpm'))]
    legs = sum(len(_legs(j)) for n, j in jobs.items() if n == 'build-rpm') + 1
    assert len(pkgs) == 2 and legs == 4  # one DEB glob, one RPM glob over three matrix legs
    assert sorted(f'{n}:{leg["arch"]}' for n in IMAGE_JOBS for leg in _legs(jobs[n])) == [
        'build-docker-fips:amd64', 'build-docker-fips:arm64', 'build-docker:amd64', 'build-docker:arm64']
    assert packages_without_sbom(jobs) == [] and images_without_sbom(jobs) == []


def test_a_package_uploaded_without_its_sbom_is_caught():
    jobs = copy.deepcopy(_jobs())
    st = _uploads(jobs['build-rpm'])[0]
    st['with']['path'] = '\n'.join(p for p in _paths(st) if not p.endswith('.cdx.json'))
    assert packages_without_sbom(jobs) == ['build-rpm:/tmp/rpm-output/*.rpm']


def test_a_second_package_job_without_sbom_is_caught():
    jobs = copy.deepcopy(_jobs())
    job = copy.deepcopy(jobs['build-deb'])
    _uploads(job)[0]['with']['path'] = 'ucm-noble_*.deb\nucm-noble_*.deb.sha256'
    jobs['build-deb-noble'] = job
    assert packages_without_sbom(jobs) == ['build-deb-noble:ucm-noble_*.deb']


def test_a_new_image_leg_gets_its_sbom_and_a_job_without_one_is_caught():
    jobs = copy.deepcopy(_jobs())
    jobs['build-docker']['strategy']['matrix']['include'].append({'arch': 'riscv64', 'runner': 'x'})
    assert images_without_sbom(jobs) == []  # the upload is named after the leg
    for st in _uploads(jobs['build-docker-fips']):
        if 'sbom' in st['with']['name']:
            jobs['build-docker-fips']['steps'].remove(st)
    assert images_without_sbom(jobs) == ['build-docker-fips:amd64', 'build-docker-fips:arm64']


@pytest.mark.parametrize('job', ['build-deb', 'build-rpm', 'build-docker', 'build-docker-fips'])
def test_each_build_records_its_own_frontend_after_building_it(job):
    j = _jobs()[job]
    built = _index(j, _named('Build frontend'))
    rec = _index(j, _named('Record the frontend build for the SBOM'))
    assert rec == built + 1
    assert 'sbom.py frontend' in j['steps'][rec]['run']


@pytest.mark.parametrize('job, step, after', [
    ('build-deb', 'SBOM of the DEB', 'Generate checksums'),
    ('build-rpm', 'SBOM of the RPM', 'Build RPM in ${{ matrix.label }} container'),
])
def test_a_package_sbom_is_made_from_the_built_file_before_its_upload(job, step, after):
    j = _jobs()[job]
    i = _index(j, _named(step))
    assert _index(j, _named(after)) < i < _index(j, lambda st: st in _uploads(j))
    st = j['steps'][i]
    assert 'if' not in st and not st.get('continue-on-error')
    assert 'sbom.py package' in st['run'] and 'sbom-venv.sh' in st['run']


@pytest.mark.parametrize('job', IMAGE_JOBS)
def test_an_image_sbom_is_made_from_the_pushed_digest_before_the_digest_leaves(job):
    j = _jobs()[job]
    prefix, variant = IMAGE_JOBS[job]
    push = _index(j, lambda st: st.get('id') == 'push')
    sbom = _index(j, _named('SBOM of the pushed image'))
    upload = _index(j, _named('Upload the image SBOM'))
    export = _index(j, _named('Export digest'))
    assert push < sbom < upload < export
    st = j['steps'][sbom]
    assert st['run'] == f'scripts/ci/sbom-image.sh {variant}'
    # The digest of the push that ran (the registry or the rehearsal one), never a tag nor the check image
    assert st['env']['DIGEST'] == '${{ steps.built.outputs.digest }}'
    assert st['env']['REPOSITORY'] == '${{ steps.built.outputs.repository }}'
    built = j['steps'][_index(j, _named('Digest of the build'))]
    assert built['env']['DIGEST'] == '${{ steps.push.outputs.digest || steps.rehearse.outputs.digest }}'
    assert _index(j, lambda s: s.get('id') == 'rehearse') < _index(j, _named('Digest of the build')) < sbom
    assert not st.get('continue-on-error') and not j.get('continue-on-error')
    up = j['steps'][upload]
    assert up['with']['if-no-files-found'] == 'error'
    for leg in _legs(j):
        assert render(up['with']['name'], {'matrix': leg}) == f"{prefix}-sbom-{leg['arch']}"


@pytest.mark.parametrize('job', IMAGE_JOBS)
def test_image_sboms_follow_the_digest_rule(job):
    """Every run pushes its image, to a registry or to the rehearsal one: its SBOM goes with its digest."""
    j = _jobs()[job]
    for name in ('SBOM of the pushed image', 'Upload the image SBOM', 'Export digest', 'Digest of the build'):
        assert 'if' not in j['steps'][_index(j, _named(name))], name


# ---- manifests: no tag without both SBOMs on the digests about to be tagged ----------------------

@pytest.mark.parametrize('job', MANIFESTS)
def test_a_manifest_requires_its_sboms_before_tagging(job):
    j = _jobs()[job]
    prefix, variant = MANIFESTS[job]
    dl = _index(j, _named('Download the SBOMs'))
    req = _index(j, _named('Require the SBOM of each architecture'))
    assert _index(j, _named('Require both architectures')) < req < _index(j, _named('Create manifest lists'))
    assert dl < req
    pattern = j['steps'][dl]['with']['pattern']
    assert fnmatch.fnmatch(f'{prefix}-sbom-amd64', pattern) and fnmatch.fnmatch(f'{prefix}-sbom-arm64', pattern)
    other = 'fips' if prefix == 'std' else 'std'
    for name in (f'{other}-sbom-amd64', f'{prefix}-digest-amd64'):
        assert not fnmatch.fnmatch(name, pattern), name
    assert f'--variant {variant}' in j['steps'][req]['run']


@pytest.fixture(scope='module')
def built_release(tmp_path_factory):
    base = tmp_path_factory.mktemp('wf-release')
    art, digests = s.release_dir(base)
    return art, digests


def _run_manifest_check(tmp_path, job, art, digests, drop=None):
    prefix, variant = MANIFESTS[job]
    temp = tmp_path / 'runner-temp'
    (temp / 'digests').mkdir(parents=True)
    (temp / 'sboms').mkdir()
    for d in digests.glob(f'{prefix}-digest-*'):
        for f in d.iterdir():
            shutil.copy(f, temp / 'digests' / f.name)
    for f in art.glob(f'ucm-*-image-{variant}-*.cdx.json*'):
        if drop is None or drop not in f.name:
            shutil.copy(f, temp / 'sboms' / f.name)
    st = _jobs()[job]['steps'][_index(_jobs()[job], _named('Require the SBOM of each architecture'))]
    ctx = {'runner': {'temp': str(temp)}, 'needs': {'build-deb': {'outputs': {'version': s.VERSION}}}}
    env = {k: render(v, ctx) for k, v in st.get('env', {}).items()}
    return subprocess.run(['bash', '-e', '-c', render(st['run'], ctx)], cwd=ROOT, capture_output=True, text=True,
                          env={**env, 'PATH': os.environ['PATH']}, timeout=120)


@pytest.mark.parametrize('job', MANIFESTS)
def test_the_manifest_check_runs_and_refuses_a_missing_sbom(tmp_path, built_release, job):
    art, digests = built_release
    proc = _run_manifest_check(tmp_path / 'ok', job, art, digests)
    assert proc.returncode == 0, proc.stderr
    proc = _run_manifest_check(tmp_path / 'ko', job, art, digests, drop='arm64')
    assert proc.returncode != 0


# ---- the release: every SBOM checked before any asset is deleted or published ----------------------

def test_the_release_checks_the_sboms_before_deleting_or_publishing():
    j = _jobs()['release']
    check = _index(j, _named('Check the SBOMs'))
    downloads = [i for i, st in enumerate(j['steps']) if str(st.get('uses', '')).startswith('actions/download-artifact@')]
    assert max(downloads) < check
    assert _index(j, lambda st: 'migration_marks.py' in str(st.get('run', ''))) < check
    assert check < _index(j, _named('Delete existing release assets')) < _index(j, _named('Create release'))
    st = j['steps'][check]
    assert 'if' not in st and not st.get('continue-on-error')
    create = j['steps'][_index(j, _named('Create release'))]
    assert 'artifacts/*' in create['with']['files']
    pats = [st['with']['pattern'] for st in j['steps'] if 'pattern' in st.get('with', {})]
    for name in ('std-sbom-amd64', 'std-sbom-arm64', 'fips-sbom-amd64', 'fips-sbom-arm64'):
        assert any(fnmatch.fnmatch(name, p) for p in pats), name
    for name in ('std-digest-amd64', 'fips-digest-arm64'):
        assert any(fnmatch.fnmatch(name, p) for p in pats), name


def _run_release_check(tmp_path, art, digests, breakage=None):
    work = tmp_path / 'workspace'
    (work / 'scripts' / 'ci').mkdir(parents=True)
    shutil.copytree(art, work / 'artifacts')
    temp = tmp_path / 'runner-temp'
    temp.mkdir()
    shutil.copytree(digests, temp / 'digests')
    (work / 'scripts' / 'ci' / 'sbom.py').symlink_to(s.SCRIPT)
    # The pinned validator is installed from the network in CI; here the test interpreter holds it
    venv = work / 'scripts' / 'ci' / 'sbom-venv.sh'
    venv.write_text(f'#!/bin/sh\nmkdir -p "$1/bin"\nprintf \'#!/bin/sh\\nexec {sys.executable} "$@"\\n\' > "$1/bin/python"\n'
                    'chmod +x "$1/bin/python"\n')
    venv.chmod(0o755)
    if breakage:
        breakage(work / 'artifacts', temp / 'digests')
    st = _jobs()['release']['steps'][_index(_jobs()['release'], _named('Check the SBOMs'))]
    ctx = {'needs': {'build-deb': {'outputs': {'version': s.VERSION}}}}
    env = {k: render(v, ctx) for k, v in st.get('env', {}).items()}
    clean = {k: v for k, v in os.environ.items() if not k.startswith('GIT_')}
    return subprocess.run(['bash', '-e', '-c', st['run']], cwd=work, capture_output=True, text=True,
                          env={**clean, **env, 'RUNNER_TEMP': str(temp)}, timeout=300), work


def test_the_release_check_passes_a_complete_release_and_indexes_it(tmp_path, built_release):
    proc, work = _run_release_check(tmp_path, *built_release)
    assert proc.returncode == 0, proc.stderr
    assert (work / 'artifacts' / 'sbom-index.json').is_file()
    assert (work / 'artifacts' / 'sbom-index.json.sha256').is_file()
    # Still published next to them
    assert (work / 'artifacts' / 'full-stop-migrations.json').is_file()
    assert len(list((work / 'artifacts').glob('*.rpm.sha256'))) == 3


@pytest.mark.parametrize('breakage', [
    lambda art, d: (art / 'ucm-3.0.rc1-image-fips-arm64.cdx.json').unlink(),
    lambda art, d: (art / 'ucm-el10-3.0.rc1-1.el10.noarch.rpm.cdx.json').write_text(''),
    lambda art, d: (art / 'ucm_3.0~rc1_all.deb').write_bytes(b'not the described package'),
], ids=['missing-fips-arm64', 'empty-rpm-sbom', 'package-not-described'])
def test_the_release_check_stops_a_release_with_a_missing_or_wrong_sbom(tmp_path, built_release, breakage):
    proc, _ = _run_release_check(tmp_path, *built_release, breakage=breakage)
    assert proc.returncode != 0
    assert '::error::SBOM:' in proc.stderr


# ---- what a failed SBOM holds back -----------------------------------------------------------------

def _needs(job):
    n = job.get('needs', [])
    return n if isinstance(n, list) else [n]


def _closure(jobs, name):
    seen, todo = set(), list(_needs(jobs[name]))
    while todo:
        n = todo.pop()
        if n not in seen:
            seen.add(n)
            todo += _needs(jobs[n])
    return seen


@pytest.mark.parametrize('job, held', [
    ('build-docker-fips', {'docker-fips-manifest', 'release', 'docker-manifest'}),
    ('build-docker', {'docker-manifest', 'release', 'docker-fips-manifest'}),
    ('build-rpm', {'release', 'docker-manifest', 'docker-fips-manifest'}),
])
def test_a_failed_sbom_holds_back_every_publication(job, held):
    """An SBOM step fails its build job, which every publication needs (the smoke needs the image
    builds too), and none of them runs on a failed dependency."""
    jobs = _jobs()
    for name in held:
        assert job in _closure(jobs, name), name
        cond = str(jobs[name].get('if', ''))
        assert not any(f in cond for f in ('always()', 'failure()', 'cancelled()')), name


# ---- pinned tools ----------------------------------------------------------------------------------

def _stub_bin(tmp_path, scripts):
    bindir = tmp_path / 'bin'
    bindir.mkdir()
    for name, body in scripts.items():
        f = bindir / name
        f.write_text('#!/bin/sh\n' + body + '\n')
        f.chmod(0o755)
    for tool in ('sh', 'mkdir', 'sha256sum', 'tar', 'rm', 'grep', 'dirname', 'uname', 'cat', 'printf', 'chmod'):
        if shutil.which(tool) and not (bindir / tool).exists():
            (bindir / tool).symlink_to(shutil.which(tool))
    return bindir


def test_trivy_is_refused_when_its_archive_is_not_the_pinned_one(tmp_path):
    # A well-formed archive whose binary even reports the pinned version: only the checksum tells
    import tarfile
    forged = tmp_path / 'forged'
    forged.mkdir()
    (forged / 'trivy').write_text('#!/bin/sh\necho "Version: 0.70.0"\n')
    (forged / 'trivy').chmod(0o755)
    archive = tmp_path / 'forged.tar.gz'
    with tarfile.open(archive, 'w:gz') as tar:
        tar.add(forged / 'trivy', arcname='trivy')
    bindir = _stub_bin(tmp_path, {'curl': f'while [ "$1" != -o ]; do shift; done; cat {archive} > "$2"'})
    dest = tmp_path / 'trivy'
    proc = subprocess.run(['sh', str(ROOT / 'scripts' / 'ci' / 'install-trivy.sh'), str(dest), 'amd64'],
                          capture_output=True, text=True, env={'PATH': str(bindir)}, timeout=60)
    assert proc.returncode != 0 and 'checksum mismatch' in proc.stderr
    assert not (dest / 'trivy').exists()


def test_trivy_is_pinned_by_version_and_checksum_for_both_runners():
    text = (ROOT / 'scripts' / 'ci' / 'install-trivy.sh').read_text()
    import re
    assert re.search(r'^TRIVY_VERSION=\d+\.\d+\.\d+$', text, re.M)
    assert len(re.findall(r'^TRIVY_SHA256_(AMD64|ARM64)=[0-9a-f]{64}$', text, re.M)) == 2


def test_the_validator_is_installed_by_hash_only(tmp_path):
    reqs = (ROOT / 'scripts' / 'ci' / 'sbom-data' / 'requirements.txt').read_text()
    entries = [e for e in reqs.replace('\\\n', ' ').splitlines() if e.strip() and not e.startswith('#')]
    assert entries
    for e in entries:
        assert '==' in e and '--hash=sha256:' in e, e
    log = tmp_path / 'pip.log'
    pip = f'echo "$@" > {log}'
    bindir = _stub_bin(tmp_path, {
        'python3': f'mkdir -p "$3/bin"; printf \'#!/bin/sh\\n{pip}\\n\' > "$3/bin/pip"; '
                   'printf \'#!/bin/sh\\nexit 0\\n\' > "$3/bin/python"; chmod +x "$3/bin/pip" "$3/bin/python"'})
    proc = subprocess.run(['sh', str(ROOT / 'scripts' / 'ci' / 'sbom-venv.sh'), str(tmp_path / 'venv')],
                          capture_output=True, text=True, env={'PATH': str(bindir)}, timeout=60)
    assert proc.returncode == 0, proc.stderr
    args = log.read_text().split()
    assert {'--require-hashes', '--no-deps', '--only-binary', ':all:'} <= set(args)


# ---- no release created around the workflow -------------------------------------------------------

def _release_checkout(tmp_path):
    """A checkout whose CHANGELOG holds an RC section: the script is read, not the repository's notes."""
    repo = tmp_path / 'repo'
    (repo / 'scripts' / 'ci').mkdir(parents=True)
    shutil.copy(ROOT / 'scripts' / 'ci' / 'release_version.py', repo / 'scripts' / 'ci')
    (repo / 'CHANGELOG.md').write_text('# Changelog\n\n## [3.0-rc1] - 2026-01-01\n\n### Fixed\n- An entry.\n')
    return repo


def test_the_publish_script_never_creates_a_release(tmp_path):
    """Only the workflow creates a release, with its SBOMs: the script edits the notes of one."""
    calls = tmp_path / 'gh.calls'
    bindir = _stub_bin(tmp_path, {
        'git': f'case "$1" in rev-parse) echo {_release_checkout(tmp_path)};; ls-remote) printf "x\\trefs/tags/v3.0-rc1\\n";; esac',
        'gh': f'echo "$@" >> {calls}; case "$1 $2" in "release view") exit 1;; "repo view") echo o/r;; esac; exit 0',
        'python3': f'exec {sys.executable} "$@"',
    })
    for tool in ('sed', 'tr', 'mktemp', 'bash'):
        (bindir / tool).symlink_to(shutil.which(tool))
    clean = {k: v for k, v in os.environ.items() if not k.startswith('GIT_')}
    proc = subprocess.run(['bash', str(ROOT / 'scripts' / 'release_publish.sh'), '3.0-rc1'], cwd=tmp_path,
                          capture_output=True, text=True, env={**clean, 'PATH': str(bindir)}, timeout=60)
    assert proc.returncode != 0
    assert 'Build & Release workflow' in proc.stderr
    assert 'release create' not in (calls.read_text() if calls.exists() else '')


def test_the_publish_script_still_edits_the_notes_of_a_release(tmp_path):
    calls = tmp_path / 'gh.calls'
    bindir = _stub_bin(tmp_path, {
        'git': f'case "$1" in rev-parse) echo {_release_checkout(tmp_path)};; ls-remote) printf "x\\trefs/tags/v3.0-rc1\\n";; esac',
        'gh': f'echo "$@" >> {calls}; case "$1 $2" in "repo view") echo o/r;; esac; exit 0',
        'python3': f'exec {sys.executable} "$@"',
    })
    for tool in ('sed', 'tr', 'mktemp', 'bash'):
        (bindir / tool).symlink_to(shutil.which(tool))
    clean = {k: v for k, v in os.environ.items() if not k.startswith('GIT_')}
    proc = subprocess.run(['bash', str(ROOT / 'scripts' / 'release_publish.sh'), '3.0-rc1', '--edit'], cwd=tmp_path,
                          capture_output=True, text=True, env={**clean, 'PATH': str(bindir)}, timeout=60)
    assert proc.returncode == 0, proc.stderr
    text = calls.read_text()
    assert 'release edit v3.0-rc1' in text and 'release create' not in text
    assert pathlib.Path(ROOT / 'scripts' / 'release_publish.sh').is_file()
