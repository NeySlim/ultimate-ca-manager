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
        'mv': 'echo "mv $*" >> "$LOG"', 'groupadd': 'echo "groupadd $*" >> "$LOG"',
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


def _run_preinst(script, tmp_path, *args):
    env, log = _fakebin(tmp_path)
    out = subprocess.run(['/bin/bash', str(script), *args], capture_output=True, text=True,
                         timeout=20, env=env)
    return out, _calls(log)


@pytest.mark.parametrize('args', [('upgrade', '2.253'), ('upgrade', '1.8.3'),
                                  ('install', '2.253')])
def test_the_deb_preinst_refuses_before_any_write(preinst, tmp_path, args):
    """dpkg passes the installed version as $2; `install` with one means its config was kept."""
    out, calls = _run_preinst(preinst, tmp_path, *args)
    assert out.returncode != 0
    assert f'UCM {args[1]} is installed' in out.stderr
    assert calls == []


def test_the_deb_preinst_upgrades_a_2_254(preinst, tmp_path):
    out, calls = _run_preinst(preinst, tmp_path, 'upgrade', '2.254')
    assert out.returncode == 0, out.stderr
    assert 'mkdir -p /var/lib/ucm/backups' in calls


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
