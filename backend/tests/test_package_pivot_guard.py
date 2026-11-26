"""The 3.0 packages refuse to install over a UCM older than 2.254, before touching a file.

The version test lives in one POSIX file that the DEB and RPM builds embed into
their pre-installation scripts. Every script here runs under a sandbox: a temp
copy, fake dpkg/rpm/mkdir/cp/mv first and alone in PATH, nothing on this host.
"""
import os
import pathlib
import re
import shutil
import subprocess
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[2]
GUARD = ROOT / 'packaging' / 'scripts' / 'pivot-guard.sh'
EMBED = ROOT / 'packaging' / 'scripts' / 'embed-pivot-guard.sh'
PREINST = ROOT / 'packaging' / 'debian' / 'preinst'
SPEC = ROOT / 'packaging' / 'rpm' / 'ucm.spec'
POSIX_SH = shutil.which('dash') or '/bin/sh'
WHAT_TO_DO = 'install 2.254, start it once, then install this package'

REFUSED = ['2.253', '2.253~rc1', '2.200', '1.8.3', '2.253.1', '2.253-1', '1:2.253',
           '2.0.2', '2', 'garbage', '.254', '1.254', '0.300']
ACCEPTED = ['', '2.254', '2.254~rc1', '2.254.rc1', '2.254-1', '2.254.1', '2.254.1~rc1',
            '2.255', '2.1000', '3.0~rc1', '3.0', '3', '10.0', '1:3.0']


def _guard(func, version):
    return subprocess.run([POSIX_SH, '-c', '. "$1"; ' + func + ' "$2"', 'sh', str(GUARD), version],
                          capture_output=True, text=True, timeout=10, env={'PATH': '/nonexistent'})


@pytest.mark.parametrize('version', REFUSED)
def test_an_installed_version_older_than_2_254_is_refused(version):
    out = _guard('ucm_pivot_version_ok', version)
    assert (out.returncode, out.stderr) == (1, '')


@pytest.mark.parametrize('version', ACCEPTED)
def test_2_254_and_later_or_nothing_installed_is_accepted(version):
    out = _guard('ucm_pivot_version_ok', version)
    assert (out.returncode, out.stderr) == (0, '')


def test_the_refusal_names_the_installed_version_and_what_to_do():
    out = _guard('ucm_pivot_guard', '2.253~rc1')
    assert out.returncode == 1
    assert out.stdout == ''
    assert 'UCM 2.253~rc1 is installed' in out.stderr
    assert WHAT_TO_DO in out.stderr.lower()
    assert '—' not in out.stderr and '–' not in out.stderr


def test_an_accepted_version_prints_nothing():
    out = _guard('ucm_pivot_guard', '2.254')
    assert (out.returncode, out.stdout, out.stderr) == (0, '', '')


# -- embedding into the package scripts ---------------------------------------

def _embed(src, tmp_path, name):
    target = tmp_path / name
    shutil.copy(src, target)
    out = subprocess.run([POSIX_SH, str(EMBED), str(target)], capture_output=True, text=True,
                         timeout=10)
    assert out.returncode == 0, out.stderr
    return target


def test_embedding_refuses_a_script_without_its_marker(tmp_path):
    target = tmp_path / 'preinst'
    target.write_text('#!/bin/sh\nexit 0\n')
    out = subprocess.run([POSIX_SH, str(EMBED), str(target)], capture_output=True, text=True,
                         timeout=10)
    assert out.returncode != 0
    assert target.read_text() == '#!/bin/sh\nexit 0\n'


def _fakebin(tmp_path, extra=None):
    """A PATH holding only recorders and the few real tools the scripts read with."""
    bin_dir = tmp_path / 'bin'
    bin_dir.mkdir()
    log = tmp_path / 'calls.log'
    scripts = {
        # Writers: record the call, change nothing
        'mkdir': 'echo "mkdir $*" >> "$LOG"', 'cp': 'echo "cp $*" >> "$LOG"',
        'mv': 'echo "mv $*" >> "$LOG"', 'dd': 'echo "dd $*" >> "$LOG"', 'groupadd': 'echo "groupadd $*" >> "$LOG"',
        'useradd': 'echo "useradd $*" >> "$LOG"',
        'dpkg-query': 'exit 0', 'getent': 'exit 2', 'openssl': 'exit 0',
        'python3': 'echo 3.12',
    }
    scripts.update(extra or {})
    for name, body in scripts.items():
        path = bin_dir / name
        path.write_text(f'#!{POSIX_SH}\n{body}\n')
        path.chmod(0o755)
    for tool in ('cut', 'date'):
        os.symlink(shutil.which(tool), bin_dir / tool)
    env = {'PATH': str(bin_dir), 'LOG': str(log)}
    return env, log


def _calls(log):
    return log.read_text().splitlines() if log.exists() else []


@pytest.fixture
def preinst(tmp_path):
    return _embed(PREINST, tmp_path, 'preinst')


def _run_preinst(script, tmp_path, *args, python='3.12'):
    """Runs the preinst where a log rotation file no package owns exists, so its `mv` is due."""
    rotation = tmp_path / 'logrotate-ucm'
    rotation.write_text('')
    text = script.read_text()
    assert text.count('LOGROTATE_CONF=/etc/logrotate.d/ucm\n') == 1
    sandboxed = tmp_path / 'preinst.sandboxed'
    sandboxed.write_text(text.replace('LOGROTATE_CONF=/etc/logrotate.d/ucm\n',
                                      f'LOGROTATE_CONF={rotation}\n'))
    env, log = _fakebin(tmp_path, {'dpkg-query': 'exit 1', 'python3': f'echo {python}'})
    out = subprocess.run(['/bin/bash', str(sandboxed), *args], capture_output=True, text=True,
                         timeout=20, env=env)
    return out, _calls(log)


@pytest.mark.parametrize('linked', [True, False])
def test_the_deb_preinst_refuses_a_linked_ucm_env_before_copying_it(preinst, tmp_path, linked):
    """/etc/ucm is the account's: a ucm.env it replaced by a link is named, and nothing is read through it."""
    victim = tmp_path / 'shadow'
    victim.write_text('root:*:1::::::\n')
    envfile = tmp_path / 'etc-ucm' / 'ucm.env'
    envfile.parent.mkdir()
    if linked:
        envfile.symlink_to(victim)
    else:
        envfile.write_text('SECRET_KEY=a\n')
    text = preinst.read_text()
    assert text.count('/etc/ucm/ucm.env') == 4, text
    preinst.write_text(text.replace('/etc/ucm/ucm.env', str(envfile)))
    out, calls = _run_preinst(preinst, tmp_path, 'upgrade', '2.254')
    backups = [c for c in calls if c.startswith('dd ')]
    if linked:
        assert out.returncode == 1 and f'{envfile} is a symbolic link or not a regular file' in out.stderr, out.stderr
        assert backups == [], calls
    else:
        assert out.returncode == 0, out.stderr
        assert backups and f'if={envfile}' in backups[0], calls


@pytest.mark.parametrize('args', [('upgrade', '2.253'), ('upgrade', '1.8.3')])
def test_the_deb_preinst_refuses_before_any_write(preinst, tmp_path, args):
    """dpkg passes the installed version as $2."""
    out, calls = _run_preinst(preinst, tmp_path, *args)
    assert out.returncode != 0
    assert WHAT_TO_DO in out.stderr.lower()
    assert calls == []


def test_the_refusal_of_an_upgrade_says_the_old_version_is_still_installed(preinst, tmp_path):
    out, _ = _run_preinst(preinst, tmp_path, 'upgrade', '2.253')
    assert 'UCM 2.253 is installed' in out.stderr
    assert 'Nothing was changed: UCM 2.253 is still installed.' in out.stderr


