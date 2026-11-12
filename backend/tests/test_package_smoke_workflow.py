"""Every package built for a release is installed by the package smoke, in its distribution."""
import copy
import fnmatch
import pathlib
import shutil
import subprocess

import pytest
import yaml

ROOT = pathlib.Path(__file__).resolve().parents[2]
WORKFLOWS = ROOT / '.github' / 'workflows'
SCRIPT = ROOT / 'scripts' / 'ci' / 'package-smoke.sh'


def _load(name):
    return yaml.safe_load((WORKFLOWS / name).read_text())


def _dist(image):
    name, _, tag = image.partition(':')
    return {'fedora': 'fc', 'almalinux': 'el'}[name] + tag


def _built_packages(build):
    """(sample asset name, build image or None for a DEB) of every package the build produces."""
    out = []
    for name, job in build['jobs'].items():
        paths = ''
        for step in job.get('steps', []):
            if str(step.get('uses', '')).startswith('actions/upload-artifact'):
                paths += str(step.get('with', {}).get('path', '')) + '\n'
        globs = [g.strip() for g in paths.split() if g.strip().endswith(('.deb', '.rpm'))]
        matrix = job.get('strategy', {}).get('matrix', {}).get('include', [])
        for g in globs:
            if g.endswith('.deb'):
                out.append((g.replace('*', '2.1_all'), None))
        if any(g.endswith('.rpm') for g in globs):
            # An RPM's distribution is only known from matrix.include: refuse what cannot be sampled.
            if not matrix:
                raise AssertionError(f'{name}: RPM job without matrix.include')
            for e in matrix:
                out.append((f"{e['asset_prefix']}2.1-1.{_dist(e['image'])}.noarch.rpm", e['image']))
    return out


def _uncovered(build, release_smoke):
    matrix = release_smoke['jobs']['smoke-packages']['strategy']['matrix']['include']
    missing = []
    for sample, image in _built_packages(build):
        if image is None:
            ok = any(fnmatch.fnmatch(sample, e['pattern']) and e['image'].split(':')[0] in ('debian', 'ubuntu')
                     for e in matrix)
        else:
            ok = any(fnmatch.fnmatch(sample, e['pattern']) and e['image'] == image for e in matrix)
        if not ok:
            missing.append(sample)
    return missing


def _smoked():
    matrix = _load('release-smoke.yml')['jobs']['smoke-packages']['strategy']['matrix']['include']
    return [(e['pattern'], e['image']) for e in matrix]


def test_every_built_package_has_a_smoke_in_its_own_image():
    build = _load('build-release.yml')
    assert len(_built_packages(build)) == 4
    assert _uncovered(build, _load('release-smoke.yml')) == []


def test_a_wrong_rpm_pattern_is_caught():
    smoke = copy.deepcopy(_load('release-smoke.yml'))
    for e in smoke['jobs']['smoke-packages']['strategy']['matrix']['include']:
        if e['image'] == 'fedora:43':
            e['pattern'] = 'ucm-el9-*.el9.noarch.rpm'
    assert _uncovered(_load('build-release.yml'), smoke) == ['ucm-2.1-1.fc43.noarch.rpm']


def test_an_unsmoked_second_deb_job_is_caught():
    build = copy.deepcopy(_load('build-release.yml'))
    job = copy.deepcopy(build['jobs']['build-deb'])
    for step in job['steps']:
        if str(step.get('uses', '')).startswith('actions/upload-artifact'):
            step['with']['path'] = 'ucm-noble_*.deb'
    build['jobs']['build-deb-noble'] = job
    assert _uncovered(build, _load('release-smoke.yml')) == ['ucm-noble_2.1_all.deb']


def _rpm_job_with_matrix(matrix):
    build = copy.deepcopy(_load('build-release.yml'))
    job = copy.deepcopy(next(j for j in build['jobs'].values()
                             if j.get('strategy', {}).get('matrix', {}).get('include')))
    if matrix is None:
        job.pop('strategy', None)
    else:
        job['strategy']['matrix'] = matrix
    build['jobs']['build-rpm-extra'] = job
    return build


