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
        tokens = [g.strip() for g in paths.splitlines() if g.strip()]
        # Checksums and Docker digests are the only non-package uploads; anything else could hide a package.
        stray = [t for t in tokens if not t.endswith(('.deb', '.rpm', '.sha256')) and '/digests/' not in t]
        if stray:
            raise AssertionError(f'{name}: uploads {stray} without a .deb/.rpm suffix')
        globs = [t for t in tokens if t.endswith(('.deb', '.rpm'))]
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


@pytest.mark.parametrize('path', ['dist/', 'out', 'dist/*'])
def test_a_job_uploading_a_directory_is_refused(path):
    build = copy.deepcopy(_load('build-release.yml'))
    job = copy.deepcopy(build['jobs']['build-deb'])
    for step in job['steps']:
        if str(step.get('uses', '')).startswith('actions/upload-artifact'):
            step['with']['path'] = path
    build['jobs']['build-deb-dir'] = job
    with pytest.raises(AssertionError, match='build-deb-dir'):
        _built_packages(build)


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


SMOKE_VARS = ('UCM_SMOKE_HOME', 'UCM_SMOKE_ENV_FILE', 'UCM_SMOKE_RUN_DIR', 'UCM_SMOKE_SUDOERS_DIR')


def _assert_sandboxed(env, tmp_path):
    """Refuse to run the script unless every path it writes is under tmp_path."""
    for var in SMOKE_VARS:
        value = env.get(var)
        assert value, f'{var} is not set: the script would use the real default path'
        assert pathlib.Path(value).resolve().is_relative_to(tmp_path.resolve()), \
            f'{var}={value} is outside {tmp_path}'


def _stubbed_run(tmp_path, kind, sudo_present, su_present=True, install_ok=False, env_extra=None,
                 deps_ok=True, safe_mode=False, health_down=False):
    """Run the script against stub commands; returns (ordered command log, completed process).

    Every path variable points under tmp_path and su, chown and the venv interpreter are stubs.
    """
    bin_dir = tmp_path / 'bin'
    bin_dir.mkdir()
    log = tmp_path / 'log'
    home = tmp_path / 'opt-ucm'
    env = {'PATH': f'{bin_dir}', 'UCM_SMOKE_HOME': str(home), 'UCM_SMOKE_ENV_FILE': str(tmp_path / 'ucm.env'),
           'UCM_SMOKE_RUN_DIR': str(tmp_path / 'run'),
           'UCM_SMOKE_SUDOERS_DIR': str(tmp_path / 'sudoers.d'), 'SMOKE_WAIT': '3', 'LOGFILE': str(log)}
    env.update(env_extra or {})
    _assert_sandboxed(env, tmp_path)
    def stub(name, body):
        f = bin_dir / name
        f.write_text('#!/bin/sh\n' + body + '\n')
        f.chmod(0o755)
    for tool in ('tr', 'rm', 'cat', 'tail', 'mkdir', 'sleep', 'date'):
        (bin_dir / tool).symlink_to(shutil.which(tool))  # no host sudo on the PATH
    # kill is a shell builtin: the only pid it can reach is the su stub's own sleep child.
    stub('chown', f'echo "chown $*" >> {log}')
    stub('id', 'echo 0')
    stub('dpkg-deb', 'echo 1.0')
    stub('rpm', 'echo 1.0')
    install_rc = 0 if install_ok else 1
    check_rc = 0 if deps_ok else 1
    stub('apt-get', f'[ "$1" = check ] && exit {check_rc}; echo "apt-get $*" >> {log}; exit {install_rc}')
    stub('dnf', f'[ "$1" = check ] && exit {check_rc}; echo "dnf $*" >> {log}; exit 1')
    stub('dpkg', f'echo "dpkg $*" >> {log}; rm -f {bin_dir}/sudo')
    if sudo_present:
        stub('sudo', 'exit 0')
    if su_present:
        # Success: "start" the app as a sleeping child whose pid lands in the pid file.
        stub('su', f'echo "su $*" >> {log}\n'
             'case "$*" in *gunicorn*) sleep 30 & echo $! > "$UCM_SMOKE_RUN_DIR/pid"; wait;; esac\n'
             f'exit {0 if install_ok else 1}')
    if install_ok:
        (home / 'venv' / 'bin').mkdir(parents=True)
        (home / 'backend').mkdir()
        py = home / 'venv' / 'bin' / 'python'
        py.write_text('#!/bin/sh\n'
                      f'echo "python $*" >> {log}\n'
                      'case "$2" in *urlopen*) ' + ('exit 1' if health_down else '[ -s "$UCM_SMOKE_RUN_DIR/pid" ] || exit 1; echo ok') + ';; '
                      f'*safe_mode*) echo {safe_mode};; *version*) echo 1.0;; esac\n')
        py.chmod(0o755)
        (tmp_path / 'ucm.env').write_text('HTTPS_PORT=18443\n')
    pkg = tmp_path / f'ucm.{kind}'
    pkg.write_text('x')
    proc = subprocess.run(['/bin/sh', str(SCRIPT), str(pkg)], env=env,
                          capture_output=True, text=True, cwd=tmp_path, timeout=60)
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