def test_the_deb_preinst_installs_over_what_a_removed_package_left(preinst, tmp_path):
    """`install <version>`: removed, its configuration files kept; the postinst archives them."""
    out, _ = _run_preinst(preinst, tmp_path, 'install', '2.253')
    assert out.returncode == 0, out.stderr
    assert out.stderr == ''


def test_the_deb_preinst_upgrades_a_2_254(preinst, tmp_path):
    out, calls = _run_preinst(preinst, tmp_path, 'upgrade', '2.254')
    assert out.returncode == 0, out.stderr
    assert calls[0] == f'mv -f {tmp_path}/logrotate-ucm {tmp_path}/logrotate-ucm.dpkg-bak'
    assert 'mkdir -p /var/lib/ucm/backups' in calls


def test_the_deb_preinst_asks_for_the_python_its_control_file_requires(preinst, tmp_path):
    out, _ = _run_preinst(preinst, tmp_path, 'install', python='3.11')
    assert out.returncode != 0
    assert 'Python 3.12 or higher is required (found 3.11)' in out.stderr


@pytest.mark.parametrize('args', [('install',), ('upgrade', '2.254.1~rc1'),
                                  ('abort-upgrade', '2.253')])
def test_the_deb_preinst_accepts_a_new_install_and_an_abort(preinst, tmp_path, args):
    out, _ = _run_preinst(preinst, tmp_path, *args)
    assert out.returncode == 0, out.stderr


def test_a_preinst_built_without_the_guard_fails_every_install(tmp_path):
    """A build that forgets the embedding cannot ship a package that skips the check."""
    shutil.copy(PREINST, tmp_path / 'raw')
    out, calls = _run_preinst(tmp_path / 'raw', tmp_path, 'install')
    assert out.returncode != 0
    assert calls == []


def _pre_section(spec_text):
    m = re.search(r'^%pre\n(.*?)^%post\n', spec_text, re.M | re.S)
    assert m, 'no %pre section'
    return m.group(1)


def _expand(body):
    """The three macros %pre uses, as rpm expands them (checked against rpmspec below)."""
    body = body.replace('%{name}', 'ucm').replace('%{ucm_home}', '/opt/ucm')
    assert not re.search(r'%(?!%)[{A-Za-z]', body.replace('%%', '')), body
    return body.replace('%%', '%')


@pytest.fixture
def rpm_pre(tmp_path):
    return _expand(_pre_section(_embed(SPEC, tmp_path, 'ucm.spec').read_text()))


def _run_pre(body, tmp_path, rpm_body, count='2'):
    env, log = _fakebin(tmp_path, {'rpm': 'printf "rpm %s\\n" "$*" >> "$LOG.rpm"\n' + rpm_body})
    out = subprocess.run([POSIX_SH, '-c', body, 'pre', count], capture_output=True, text=True,
                         timeout=20, env=env)
    return out, _calls(log), _calls(pathlib.Path(env['LOG'] + '.rpm'))


@pytest.mark.parametrize('installed', ['2.253', '2.254\n2.253', '1.8.3'])
def test_the_rpm_pre_refuses_before_creating_the_account(rpm_pre, tmp_path, installed):
    out, calls, queries = _run_pre(rpm_pre, tmp_path, f"printf '{installed}\\n'")
    assert out.returncode != 0
    assert WHAT_TO_DO in out.stderr.lower()
    assert calls == []
    assert queries == ['rpm -q --qf %{VERSION}\\n ucm']


@pytest.mark.parametrize('installed', ['2.254~rc1', '2.254.1'])
def test_the_rpm_pre_upgrades_from_2_254(rpm_pre, tmp_path, installed):
    out, calls, _ = _run_pre(rpm_pre, tmp_path, f"printf '{installed}\\n'")
    assert out.returncode == 0, out.stderr
    assert calls[0].startswith('groupadd -r ucm')


def test_the_rpm_pre_accepts_a_new_install(rpm_pre, tmp_path):
    out, calls, _ = _run_pre(rpm_pre, tmp_path, "echo 'package ucm is not installed'; exit 1",
                             count='1')
    assert out.returncode == 0, out.stderr
    assert calls[0].startswith('groupadd -r ucm')


def test_the_rpm_pre_refuses_an_upgrade_whose_installed_version_it_cannot_read(rpm_pre, tmp_path):
    """$1 is 2 or more on an upgrade: a UCM is installed, whatever rpm -q answered."""
    out, calls, _ = _run_pre(rpm_pre, tmp_path, 'exit 1', count='2')
    assert out.returncode != 0
    assert 'could not be read' in out.stderr
    assert calls == []


def test_a_spec_built_without_the_guard_fails_every_install(tmp_path):
    body = _expand(_pre_section(SPEC.read_text()))
    out, calls, _ = _run_pre(body, tmp_path, 'exit 1', count='1')
    assert out.returncode != 0
    assert calls == []


@pytest.mark.skipif(not shutil.which('rpmspec'), reason='rpmspec is not installed')
def test_rpm_expands_the_embedded_guard_as_the_sandbox_does(tmp_path, rpm_pre):
    spec = _embed(SPEC, tmp_path, 'ucm.spec')
    out = subprocess.run(['rpmspec', '-P', str(spec)], capture_output=True, text=True,
                         timeout=30)
    assert out.returncode == 0, out.stderr
    assert _pre_section(out.stdout).strip() == rpm_pre.strip()


def test_every_package_build_embeds_the_guard():
    """dh_installdeb writes DEBIAN/preinst; both RPM builders copy the spec before rpmbuild."""
    rules = subprocess.run(['make', '-n', '-f', 'packaging/debian/rules', 'override_dh_installdeb'],
                           cwd=ROOT, capture_output=True, text=True, timeout=10)
    assert rules.returncode == 0, rules.stderr
    lines = rules.stdout.splitlines()
    assert lines[0].startswith('dh_installdeb')
    assert any('embed-pivot-guard.sh debian/ucm/DEBIAN/preinst' in line for line in lines[1:])
    for builder in ('.github/workflows/build-release.yml', 'packaging/scripts/build-rpm.sh'):
        text = (ROOT / builder).read_text()
        spec_ready = text.index('rpmbuild -bb')
        assert re.search(r'embed-pivot-guard\.sh\S*\s+\S*spec', text[:spec_ready], re.I), builder


def test_no_package_or_image_runs_the_1_x_upgrade_any_more():
    """A 1.x goes through 2.254, whose packages still carry its upgrade; 3.0 has none."""
    assert not (ROOT / 'backend' / 'migrate_v1_to_v2.py').exists()
    found = []
    for top in ('packaging', 'docker', 'backend', '.github', 'scripts', 'charts'):
        for path in (ROOT / top).rglob('*'):
            parts = path.relative_to(ROOT).parts
            if not path.is_file() or 'tests' in parts or '__pycache__' in parts:
                continue
            text = path.read_text(errors='ignore')
            if re.search(r'migrate_v1_to_v2|V1_DB\b|v1\.8\.x', text):
                found.append(str(path.relative_to(ROOT)))
    for name in ('Dockerfile', 'Dockerfile.fips'):
        if (ROOT / name).exists() and 'migrate_v1_to_v2' in (ROOT / name).read_text():
            found.append(name)
    assert found == []


# -- the post-installation scripts archive what a removed UCM left -------------------

POSTINST = ROOT / 'packaging' / 'debian' / 'postinst'
ARCHIVER = 'archive-leftovers.sh'