@pytest.mark.parametrize('matrix', [None, {'image': ['opensuse/leap:16']}])
def test_an_rpm_job_without_matrix_include_is_refused(matrix):
    with pytest.raises(AssertionError, match='build-rpm-extra'):
        _built_packages(_rpm_job_with_matrix(matrix))


def test_the_deb_is_smoked_on_debian_and_ubuntu():
    images = {img for p, img in _smoked() if fnmatch.fnmatch('ucm_2.1_all.deb', p)}
    assert {'debian:13', 'ubuntu:24.04', 'ubuntu:26.04'} <= images


def test_smoke_matrix_does_not_stop_at_the_first_failure():
    job = _load('release-smoke.yml')['jobs']['smoke-packages']
    assert job['strategy']['fail-fast'] is False


def test_script_is_valid_shell():
    assert subprocess.run(['sh', '-n', str(SCRIPT)]).returncode == 0


@pytest.mark.skipif(not shutil.which('shellcheck'), reason='shellcheck not installed')
def test_script_passes_shellcheck():
    assert subprocess.run(['shellcheck', '-s', 'sh', str(SCRIPT)]).returncode == 0


def _stubbed_run(tmp_path, kind, sudo_present, su_present=True):
    """Run the script against stub commands; returns (ordered command log, completed process)."""
    bin_dir = tmp_path / 'bin'
    bin_dir.mkdir()
    log = tmp_path / 'log'
    def stub(name, body):
        f = bin_dir / name
        f.write_text('#!/bin/sh\n' + body + '\n')
        f.chmod(0o755)
    for tool in ('tr', 'rm', 'cat', 'tail', 'mkdir', 'chown', 'sleep', 'kill'):
        (bin_dir / tool).symlink_to(shutil.which(tool))  # no host sudo on the PATH
    stub('id', 'echo 0')
    stub('dpkg-deb', 'echo 1.0')
    stub('rpm', 'echo 1.0')
    stub('apt-get', f'echo "apt-get $*" >> {log}; exit 1')
    stub('dnf', f'echo "dnf $*" >> {log}; exit 1')
    stub('dpkg', f'echo "dpkg $*" >> {log}; rm -f {bin_dir}/sudo')
    if sudo_present:
        stub('sudo', 'exit 0')
    if su_present:
        stub('su', 'exit 1')
    pkg = tmp_path / f'ucm.{kind}'
    pkg.write_text('x')
    proc = subprocess.run(['/bin/sh', str(SCRIPT), str(pkg)], env={'PATH': f'{bin_dir}'},
                          capture_output=True, text=True, cwd=tmp_path)
    return (log.read_text().splitlines() if log.exists() else []), proc


def test_a_preinstalled_sudo_is_removed_before_the_install(tmp_path):
    calls, _ = _stubbed_run(tmp_path, 'deb', sudo_present=True)
    assert calls[0].startswith('dpkg --purge') and calls[1].startswith('apt-get')


def test_no_sudo_removal_when_the_image_has_none(tmp_path):
    calls, _ = _stubbed_run(tmp_path, 'deb', sudo_present=False)
    assert calls and calls[0].startswith('apt-get')


def test_a_missing_su_stops_before_the_package_install(tmp_path):
    calls, proc = _stubbed_run(tmp_path, 'deb', sudo_present=False, su_present=False)
    assert proc.returncode == 2
    assert 'FAIL: precondition: su is missing in this image' in proc.stdout
    assert not any(c.startswith('apt-get') for c in calls)


def test_an_rpm_image_without_su_gets_util_linux_first(tmp_path):
    calls, proc = _stubbed_run(tmp_path, 'rpm', sudo_present=False, su_present=False)
    assert calls == ['dnf install -y -q util-linux']
    assert proc.returncode == 2 and 'su is missing' in proc.stdout