def test_the_guard_refuses_a_path_outside_tmp_path(tmp_path):
    for var in SMOKE_VARS:
        (tmp_path / var).mkdir()
        with pytest.raises(AssertionError, match=var):
            _stubbed_run(tmp_path / var, 'deb', sudo_present=False, env_extra={var: '/opt/ucm'})
        assert not (tmp_path / var / 'log').exists()


def test_the_guard_refuses_an_unset_path_variable(tmp_path):
    with pytest.raises(AssertionError, match='UCM_SMOKE_RUN_DIR'):
        _assert_sandboxed({'UCM_SMOKE_HOME': str(tmp_path), 'UCM_SMOKE_ENV_FILE': str(tmp_path)}, tmp_path)


def test_a_succeeding_install_stays_under_tmp_path(tmp_path):
    calls, proc = _stubbed_run(tmp_path, 'deb', sudo_present=False, install_ok=True)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert 'package smoke passed' in proc.stdout
    assert any(c.startswith('su ') for c in calls) and any(c.startswith('chown ') for c in calls)
    for line in calls:
        for host in ('/opt/ucm', '/etc/ucm', '/tmp/ucm-'):
            assert host not in line.replace(str(tmp_path), ''), line
    assert (tmp_path / 'run' / 'install.log').exists() and (tmp_path / 'run' / 'app.log').exists()


def test_a_safe_mode_health_answer_fails(tmp_path):
    _, proc = _stubbed_run(tmp_path, 'deb', sudo_present=False, install_ok=True, safe_mode=True)
    assert proc.returncode == 1 and 'safe_mode' in proc.stdout


def test_the_health_wait_is_bounded_by_the_announced_delay(tmp_path):
    import time
    t0 = time.time()
    _, proc = _stubbed_run(tmp_path, 'deb', sudo_present=False, install_ok=True, health_down=True)
    assert time.time() - t0 < 3 + 4  # WAIT=3 plus at most one probe overshoot
    assert 'within 3s' in proc.stdout and proc.returncode == 1


def test_a_sudo_removal_that_breaks_dependencies_is_a_precondition(tmp_path):
    calls, proc = _stubbed_run(tmp_path, 'deb', sudo_present=True, deps_ok=False)
    assert proc.returncode == 2
    assert 'precondition: removing sudo broke package dependencies' in proc.stdout
    assert not any(c.startswith('apt-get') for c in calls)


def test_a_branch_build_does_not_start_the_smoke_jobs():
    jobs = _load('release-smoke.yml')['jobs']
    assert jobs
    for name, job in jobs.items():
        cond = str(job.get('if', ''))
        assert "workflow_dispatch" in cond, name
        assert "startsWith(github.event.workflow_run.head_branch, 'v')" in cond, name