def _post_sandbox(tmp_path, archive_rc):
    """Paths moved under tmp_path; every command that writes outside it is a recorder."""
    home, data, config = tmp_path / 'opt' / 'ucm', tmp_path / 'opt' / 'ucm' / 'data', tmp_path / 'etc' / 'ucm'
    (home / 'scripts').mkdir(parents=True)
    data.mkdir()
    config.mkdir(parents=True)
    shutil.copy(GUARD, home / 'scripts' / 'pivot-guard.sh')
    record = 'echo "$(basename "$0") $*" >> "$LOG"'
    fakes = {name: record for name in ('mkdir', 'chown', 'chmod', 'rm', 'addgroup', 'adduser',
                                        'usermod', 'groupadd', 'useradd', 'openssl')}
    fakes.update({
        'getent': 'case "$1 $2" in "group softhsm"|"group ods") exit 2 ;; esac; exit 0',
        'systemctl': record + '\n[ "$1" != is-active ]',
        # fips-requested answers from the file, as native-setup.sh does
        'bash': record + '\n[ "$2" != fips-requested ] || grep -qx "UCM_FIPS_BUILD=1" "$3"',
        # The archiver's answer, or the scriptlet killed while it runs; whether the
        # configuration existed when it ran
        # The archiver is called with the interpreter it renames with
        'sh': record.replace('$*', '${UCM_RETRY:+UCM_RETRY=$UCM_RETRY }${UCM_PYTHON:+UCM_PYTHON=$UCM_PYTHON }$*') + f'\n[ -e "{config}/ucm.env" ] && echo "sh saw ucm.env" >> "$LOG"\n'
              + {'kill': 'kill -9 $PPID; sleep 5',
                 # Puts back an archived ucm.env, archives it, carries UCM_FIPS_BUILD=1 over
                 'fips': f'printf "UCM_FIPS_BUILD=1\\n" > "{config}/ucm.env"'}.get(
                     archive_rc, f'exit {archive_rc}'),
        'python3': 'echo 00', 'hostname': 'echo host',
    })
    bin_dir = tmp_path / 'bin'
    bin_dir.mkdir()
    for name, body in fakes.items():
        (bin_dir / name).write_text(f'#!{POSIX_SH}\n{body}\n')
        (bin_dir / name).chmod(0o755)
    for tool in ('cat', 'grep', 'basename', 'dirname', 'find'):
        os.symlink(shutil.which(tool), bin_dir / tool)
    log = tmp_path / 'calls.log'
    return {'PATH': str(bin_dir), 'LOG': str(log)}, log, home, data, config


def _paths(text, home, data, config, quoted):
    q = '"' if quoted else ''
    for name, value, path in (('UCM_HOME', '/opt/ucm', home), ('UCM_DATA', '/opt/ucm/data', data),
                              ('UCM_CONFIG', '/etc/ucm', config)):
        line = f'{name}={q}{value}{q}\n'
        assert text.count(line) == 1, line
        text = text.replace(line, f'{name}={q}{path}{q}\n')
    return text


def _run_postinst(tmp_path, *args, archive_rc=0):
    env, log, home, data, config = _post_sandbox(tmp_path, archive_rc)
    script = tmp_path / 'postinst.sandboxed'
    script.write_text(_paths(POSTINST.read_text(), home, data, config, quoted=True))
    out = subprocess.run(['/bin/bash', str(script), *args], capture_output=True, text=True,
                         timeout=20, env=env)
    return out, _calls(log), home, data, config


def _post_body(tmp_path, home, data, config):
    m = re.search(r'^%post\n(.*?)^%preun\n', SPEC.read_text(), re.M | re.S)
    assert m, 'no %post section'
    body = m.group(1)
    assert body.count('%systemd_post %{name}.service\n') == 1
    body = body.replace('%systemd_post %{name}.service\n', ': systemd_post\n')
    body = body.replace('%{ucm_data}', '/opt/ucm/data').replace('%{ucm_python}', 'python3')
    body = _expand(body)
    return _paths(body, home, data, config, quoted=False)


def _run_post(tmp_path, count, archive_rc=0):
    env, log, home, data, config = _post_sandbox(tmp_path, archive_rc)
    body = _post_body(tmp_path, home, data, config)
    out = subprocess.run([POSIX_SH, '-c', body, 'post', count], capture_output=True, text=True,
                         timeout=20, env=env)
    return out, _calls(log), home, data, config


def _archiver_calls(calls):
    return [c for c in calls if c.startswith('sh ') and ARCHIVER in c]


def _check_order(calls, home, data, config):
    """After the venv is built, before the data directories and the configuration are written."""
    archive = calls.index(_archiver_calls(calls)[0])
    venv = next(i for i, c in enumerate(calls) if c.startswith('bash ') and ' venv ' in f'{c} ')
    first_data = next(i for i, c in enumerate(calls) if c.startswith('mkdir') and str(data) in c)
    assert venv < archive < first_data
    assert 'sh saw ucm.env' not in calls
    assert [c.split(' UCM_PYTHON=')[1] for c in _archiver_calls(calls)] == [
        f'python3 {home}/scripts/{ARCHIVER} {home} {data} {config}']


@pytest.mark.parametrize('previous', ['', '2.253', '1.8.3'])
def test_the_deb_postinst_archives_on_a_new_install(tmp_path, previous):
    """Nothing configured, or a removed version older than 2.254 that no upgrade reaches."""
    out, calls, home, data, config = _run_postinst(tmp_path, 'configure', previous)
    assert out.returncode == 0, out.stderr
    _check_order(calls, home, data, config)
    assert 'systemctl start ucm' in calls


@pytest.mark.parametrize('previous', ['2.254', '2.254.1', '3.0~rc1', '3.0'])
def test_the_deb_postinst_never_archives_on_an_upgrade_or_a_reconfigure(tmp_path, previous):
    out, calls, *_ = _run_postinst(tmp_path, 'configure', previous)
    assert out.returncode == 0, out.stderr
    assert _archiver_calls(calls) == []
    assert 'systemctl start ucm' in calls


def _started_after_a_reset(calls):
    """An install's start is wanted: the start limit, meant for crashes, is reset first."""
    systemctl = [c for c in calls if c.startswith('systemctl ') and ' ucm' in f'{c} ' and 'watcher' not in c]
    start = systemctl.index('systemctl start ucm')
    assert 'systemctl reset-failed ucm' in systemctl[:start], systemctl


def test_the_deb_postinst_resets_the_start_limit_before_it_starts_the_service(tmp_path):
    out, calls, *_ = _run_postinst(tmp_path, 'configure', '2.254')
    assert out.returncode == 0, out.stderr
    _started_after_a_reset(calls)


def test_the_rpm_post_resets_the_start_limit_before_it_starts_the_service(tmp_path):
    out, calls, *_ = _run_post(tmp_path, '2')
    assert out.returncode == 0, out.stderr
    _started_after_a_reset(calls)


PENDING = '.leftover-archive-pending'


def _stopped_at_the_archiver(out, calls, home, data, config, retry, archive_rc):
    """A failed archiving ends the script: no call after it, nothing in the data or the
    configuration, no banner, the next run told to archive again, and the retry named: by
    the archiver on 1 and 2, before the line it ends with; by the script on another code."""
    assert out.returncode != 0
    archive = calls.index(_archiver_calls(calls)[0])
    assert calls[archive + 1:] == []
    assert list(data.iterdir()) == [] and list(config.iterdir()) == []
    assert 'INSTALLED' not in out.stdout
    assert calls[archive].startswith(f'sh UCM_RETRY={retry} UCM_PYTHON=')
    said = f'UCM was not set up. Fix the cause, then run: {retry}'
    assert (said in out.stdout) is (archive_rc not in (1, 2)), out.stdout
    assert archive_rc in (1, 2) or out.stdout.splitlines()[-1] == said, out.stdout
    assert (home / PENDING).exists()


@pytest.mark.parametrize('archive_rc', [1, 2, 127])
def test_the_deb_postinst_stops_when_archiving_failed(tmp_path, archive_rc):
    out, calls, home, data, config = _run_postinst(tmp_path, 'configure', '', archive_rc=archive_rc)
    _stopped_at_the_archiver(out, calls, home, data, config, 'dpkg --configure -a', archive_rc)


@pytest.mark.parametrize('previous', ['', '3.0'])
def test_the_deb_postinst_archives_again_after_a_failed_attempt(tmp_path, previous):
    """The pending mark is honoured whatever dpkg passes, and cleared once archiving worked."""
    env, log, home, data, config = _post_sandbox(tmp_path, 0)
    (home / PENDING).write_text('')
    script = tmp_path / 'postinst.sandboxed'
    script.write_text(_paths(POSTINST.read_text(), home, data, config, quoted=True))
    out = subprocess.run(['/bin/bash', str(script), 'configure', previous], capture_output=True,
                         text=True, timeout=20, env=env)
    calls = _calls(log)
    assert out.returncode == 0, out.stderr
    _check_order(calls, home, data, config)
    assert f'rm -f {home}/{PENDING}' in calls
    assert 'systemctl start ucm' in calls


def test_the_rpm_post_archives_on_a_new_install_only(tmp_path):
    out, calls, home, data, config = _run_post(tmp_path / 'new', '1')
    assert out.returncode == 0, out.stderr
    _check_order(calls, home, data, config)
    assert 'systemctl start ucm' in calls
    out, calls, *_ = _run_post(tmp_path / 'upgrade', '2')
    assert out.returncode == 0, out.stderr
    assert _archiver_calls(calls) == []


@pytest.mark.parametrize('archive_rc', [1, 2, 127])
def test_the_rpm_post_stops_when_archiving_failed(tmp_path, archive_rc):
    out, calls, home, data, config = _run_post(tmp_path, '1', archive_rc=archive_rc)
    _stopped_at_the_archiver(out, calls, home, data, config, 'dnf reinstall ucm', archive_rc)


def test_the_rpm_post_archives_again_on_the_reinstall_after_a_failed_attempt(tmp_path):
    """dnf reinstall runs %post with $1 = 2: the pending mark, not $1, asks for the archiving."""
    env, log, home, data, config = _post_sandbox(tmp_path, 0)
    (home / PENDING).write_text('')
    body = _post_body(tmp_path, home, data, config)
    out = subprocess.run([POSIX_SH, '-c', body, 'post', '2'], capture_output=True, text=True,
                         timeout=20, env=env)
    calls = _calls(log)
    assert out.returncode == 0, out.stderr
    _check_order(calls, home, data, config)
    assert f'rm -f {home}/{PENDING}' in calls
    assert 'systemctl start ucm' in calls


def test_the_rpm_post_marks_a_new_install_before_the_venv_is_built(tmp_path):
    """A UCM_FIPS_BUILD=1 build that fails stops %post before the archiver: the mark set
    first makes the reinstall ($1 = 2) archive, where $1 alone would skip it."""
    env, log, home, data, config = _post_sandbox(tmp_path, 0)
    (config / 'ucm.env').write_text('UCM_FIPS_BUILD=1\n')
    works = tmp_path / 'venv-works'
    (tmp_path / 'bin' / 'bash').write_text(
        f'#!{POSIX_SH}\necho "$(basename "$0") $*" >> "$LOG"\ncase $2 in\n'
        f'    fips-requested) grep -qx "UCM_FIPS_BUILD=1" "$3" ;;\n    venv) [ -e "{works}" ] ;;\nesac\n')
    body = _post_body(tmp_path, home, data, config)
    out = subprocess.run([POSIX_SH, '-c', body, 'post', '1'], capture_output=True, text=True,
                         timeout=20, env=env)
    assert out.returncode == 1, (out.stdout, out.stderr)
    assert _archiver_calls(_calls(log)) == []
    assert (home / PENDING).exists()
    works.write_text('')
    log.unlink()
    out = subprocess.run([POSIX_SH, '-c', body, 'post', '2'], capture_output=True, text=True,
                         timeout=20, env=env)
    assert out.returncode == 0, (out.stdout, out.stderr)
    assert len(_archiver_calls(_calls(log))) == 1


def test_the_rpm_post_marks_a_new_install_before_anything_else(tmp_path):
    """A %post killed at %systemd_post, its first command after the mark, leaves the mark."""
    env, log, home, data, config = _post_sandbox(tmp_path, 0)
    body = _post_body(tmp_path, home, data, config)
    assert body.count(': systemd_post\n') == 1
    body = body.replace(': systemd_post\n', 'kill -9 $$\n')
    out = subprocess.run([POSIX_SH, '-c', body, 'post', '1'], capture_output=True, text=True,
                         timeout=20, env=env)
    assert out.returncode == -9
    assert (home / PENDING).exists()


@pytest.mark.parametrize('count, kept', [('0', False), ('1', True)])
def test_the_rpm_postun_drops_the_mark_on_erase_only(tmp_path, count, kept):
    m = re.search(r'^%postun\n(.*?)^%files\n', SPEC.read_text(), re.M | re.S)
    assert m, 'no %postun section'
    body = m.group(1)
    macro = '%systemd_postun_with_restart %{name}.service\n'
    assert body.count(macro) == 1
    body = _expand(body.replace(macro, ': systemd_postun\n'))
    home = tmp_path / 'opt' / 'ucm'
    home.mkdir(parents=True)
    (home / PENDING).write_text('')
    assert body.count('/opt/ucm') == 1
    body = body.replace('/opt/ucm', str(home))
    out = subprocess.run([POSIX_SH, '-c', body, 'postun', count], capture_output=True, text=True,
                         timeout=20)
    assert out.returncode == 0, out.stderr
    assert (home / PENDING).exists() is kept


def test_both_packages_ship_the_archiver_and_the_deb_its_guard():
    rules = subprocess.run(['make', '-n', '-f', 'packaging/debian/rules', 'override_dh_auto_install'],
                           cwd=ROOT, capture_output=True, text=True, timeout=10)
    assert rules.returncode == 0, rules.stderr
    for name in (ARCHIVER, 'pivot-guard.sh'):
        assert f'packaging/scripts/{name} debian/ucm/opt/ucm/scripts/' in rules.stdout
    assert f'packaging/scripts/{ARCHIVER} %{{buildroot}}%{{ucm_home}}/scripts/' in SPEC.read_text()


@pytest.mark.parametrize('package, first', [('deb', ''), ('deb', '2.253'), ('rpm', '1')])
def test_a_scriptlet_killed_while_archiving_leaves_the_mark_for_the_retry(tmp_path, package, first):
    """The pending mark is set before the archiver runs: a scriptlet killed during it
    leaves the mark, so a retry whose $1/$2 alone would skip it archives again (below)."""
    env, log, home, data, config = _post_sandbox(tmp_path, 'kill')
    if package == 'deb':
        script = tmp_path / 'postinst.sandboxed'
        script.write_text(_paths(POSTINST.read_text(), home, data, config, quoted=True))
        cmd = ['/bin/bash', str(script), 'configure', first]
    else:
        cmd = [POSIX_SH, '-c', _post_body(tmp_path, home, data, config), 'post', first]
    out = subprocess.run(cmd, capture_output=True, text=True, timeout=20, env=env)
    calls = _calls(log)
    assert out.returncode != 0
    assert _archiver_calls(calls) == calls[-1:]
    assert (home / PENDING).exists()
    assert list(data.iterdir()) == [] and list(config.iterdir()) == []

@pytest.mark.parametrize('package, retry', [('deb', '3.0'), ('rpm', '2')])
@pytest.mark.parametrize('left', ['mark', 'journal'])
def test_a_retry_archives_while_a_mark_or_a_journal_is_left(tmp_path, package, retry, left):
    """Either one is enough: a journal without the mark (a run killed before 3.0 set it,
    or the mark removed by a purge) still sends the retry through the archiver."""
    env, log, home, data, config = _post_sandbox(tmp_path, 0)
    if left == 'mark':
        (home / PENDING).write_text('')
    else:
        journal = home.parent / 'ucm-archive' / '20261114T120000Z' / '.journal'
        journal.parent.mkdir(parents=True)
        journal.write_text('')
    if package == 'deb':
        script = tmp_path / 'postinst.sandboxed'
        script.write_text(_paths(POSTINST.read_text(), home, data, config, quoted=True))
        cmd = ['/bin/bash', str(script), 'configure', retry]
    else:
        cmd = [POSIX_SH, '-c', _post_body(tmp_path, home, data, config), 'post', retry]
    out = subprocess.run(cmd, capture_output=True, text=True, timeout=20, env=env)
    calls = _calls(log)
    assert out.returncode == 0, out.stderr
    _check_order(calls, home, data, config)
    assert f'rm -f {home}/{PENDING}' in calls


@pytest.mark.parametrize('package', ['deb', 'rpm'])
@pytest.mark.parametrize('archive_rc, banner', [(0, True), (3, False)])
def test_no_success_banner_after_a_database_left_for_the_service_to_refuse(tmp_path, package,
                                                                          archive_rc, banner):
    """3: the archiver said the service will refuse the database it left; the install goes
    on as before, but never ends on "UCM INSTALLED", and no retry is asked for."""
    if package == 'deb':
        out, calls, home, *_ = _run_postinst(tmp_path, 'configure', '', archive_rc=archive_rc)
    else:
        out, calls, home, *_ = _run_post(tmp_path, '1', archive_rc=archive_rc)
    assert out.returncode == 0, out.stderr
    assert any(' banner ' in c for c in calls if c.startswith('bash ')) is banner
    assert f'rm -f {home}/{PENDING}' in calls
    assert 'not set up' not in out.stdout


@pytest.mark.parametrize('package', ['deb', 'rpm'])
@pytest.mark.parametrize('before', [False, True])
def test_a_venv_built_before_fips_came_back_is_built_again(tmp_path, package, before):
    """A retry whose ucm.env was still in the archive built a standard venv; the archiver
    then wrote UCM_FIPS_BUILD=1 into the new ucm.env: the venv is built again, once."""
    env, log, home, data, config = _post_sandbox(tmp_path, 'fips')
    if before:
        (config / 'ucm.env').write_text('UCM_FIPS_BUILD=1\n')
    if package == 'deb':
        script = tmp_path / 'postinst.sandboxed'
        script.write_text(_paths(POSTINST.read_text(), home, data, config, quoted=True))
        cmd = ['/bin/bash', str(script), 'configure', '']
    else:
        cmd = [POSIX_SH, '-c', _post_body(tmp_path, home, data, config), 'post', '1']
    out = subprocess.run(cmd, capture_output=True, text=True, timeout=20, env=env)
    calls = _calls(log)
    assert out.returncode == 0, out.stderr
    venvs = [i for i, c in enumerate(calls) if c.startswith('bash ') and ' venv ' in f'{c} ']
    archiver = calls.index(_archiver_calls(calls)[0])
    if before:
        assert len(venvs) == 1 and 'came back' not in out.stdout
    else:
        assert len(venvs) == 2 and venvs[0] < archiver < venvs[1]
        assert 'building it again against the system OpenSSL' in out.stdout


@pytest.mark.parametrize('package', ['deb', 'rpm'])
def test_the_ownership_given_to_the_service_never_reaches_a_local_archive(tmp_path, package):
    """The archiver leaves what it could not rename out of its filesystem in .ucm-archive-*
    directories of the data and the configuration, root's: the chown that gives the rest to
    the service account passes them by, and still reaches everything else."""
    env, log, home, data, config = _post_sandbox(tmp_path, 0)
    for top in (data, data / 'ca', config):
        (top / '.ucm-archive-20261114T120000Z' / 'old').mkdir(parents=True)
        (top / '.ucm-archive-20261114T120000Z' / 'old' / 'leaf.key').write_text('key')
    (data / 'ca' / 'kept.pem').write_text('pem')
    (config / 'kept.env').write_text('x')
    (home / 'backend' / 'data').mkdir(parents=True)
    if package == 'deb':
        script = tmp_path / 'postinst.sandboxed'
        script.write_text(_paths(POSTINST.read_text(), home, data, config, quoted=True))
        cmd = ['/bin/bash', str(script), 'configure', '2.254']
    else:
        cmd = [POSIX_SH, '-c', _post_body(tmp_path, home, data, config), 'post', '2']
    out = subprocess.run(cmd, capture_output=True, text=True, timeout=20, env=env)
    assert out.returncode == 0, out.stderr
    # own chown-tree passes .ucm-archive-* by (tests/test_native_setup_script.py); the starting
    # points end in /: a data or configuration directory behind a link is reached
    setup = f'bash {home}/scripts/native-setup.sh own chown-tree'
    trees = [c for c in _calls(log) if c.startswith(setup)]
    # The home and all that root runs from it are root's: only what the service writes (the data,
    # the older backend/data its unit still lists) is given to the account
    assert trees == [f'{setup} {home}/ root:root data backend/data', f'{setup} {data}/ ucm:ucm',
                     f'{setup} {home}/backend/data ucm:ucm', f'{setup} {config}/ ucm:ucm dns-hooks',
                     f'{setup} /var/log/ucm/ ucm:ucm'], trees
    assert not [c for c in _calls(log) if c.startswith('chown ')], _calls(log)


POSTRM = ROOT / 'packaging' / 'debian' / 'postrm'


def _postrm_with(tmp_path, action, lay, lib=None, logs=None, real=(), tools=None):
    """_postrm, with `lay(home, config)` run on the sandbox before the script; /var/lib/ucm
    and /var/log/ucm become `lib` and `logs` (by default absent paths of the sandbox);
    the tools named in `real` run for real instead of being recorded, `tools` maps a name
    to a script body that replaces it last."""
    env, log, home, _data, config = _post_sandbox(tmp_path, 0)
    lay(home, config)
    for tool in (*real, 'python3'):
        (pathlib.Path(env['PATH']) / tool).unlink(missing_ok=True)
        os.symlink(shutil.which(tool), pathlib.Path(env['PATH']) / tool)
    (bin_rm := pathlib.Path(env['PATH']) / 'rm').write_text(
        f'#!{POSIX_SH}\necho "rm $*" >> "$LOG"\nexec {shutil.which("rm")} "$@"\n')
    bin_rm.chmod(0o755)
    for name, body in (tools or {}).items():
        (pathlib.Path(env['PATH']) / name).unlink(missing_ok=True)
        (pathlib.Path(env['PATH']) / name).write_text(f'#!{POSIX_SH}\n{body}\n')
        (pathlib.Path(env['PATH']) / name).chmod(0o755)
    for tool in ('sort', 'sed', 'rmdir', 'dd'):
        os.symlink(shutil.which(tool), pathlib.Path(env['PATH']) / tool)
    text = POSTRM.read_text()
    for line, path in (('UCM_HOME=/opt/ucm\n', home), ('UCM_CONFIG=/etc/ucm\n', config)):
        assert text.count(line) == 1, line
        text = text.replace(line, f'{line.split("=")[0]}={path}\n')
    for real, path in (('/var/lib/ucm', lib or tmp_path / 'var' / 'lib' / 'ucm'),
                       ('/var/log/ucm', logs or tmp_path / 'var' / 'log' / 'ucm')):
        text = text.replace(real, str(path))
    # No path of this machine is left for the script to remove
    assert not re.search(r'(?<![\w.-])/(var|etc|opt|srv|usr)/', text), text
    script = tmp_path / 'postrm.sandboxed'
    script.write_text(text)
    out = subprocess.run(['/bin/bash', str(script), action], capture_output=True, text=True,
                         timeout=20, env=env)
    assert out.returncode == 0, out.stderr
    return out, log, home, config


@pytest.mark.parametrize('action, removed', [('purge', True), ('remove', False)])
def test_a_purge_removes_the_pending_mark(tmp_path, action, removed):
    """The mark is no package file: dpkg leaves it, the purge takes it (a journal left in
    the archive still sends the next install through the archiver)."""
    out, log, home, config = _postrm_with(tmp_path, action, lambda home, config: (home / PENDING).write_text(''))
    assert (home / PENDING).exists() is not removed
    # Without a local archive the configuration goes whole, and only on a purge
    assert config.exists() is not removed
    assert all(c in (f'rm -f {home}/{PENDING}', f'rm -rf {config}') for c in _calls(log) if c.startswith('rm '))


def test_a_purge_keeps_a_local_archive_the_archiver_left_under_var_lib_ucm(tmp_path):
    """DATABASE_PATH of the older packages placed the database in /var/lib/ucm: on another
    filesystem it is archived beside itself, and the purge, which removes that directory,
    leaves that archive as its README says."""
    from tests.test_package_leftover_archive import LOCAL, Box
    box = Box(tmp_path / 'box')
    lib = box.tmp / 'var' / 'lib' / 'ucm'
    lib.mkdir(parents=True)
    shutil.move(box.data / 'ucm.db', lib / 'ucm.db')
    (lib / 'stale.pid').write_text('1')
    env_file = box.config / 'ucm.env'
    env_file.write_text(env_file.read_text().replace(f'{box.data}/ucm.db', f'{lib}/ucm.db'))
    db = (lib / 'ucm.db').read_bytes()
    box.wrap(other_fs=(lib,))
    out = box.run()
    assert out.returncode == 0, out.stdout + out.stderr
    kept = lib / LOCAL
    assert (kept / 'ucm.db').read_bytes() == db
    assert 'leaves them where they are' in (box.archive / 'README.txt').read_text()

    out, log, _home, _config = _postrm_with(tmp_path / 'pkg', 'purge', lambda home, config: None, lib=lib)
    assert (kept / 'ucm.db').read_bytes() == db
    assert not (lib / 'stale.pid').exists()
    assert f'  {kept}' in out.stdout.splitlines()


def _tree(root):
    return sorted((str(p.relative_to(root)), p.read_bytes() if p.is_file() else None, oct(p.lstat().st_mode))
                  for p in root.rglob('*'))


def test_a_purge_keeps_the_local_archives_of_an_earlier_installation(tmp_path):
    """They hold that installation's keys: the purge removes the configuration around
    them, names them, and leaves each one as it was, an empty directory inside included."""
    def lay(home, config):
        (config / 'ucm.env').write_text('new')
        (config / 'conf.d').mkdir()
        (config / 'conf.d' / 'extra').write_text('new')
        (config / 'ssl').mkdir()
        (config / 'ssl' / 'cert.pem').write_text('new')
        for where in (config, config / 'ssl'):
            kept = where / '.ucm-archive-20260101T000000Z'
            (kept / 'empty').mkdir(parents=True)
            (kept / 'master.key').write_text('old key')
            kept.chmod(0o700)
    out, log, home, config = _postrm_with(tmp_path, 'purge', lay)
    kept = [config / '.ucm-archive-20260101T000000Z', config / 'ssl' / '.ucm-archive-20260101T000000Z']
    for k in kept:
        assert [n for n, *_ in _tree(k)] == ['empty', 'master.key'], k
        assert (k / 'master.key').read_text() == 'old key' and (k / 'empty').is_dir()
        assert oct(k.stat().st_mode & 0o777) == '0o700'
        assert f'  {k}' in out.stdout.splitlines()
    # Nothing else is left, and no directory but those that hold an archive
    assert sorted(str(p.relative_to(config)) for p in config.rglob('*') if not any(
        part.startswith('.ucm-archive-') for part in p.relative_to(config).parts)) == ['ssl']
    assert f'chown root:root {config}' in _calls(log) and f'chmod 700 {config}' in _calls(log)
    assert not any(c.startswith('rm -rf ') for c in _calls(log)), _calls(log)
    assert not any('.ucm-archive-' in c for c in _calls(log) if c.startswith('rm ')), _calls(log)


def test_a_directory_swapped_for_a_link_during_the_purge_is_never_entered(tmp_path):
    """/etc/ucm is the account's: a directory of it swapped for a link to a root directory while
    the purge empties it must cost that directory nothing, whatever removes the files."""
    victim = tmp_path / 'victim'
    victim.mkdir()
    for name in ('a.conf', 'b.conf'):
        (victim / name).write_text('root\n')
    sub = tmp_path.resolve() / 'etc' / 'ucm' / 'sub'

    def lay(home, config):
        (config / '.ucm-archive-20260101T000000Z').mkdir()
        (config / '.ucm-archive-20260101T000000Z' / 'master.key').write_text('old key')
        sub.mkdir()
        for name in ('a.conf', 'b.conf'):
            (sub / name).write_text('account\n')
    swap = f'mv {sub} {sub}.moved; ln -s {victim} {sub}'
    # The swap lands right before the first removal inside sub, by path (rm) or by descriptor (python)
    prelude = (f"import os\n_unlink = os.unlink\n_swapped = []\n"
               f"def _racing(name, *a, dir_fd=None, **k):\n"
               f"    at = os.readlink('/proc/self/fd/%d' % dir_fd) if dir_fd is not None else os.path.dirname(name)\n"
               f"    if not _swapped and at == '{sub}':\n"
               f"        _swapped.append(1); os.rename('{sub}', '{sub}.moved'); os.symlink('{victim}', '{sub}')\n"
               f"    return _unlink(name, *a, dir_fd=dir_fd, **k)\n"
               f"os.unlink = _racing\nos.remove = _racing\n")
    tools = {
        'rm': f'case "$*" in *{sub}/*) [ -L {sub} ] || {{ {swap}; }};; esac\nexec {shutil.which("rm")} "$@"',
        'python3': f'[ "$2" = -c ] || exec {sys.executable} "$@"\ncode=$3; shift 3\nexec {sys.executable} -I -c "{prelude}$code" "$@"',
    }
    out, _log, _home, config = _postrm_with(tmp_path, 'purge', lay, real=('mv', 'ln'), tools=tools)
    assert sorted(p.name for p in victim.iterdir()) == ['a.conf', 'b.conf']
    assert all((victim / n).read_text() == 'root\n' for n in ('a.conf', 'b.conf'))
    assert (config / '.ucm-archive-20260101T000000Z' / 'master.key').read_text() == 'old key'
    # The race was run: the directory emptied is the one moved away, the link went with the purge
    assert (sub.parent / 'sub.moved').is_dir() and not list((sub.parent / 'sub.moved').iterdir())


def test_a_removal_says_where_the_data_stays_and_what_a_purge_keeps(tmp_path):
    """The data of this release is under the home; no removal is advised beyond the purge,
    which keeps what an earlier installation left in its local archives."""
    out, _log, home, config = _postrm_with(tmp_path, 'remove', lambda home, config: None)
    assert f'Data preserved in {home}/data, configuration in {config}' in out.stdout, out.stdout
    assert 'apt purge ucm' in out.stdout and '.ucm-archive-* directories' in out.stdout, out.stdout
    assert 'rm -rf' not in out.stdout, out.stdout


KEY_TOOLS = ('mkdir', 'mv', 'date')


def _lay_key(data_file=None, env_text='UCM_FQDN=x\n'):
    def lay(home, config):
        (config / 'master.key').write_bytes(b'k' * 32)
        (config / 'ucm.env').write_text(env_text)
        (config / 'audit-chain.keys').write_text('{}')
        if data_file:
            (home / 'data' / data_file).write_bytes(b'SQLite format 3\x00')
    return lay


@pytest.mark.parametrize('data_file, env_text', [
    ('ucm.db', 'UCM_FQDN=x\n'),
    # PostgreSQL: the data outlives the purge outside the machine
    (None, 'export DATABASE_URL="postgresql://u:p@db/ucm"\n'),
])
def test_a_purge_that_keeps_data_keeps_its_master_key_root_only(tmp_path, data_file, env_text):
    """The key encrypts the private keys of the data the purge leaves: it and ucm.env move
    to a root-only archive beside the home, named in the output, before /etc/ucm goes."""
    out, log, home, config = _postrm_with(tmp_path, 'purge', _lay_key(data_file, env_text),
                                          real=KEY_TOOLS)
    kept = list((home.parent / 'ucm-archive').glob('*-purge'))
    assert len(kept) == 1, (kept, out.stderr)
    assert re.fullmatch(r'\d{8}T\d{6}Z-purge', kept[0].name), kept[0].name
    assert (kept[0] / 'master.key').read_bytes() == b'k' * 32
    assert (kept[0] / 'ucm.env').read_text() == env_text
    assert (kept[0] / 'audit-chain.keys').read_text() == '{}'
    assert not config.exists()
    calls = _calls(log)
    assert f'chown -R root:root {kept[0]}' in calls and f'chmod -R go= {kept[0]}' in calls, calls
    assert calls.index(f'chmod -R go= {kept[0]}') < calls.index(f'rm -rf {config}')
    assert f'  {kept[0]}' in out.stdout.splitlines(), out.stdout
    assert 'master.key' in out.stdout


def test_a_purge_names_only_the_files_it_kept(tmp_path):
    """No audit-chain.keys in the configuration: the output never says it was kept."""
    def lay(home, config):
        _lay_key('ucm.db')(home, config)
        (config / 'audit-chain.keys').unlink()
    out, _log, home, _config = _postrm_with(tmp_path, 'purge', lay, real=KEY_TOOLS)
    kept = next((home.parent / 'ucm-archive').glob('*-purge'))
    assert sorted(p.name for p in kept.iterdir()) == ['master.key', 'ucm.env']
    assert 'audit-chain.keys' not in out.stdout, out.stdout
    assert 'Kept: master.key, ucm.env,' in out.stdout, out.stdout


def test_a_purge_says_how_to_restore_the_kept_keys(tmp_path):
    # postinst starts UCM: the keys go back before the install, with the archived settings
    out, _log, _home, config = _postrm_with(tmp_path, 'purge', _lay_key('ucm.db'), real=KEY_TOOLS)
    text = ' '.join(out.stdout.split())
    assert 'before apt install ucm' in text and f'master.key and audit-chain.keys back into {config}' in text, text
    assert 'chown ucm:ucm' in text and 'chmod 600' in text and 'systemctl restart ucm' in text, text
    assert 'DATABASE_URL and KEY_ENCRYPTION_KEY' in text, text


def test_a_purge_without_data_removes_the_key_with_the_configuration(tmp_path):
    """Nothing kept needs the key: the configuration goes whole, no archive is made."""
    def lay(home, config):
        _lay_key()(home, config)
        # An earlier installation's archive in the data is no data of this one
        (home / 'data' / '.ucm-archive-20260101T000000Z').mkdir()
        (home / 'data' / '.ucm-archive-20260101T000000Z' / 'ucm.db').write_text('old')
    out, log, home, config = _postrm_with(tmp_path, 'purge', lay, real=KEY_TOOLS)
    assert not (home.parent / 'ucm-archive').exists()
    assert not config.exists()
    assert 'master.key' not in out.stdout


def test_a_removal_says_where_the_master_key_of_the_data_is(tmp_path):
    out, _log, _home, config = _postrm_with(tmp_path, 'remove', lambda home, config: None)
    assert f'{config}/master.key' in out.stdout, out.stdout


def test_a_removal_stops_and_disables_the_watcher_too(tmp_path):
    """postinst enables ucm-watcher.path: once its unit files are gone it must not keep
    watching the data left in place."""
    _out, log, _home, _config = _postrm_with(tmp_path, 'remove', lambda home, config: None)
    calls = _calls(log)
    for call in ('systemctl stop ucm-watcher.path ucm-watcher.service', 'systemctl disable ucm-watcher.path'):
        assert call in calls, calls
    assert calls.index('systemctl disable ucm-watcher.path') < calls.index('systemctl daemon-reload')


# -- bytecode an earlier version wrote never outlives it ----------------------------

def _caches(home, data):
    """A __pycache__ the service wrote in each place: the package's code, its venv, its data."""
    places = {name: path / '__pycache__' for name, path in (
        ('backend', home / 'backend' / 'models'), ('scripts', home / 'scripts'),
        ('venv', home / 'venv' / 'lib'), ('data', data))}
    for cache in places.values():
        cache.mkdir(parents=True, exist_ok=True)
        (cache / 'x.cpython-312.pyc').write_bytes(b'old')
    return places


def _real_rm_inside(tmp_path):
    """rm records its call, then runs for real on paths of the sandbox only."""
    (tmp_path / 'bin' / 'rm').write_text(
        f'#!{POSIX_SH}\necho "rm $*" >> "$LOG"\n'
        f'for a; do case $a in -*) ;; "{tmp_path}"/*) ;; *) exit 0 ;; esac; done\n'
        f'exec {shutil.which("rm")} "$@"\n')


def _purged_before_python(calls, places):
    purge = next(i for i, c in enumerate(calls) if c.startswith('rm ') and '__pycache__' in c)
    first_python = next(i for i, c in enumerate(calls) if c.startswith(('bash ', 'sh ')))
    assert purge < first_python, calls
    assert not places['backend'].exists() and not places['scripts'].exists()
    assert places['venv'].exists() and places['data'].exists()


@pytest.mark.parametrize('previous', ['', '2.254'])
def test_the_deb_postinst_drops_the_bytecode_of_its_code_before_any_python_runs(tmp_path, previous):
    env, log, home, data, config = _post_sandbox(tmp_path, 0)
    places = _caches(home, data)
    _real_rm_inside(tmp_path)
    script = tmp_path / 'postinst.sandboxed'
    script.write_text(_paths(POSTINST.read_text(), home, data, config, quoted=True))
    out = subprocess.run(['/bin/bash', str(script), 'configure', previous], capture_output=True,
                         text=True, timeout=20, env=env)
    assert out.returncode == 0, out.stderr
    _purged_before_python(_calls(log), places)


@pytest.mark.parametrize('count', ['1', '2'])
def test_the_rpm_post_drops_the_bytecode_of_its_code_before_any_python_runs(tmp_path, count):
    env, log, home, data, config = _post_sandbox(tmp_path, 0)
    places = _caches(home, data)
    _real_rm_inside(tmp_path)
    body = _post_body(tmp_path, home, data, config)
    out = subprocess.run([POSIX_SH, '-c', body, 'post', count], capture_output=True, text=True,
                         timeout=20, env=env)
    assert out.returncode == 0, out.stderr
    _purged_before_python(_calls(log), places)


@pytest.mark.skipif(not shutil.which('rpmbuild'), reason='rpmbuild is not installed')
def test_the_rpm_keeps_the_dates_of_its_sources_where_rpm_clamps_them(tmp_path):
    """Built as Fedora 43 and EL10 configure rpm (dates clamped to SOURCE_DATE_EPOCH, taken
    from the %changelog): a file keeps its own date, not the date of the last entry."""
    lines = [l for l in SPEC.read_text().splitlines() if l.startswith('%global source_date_epoch')]
    top = tmp_path / 'rpmbuild'
    (top / 'SOURCES').mkdir(parents=True)
    src = top / 'SOURCES' / 'f.py'
    src.write_text('x = 1\n')
    stamp = 1_800_000_000
    os.utime(src, (stamp, stamp))
    spec = tmp_path / 't.spec'
    spec.write_text('\n'.join(lines) + '\nName: t\nVersion: 1\nRelease: 1\nSummary: t\nLicense: MIT\n'
                    'BuildArch: noarch\nSource0: f.py\n%description\nt\n%install\n'
                    'install -d %{buildroot}/opt/t\ncp -p %{SOURCE0} %{buildroot}/opt/t/f.py\n'
                    '%files\n/opt/t/f.py\n%changelog\n* Sat Feb 07 2026 t <t@t> - 1-1\n- t\n')
    env = {k: v for k, v in os.environ.items() if k != 'SOURCE_DATE_EPOCH'}
    built = subprocess.run(
        ['rpmbuild', '-bb', '--define', f'_topdir {top}', '--define', 'source_date_epoch_from_changelog 1',
         '--define', 'build_mtime_policy clamp_to_source_date_epoch',
         '--define', 'clamp_mtime_to_source_epoch 1', str(spec)],
        capture_output=True, text=True, timeout=120, env=env)
    assert built.returncode == 0, built.stderr
    rpm = next((top / 'RPMS' / 'noarch').glob('t-1-1*.rpm'))
    dump = subprocess.run(['rpm', '-qp', '--dump', str(rpm)], capture_output=True, text=True,
                          timeout=20, env=env).stdout
    assert dump.split()[2] == str(stamp), dump


# The certificate is generated by native-setup.sh https-cert (tests/test_native_setup_script.py),
# which names it without hostname and never writes through a link the service account laid
def test_the_deb_postinst_generates_its_https_certificate_through_native_setup(tmp_path):
    env, log, home, data, config = _post_sandbox(tmp_path, 0)
    script = tmp_path / 'postinst.sandboxed'
    script.write_text(_paths(POSTINST.read_text(), home, data, config, quoted=True))
    out = subprocess.run(['/bin/bash', str(script), 'configure', ''], capture_output=True,
                         text=True, timeout=20, env=env)
    assert out.returncode == 0, out.stderr
    calls = _calls(log)
    assert f'bash {home}/scripts/native-setup.sh https-cert {data} ucm ucm' in calls, calls
    assert not [c for c in calls if c.startswith('openssl req')], calls


def test_the_rpm_post_generates_its_https_certificate_through_native_setup(tmp_path):
    env, log, home, data, config = _post_sandbox(tmp_path, 0)
    body = _post_body(tmp_path, home, data, config)
    out = subprocess.run([POSIX_SH, '-c', body, 'post', '1'], capture_output=True, text=True,
                         timeout=20, env=env)
    assert out.returncode == 0, out.stderr
    calls = _calls(log)
    assert f'bash {home}/scripts/native-setup.sh https-cert {data} ucm ucm' in calls, calls
    assert not [c for c in calls if c.startswith('openssl req')], calls


@pytest.mark.parametrize('nologin', [True, False])
def test_the_rpm_pre_gives_the_account_a_shell_that_exists(rpm_pre, tmp_path, nologin):
    """/sbin/nologin stands for a path of the sandbox, there or not (a minimal EL9)."""
    shell = tmp_path / 'nologin'
    if nologin:
        shell.write_text('#!/bin/sh\nexit 1\n')
        shell.chmod(0o755)
    assert rpm_pre.count('/sbin/nologin') == 1
    body = rpm_pre.replace('/sbin/nologin', str(shell))
    out, calls, _ = _run_pre(body, tmp_path, "echo 'package ucm is not installed'; exit 1", count='1')
    assert out.returncode == 0, out.stderr
    useradd = next(c for c in calls if c.startswith('useradd'))
    assert f'-s {shell if nologin else "/bin/false"} ' in useradd, useradd


# /etc/ucm is the service account's: a ucm.env it replaced by a link is checked before any write,
# and the new file is written by own (a new file renamed over the entry), never through a link
def _linked_env(tmp_path, config):
    absent = tmp_path / 'victim-created-by-root'
    (config / 'ucm.env').symlink_to(absent)
    return absent


def test_the_deb_postinst_writes_no_ucm_env_through_a_link(tmp_path):
    env, log, home, data, config = _post_sandbox(tmp_path, 0)
    absent = _linked_env(tmp_path, config)
    script = tmp_path / 'postinst.sandboxed'
    script.write_text(_paths(POSTINST.read_text(), home, data, config, quoted=True))
    subprocess.run(['/bin/bash', str(script), 'configure', '2.254'], capture_output=True,
                   text=True, timeout=20, env=env)
    assert not absent.exists()
    calls = _calls(log)
    check = calls.index(f'bash {home}/scripts/native-setup.sh env-check {config}/ucm.env')
    assert calls.index(f'bash {home}/scripts/native-setup.sh own write {config}/ucm.env 600') > check


def test_the_rpm_post_writes_no_ucm_env_through_a_link(tmp_path):
    env, log, home, data, config = _post_sandbox(tmp_path, 0)
    absent = _linked_env(tmp_path, config)
    body = _post_body(tmp_path, home, data, config)
    subprocess.run([POSIX_SH, '-c', body, 'post', '2'], capture_output=True, text=True,
                   timeout=20, env=env)
    assert not absent.exists()
    calls = _calls(log)
    check = calls.index(f'bash {home}/scripts/native-setup.sh env-check {config}/ucm.env')
    assert calls.index(f'bash {home}/scripts/native-setup.sh own write {config}/ucm.env 600') > check


def test_the_deb_postinst_adds_data_dir_through_native_setup(tmp_path):
    out, calls, home, data, config = _run_postinst(tmp_path, 'configure', '2.254')
    assert out.returncode == 0, out.stderr
    assert f'bash {home}/scripts/native-setup.sh env-ensure {config}/ucm.env DATA_DIR {data}' in calls


def test_the_rpm_post_runs_native_setup_with_the_interpreter_the_package_requires(tmp_path):
    """EL9 requires python3.12 alone: native-setup writes through it, not through python3."""
    env, log, home, data, config = _post_sandbox(tmp_path, 0)
    (tmp_path / 'bin' / 'bash').write_text(
        f'#!{POSIX_SH}\necho "bash UCM_PYTHON=${{UCM_PYTHON:-}} $*" >> "$LOG"\n'
        '[ "$2" != fips-requested ] || grep -qx "UCM_FIPS_BUILD=1" "$3"\n')
    m = re.search(r'^%post\n(.*?)^%preun\n', SPEC.read_text(), re.M | re.S)
    body = m.group(1).replace('%systemd_post %{name}.service\n', ': systemd_post\n')
    body = _paths(_expand(body.replace('%{ucm_data}', '/opt/ucm/data')
                          .replace('%{ucm_python}', 'python3.12')), home, data, config, quoted=False)
    out = subprocess.run([POSIX_SH, '-c', body, 'post', '1'], capture_output=True, text=True,
                         timeout=20, env=env)
    assert out.returncode == 0, out.stderr
    setup = [c for c in _calls(log) if c.startswith('bash ') and 'native-setup.sh' in c]
    assert any(' venv ' in c for c in setup) and any(' https-cert ' in c for c in setup), setup
    assert all(c.startswith('bash UCM_PYTHON=python3.12 ') for c in setup), setup
