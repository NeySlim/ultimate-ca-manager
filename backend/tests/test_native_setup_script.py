"""packaging/scripts/native-setup.sh, run for real against temporary files and fake tools.

The DEB postinst and the RPM %post both call it: ucm.env completion, the
UCM_FIPS_BUILD=1 build-tool check, the venv build and the host FIPS step.
"""
import os
import pathlib
import shutil
import stat
import subprocess
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[2]
SCRIPT = ROOT / 'packaging' / 'scripts' / 'native-setup.sh'
BASH = shutil.which('bash')
UTILS = ('sed', 'awk', 'sort', 'grep', 'dirname', 'tail', 'head', 'tr', 'cat', 'wc',
         'mktemp', 'rm', 'mv', 'mkdir', 'touch', 'chmod', 'openssl', 'env', 'cp', 'readlink')

UBUNTU = 'ID=ubuntu\nVERSION_ID="24.04"\nPRETTY_NAME="Ubuntu 24.04.3 LTS"\n'
ALMA = 'ID="almalinux"\nID_LIKE="rhel centos fedora"\nVERSION_ID="9.8"\nPRETTY_NAME="AlmaLinux 9.8"\n'
RHEL = 'ID="rhel"\nID_LIKE="fedora"\nVERSION_ID="9.6"\nPRETTY_NAME="Red Hat Enterprise Linux 9.6"\n'
DEBIAN = 'ID=debian\nVERSION_ID="13"\nPRETTY_NAME="Debian GNU/Linux 13 (trixie)"\n'
FEDORA = 'ID=fedora\nVERSION_ID=43\nPRETTY_NAME="Fedora Linux 43"\n'

pytestmark = pytest.mark.skipif(BASH is None, reason='bash is required')


def _stub(path, body='exit 0'):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f'#!{BASH}\n{body}\n')
    path.chmod(0o755)
    return path


def _env(tmp_path, os_release=UBUNTU, extra=None):
    osr = tmp_path / 'os-release'
    osr.write_text(os_release)
    env = {
        'PATH': os.environ.get('PATH', '/usr/bin:/bin'),
        'UCM_SETUP_OS_RELEASE': str(osr),
        'UCM_SETUP_FIPS_FLAG': str(tmp_path / 'fips_enabled'),
        'UCM_SETUP_RUST_ROOT': str(tmp_path / 'usrlib'),
        'UCM_SETUP_BUILD_LOG': str(tmp_path / 'log' / 'fips-build.log'),
    }
    env.update(extra or {})
    return env


def _run(args, env):
    return subprocess.run([BASH, str(SCRIPT), *args], env=env, capture_output=True, text=True)


def _values(path):
    out = {}
    for line in path.read_text().splitlines():
        if '=' in line and not line.lstrip().startswith('#'):
            key, _, value = line.partition('=')
            out.setdefault(key.strip(), []).append(value)
    return out


# ---------------------------------------------------------------- ucm.env

def test_a_file_written_before_the_install_gets_secrets_and_defaults(tmp_path):
    envfile = tmp_path / 'ucm.env'
    envfile.write_text('UCM_FIPS_BUILD=1\n')
    envfile.chmod(0o644)
    result = _run(['env', str(envfile), '/opt/ucm/data'], _env(tmp_path))
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == 'new'
    values = _values(envfile)
    for key in ('SECRET_KEY', 'JWT_SECRET_KEY'):
        assert len(values[key]) == 1 and len(values[key][0]) == 64, values
        int(values[key][0], 16)
    assert values['SECRET_KEY'] != values['JWT_SECRET_KEY']
    assert values['DATABASE_PATH'] == ['/opt/ucm/data/ucm.db']
    assert values['DATA_DIR'] == ['/opt/ucm/data']
    assert values['HTTPS_PORT'] == ['8443'] and values['HTTP_PROTOCOL_PORT'] == ['8080']
    assert values['INITIAL_ADMIN_PASSWORD'] == ['changeme123']
    assert values['UCM_FIPS_BUILD'] == ['1']
    assert stat.S_IMODE(envfile.stat().st_mode) == 0o600


def test_a_file_without_final_newline_keeps_its_last_line(tmp_path):
    envfile = tmp_path / 'ucm.env'
    envfile.write_text('UCM_FIPS_BUILD=1')
    assert _run(['env', str(envfile), '/d'], _env(tmp_path)).returncode == 0
    assert _values(envfile)['UCM_FIPS_BUILD'] == ['1']
    assert 'UCM_FIPS_BUILD=1SECRET_KEY' not in envfile.read_text()


def test_present_values_are_never_overwritten(tmp_path):
    envfile = tmp_path / 'ucm.env'
    envfile.write_text('SECRET_KEY=keep-me\nHTTPS_PORT=9443\nexport LOG_LEVEL="DEBUG"\n')
    result = _run(['env', str(envfile), '/d'], _env(tmp_path))
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == ''
    values = _values(envfile)
    assert values['SECRET_KEY'] == ['keep-me']
    assert values['HTTPS_PORT'] == ['9443']
    assert len(values['JWT_SECRET_KEY'][0]) == 64
    # A configured install is not handed the first-start defaults again
    assert 'INITIAL_ADMIN_PASSWORD' not in values and 'LOG_LEVEL' not in values


def test_an_empty_secret_is_completed(tmp_path):
    envfile = tmp_path / 'ucm.env'
    envfile.write_text('SECRET_KEY=\nJWT_SECRET_KEY=x\n')
    assert _run(['env', str(envfile), '/d'], _env(tmp_path)).returncode == 0
    assert len(_values(envfile)['SECRET_KEY'][-1]) == 64


def test_a_complete_file_is_left_untouched(tmp_path):
    envfile = tmp_path / 'ucm.env'
    body = 'SECRET_KEY=a\nJWT_SECRET_KEY=b\nDATABASE_PATH=/x.db\n'
    envfile.write_text(body)
    envfile.chmod(0o640)
    assert _run(['env', str(envfile), '/d'], _env(tmp_path)).returncode == 0
    assert envfile.read_text() == body
    assert stat.S_IMODE(envfile.stat().st_mode) == 0o640


@pytest.mark.parametrize('before, after', [
    ('SECRET_KEY=a\nJWT_SECRET_KEY=b\n', ['1']),
    ('SECRET_KEY=a\nJWT_SECRET_KEY=b\nUCM_FIPS_BUILD=0\n', ['1']),
])
def test_the_environment_variable_is_persisted(tmp_path, before, after):
    envfile = tmp_path / 'ucm.env'
    envfile.write_text(before)
    assert _run(['env', str(envfile), '/d'], _env(tmp_path, extra={'UCM_FIPS_BUILD': '1'})).returncode == 0
    assert _values(envfile)['UCM_FIPS_BUILD'] == after


@pytest.mark.parametrize('content, variable, requested', [
    ('', None, False),
    ('UCM_FIPS_BUILD=1\n', None, True),
    ('UCM_FIPS_BUILD="yes"\n', None, True),
    ('UCM_FIPS_BUILD=0\n', None, False),
    ('', '1', True),
    ('# UCM_FIPS_BUILD=1\n', None, False),
])
def test_fips_requested(tmp_path, content, variable, requested):
    envfile = tmp_path / 'ucm.env'
    envfile.write_text(content)
    extra = {'UCM_FIPS_BUILD': variable} if variable else {}
    result = _run(['fips-requested', str(envfile)], _env(tmp_path, extra=extra))
    assert (result.returncode == 0) is requested


# ------------------------------------------------------------ build tools

def _toolbox(tmp_path, rustc_in_path='1.75.0', missing=(), libs=True):
    """A PATH holding the basic utilities and stubs for every build tool."""
    bin_dir = tmp_path / 'bin'
    bin_dir.mkdir(exist_ok=True)
    for util in UTILS:
        real = shutil.which(util)
        if real and not (bin_dir / util).exists():
            (bin_dir / util).symlink_to(real)
    for tool in ('gcc', 'pkg-config', 'pg_config', 'xml2-config', 'xslt-config', 'xmlsec1-config'):
        if tool not in missing:
            _stub(bin_dir / tool)
    listing = 'libxmlsec1-openssl.so.1 (libc6,x86-64) => /lib/libxmlsec1-openssl.so.1' if libs else ''
    _stub(bin_dir / 'ldconfig', f'echo "{listing}"')
    if rustc_in_path:
        _stub(bin_dir / 'rustc', f'echo "rustc {rustc_in_path} (abc 2024-01-01)"')
        _stub(bin_dir / 'cargo', f'echo "cargo {rustc_in_path}"')
    python = _stub(tmp_path / 'python', 'exit 0')
    return bin_dir, python


def _rust_lib(tmp_path, version):
    root = tmp_path / 'usrlib' / f'rust-{version.rsplit(".", 1)[0]}' / 'bin'
    _stub(root / 'rustc', f'echo "rustc {version} (def 2025-11-07)"')
    _stub(root / 'cargo', f'echo "cargo {version}"')
    return root


def test_the_newest_rust_outside_path_is_chosen(tmp_path):
    bin_dir, python = _toolbox(tmp_path)
    _rust_lib(tmp_path, '1.84.0')
    newest = _rust_lib(tmp_path, '1.91.1')
    result = _run(['check-build-tools', str(python), 'deb'], _env(tmp_path, extra={'PATH': str(bin_dir)}))
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == str(newest)


def test_rust_in_path_is_enough_when_recent(tmp_path):
    bin_dir, python = _toolbox(tmp_path, rustc_in_path='1.92.0')
    result = _run(['check-build-tools', str(python), 'rpm'], _env(tmp_path, ALMA, {'PATH': str(bin_dir)}))
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == str(bin_dir)


@pytest.mark.parametrize('rustc', [None, '1.75.0', '1.82.9'])
def test_missing_or_old_rust_fails_with_the_ubuntu_command(tmp_path, rustc):
    bin_dir, python = _toolbox(tmp_path, rustc_in_path=rustc)
    result = _run(['check-build-tools', str(python), 'deb'], _env(tmp_path, extra={'PATH': str(bin_dir)}))
    assert result.returncode == 1
    assert 'cargo/rustc>=1.83' in result.stderr
    assert ('sudo apt-get install -y gcc pkg-config python3-dev python3-venv libpq-dev libxml2-dev '
            'libxslt1-dev zlib1g-dev libssl-dev libxmlsec1-dev libxmlsec1t64-openssl rustc-1.91 cargo-1.91') in result.stderr
    assert 'sudo dpkg --configure -a' in result.stderr


def test_missing_headers_are_listed_with_the_el9_command(tmp_path):
    bin_dir, python = _toolbox(tmp_path, rustc_in_path='1.92.0', missing=('xmlsec1-config', 'pg_config'), libs=False)
    result = _run(['check-build-tools', str(python), 'rpm'], _env(tmp_path, ALMA, {'PATH': str(bin_dir)}))
    assert result.returncode == 1
    for item in ('pg_config', 'xmlsec1-config', 'libxmlsec1-openssl'):
        assert item in result.stderr
    assert 'sudo dnf config-manager --set-enabled crb' in result.stderr
    assert 'xmlsec1-devel xmlsec1-openssl libtool-ltdl-devel rust cargo' in result.stderr
    assert 'sudo dnf reinstall' in result.stderr


def test_rhel_is_told_to_enable_codeready_builder(tmp_path):
    bin_dir, python = _toolbox(tmp_path, rustc_in_path=None)
    result = _run(['check-build-tools', str(python), 'rpm'], _env(tmp_path, RHEL, {'PATH': str(bin_dir)}))
    assert result.returncode == 1
    assert 'subscription-manager repos --enable codeready-builder-for-rhel-9-' in result.stderr


def test_an_old_python_is_refused(tmp_path):
    bin_dir, _python = _toolbox(tmp_path, rustc_in_path='1.92.0')
    old = _stub(tmp_path / 'python39', 'exit 1')
    result = _run(['check-build-tools', str(old), 'rpm'], _env(tmp_path, ALMA, {'PATH': str(bin_dir)}))
    assert result.returncode == 1
    assert 'python>=3.12' in result.stderr


@pytest.mark.parametrize('os_release', [DEBIAN, FEDORA, ALMA.replace('9.8', '10.0')])
def test_unsupported_distributions_are_refused(tmp_path, os_release):
    bin_dir, python = _toolbox(tmp_path, rustc_in_path='1.92.0')
    result = _run(['check-build-tools', str(python), 'deb'], _env(tmp_path, os_release, {'PATH': str(bin_dir)}))
    assert result.returncode == 1
    assert 'supported on RHEL, AlmaLinux and Rocky Linux 9 and on Ubuntu 24.04' in result.stderr


# ----------------------------------------------------------------- venv

def _fake_python(tmp_path, pip_body):
    """`python -m venv DIR` lays out a venv whose pip records its calls, then runs pip_body."""
    record = tmp_path / 'pip-calls'
    templates = tmp_path / 'templates'
    _stub(templates / 'pip',
          f'echo "ARGS $*" >> {record}\necho "PATH $PATH" >> {record}\necho "RUSTC ${{RUSTC:-}}" >> {record}\n'
          f'prev=""; for a in "$@"; do [ "$prev" = -r ] && cat "$a" >> {record}; prev=$a; done\n{pip_body}')
    _stub(templates / 'python', 'cat > /dev/null; echo "cryptography, hashlib and psycopg2 use the system OpenSSL"')
    body = (f'if [ "$1" = -m ] && [ "$2" = venv ]; then\n'
            f'  mkdir -p "$3/bin" && cp {templates}/pip {templates}/python "$3/bin/"\nfi\nexit 0')
    return _stub(tmp_path / 'python', body), record


def _home(tmp_path):
    home = tmp_path / 'opt'
    (home / 'venv').mkdir(parents=True)
    (home / 'venv' / 'previous').write_text('old venv')
    (home / 'requirements.txt').write_text('cryptography==50.0.2\npsycopg2-binary>=2.9.9\nxmlsec>=1.3.13\nlxml>=5.0\n')
    envfile = tmp_path / 'ucm.env'
    envfile.write_text('UCM_FIPS_BUILD=1\n')
    return home, envfile


def test_the_fips_build_compiles_from_source_with_rust_in_path(tmp_path):
    bin_dir, _ = _toolbox(tmp_path, rustc_in_path=None)
    rust = _rust_lib(tmp_path, '1.92.0')
    python, record = _fake_python(tmp_path, 'exit 0')
    home, envfile = _home(tmp_path)
    result = _run(['venv', str(home), str(python), 'rpm', str(envfile)],
                  _env(tmp_path, ALMA, {'PATH': str(bin_dir)}))
    assert result.returncode == 0, result.stderr
    calls = record.read_text()
    assert 'ARGS install --no-binary cryptography,psycopg2,lxml,xmlsec -r ' in calls
    assert 'psycopg2>=2.9.9' in calls and 'psycopg2-binary' not in calls
    assert 'xmlsec==1.3.13' in calls  # EL9 pin
    assert f'PATH {rust}:' in calls and f'RUSTC {rust}/rustc' in calls
    assert '--quiet -r' not in calls
    assert not (home / 'venv' / 'previous').exists() and not (home / 'venv.prev').exists()


def test_ubuntu_keeps_the_xmlsec_requirement(tmp_path):
    bin_dir, _ = _toolbox(tmp_path, rustc_in_path=None)
    _rust_lib(tmp_path, '1.91.1')
    python, record = _fake_python(tmp_path, 'exit 0')
    home, envfile = _home(tmp_path)
    result = _run(['venv', str(home), str(python), 'deb', str(envfile)], _env(tmp_path, extra={'PATH': str(bin_dir)}))
    assert result.returncode == 0, result.stderr
    assert 'xmlsec>=1.3.13' in record.read_text()


def test_a_failed_fips_build_fails_and_keeps_the_previous_venv(tmp_path):
    bin_dir, _ = _toolbox(tmp_path, rustc_in_path='1.92.0')
    python, record = _fake_python(tmp_path, 'case "$*" in *no-binary*) echo "error: linker cc failed"; exit 1;; esac; exit 0')
    home, envfile = _home(tmp_path)
    result = _run(['venv', str(home), str(python), 'rpm', str(envfile)],
                  _env(tmp_path, ALMA, {'PATH': str(bin_dir)}))
    assert result.returncode == 1
    assert 'the UCM_FIPS_BUILD=1 build failed' in result.stderr
    assert 'linker cc failed' in result.stderr
    assert (home / 'venv' / 'previous').read_text() == 'old venv'
    assert '--quiet -r' not in record.read_text()  # never falls back to the wheels


def test_missing_tools_fail_before_the_venv_is_touched(tmp_path):
    bin_dir, _ = _toolbox(tmp_path, rustc_in_path=None)
    python, record = _fake_python(tmp_path, 'exit 0')
    home, envfile = _home(tmp_path)
    result = _run(['venv', str(home), str(python), 'deb', str(envfile)], _env(tmp_path, extra={'PATH': str(bin_dir)}))
    assert result.returncode == 1
    assert 'cargo/rustc>=1.83' in result.stderr
    assert (home / 'venv' / 'previous').exists() and not record.exists()


def test_the_standard_install_is_unchanged(tmp_path):
    bin_dir, _ = _toolbox(tmp_path, rustc_in_path=None)
    python, record = _fake_python(tmp_path, 'exit 0')
    home, envfile = _home(tmp_path)
    envfile.write_text('SECRET_KEY=a\n')
    result = _run(['venv', str(home), str(python), 'deb', str(envfile)], _env(tmp_path, DEBIAN, {'PATH': str(bin_dir)}))
    assert result.returncode == 0, result.stderr
    args = [line for line in record.read_text().splitlines() if line.startswith('ARGS')]
    assert args == [
        'ARGS install --quiet --upgrade pip',
        f'ARGS install --quiet -r {home}/requirements.txt',
        'ARGS install --quiet --no-deps pyjks==20.0.0',
    ]


def _build_ok(tmp_path, envfile, os_release=ALMA):
    return _run(['fips-build-ok', str(envfile)], _env(tmp_path, os_release))


def test_a_failed_build_is_reported_until_a_build_succeeds(tmp_path):
    bin_dir, _ = _toolbox(tmp_path, rustc_in_path='1.92.0')
    failing, _ = _fake_python(tmp_path, 'case "$*" in *no-binary*) exit 1;; esac; exit 0')
    home, envfile = _home(tmp_path)
    env = _env(tmp_path, ALMA, {'PATH': str(bin_dir)})
    assert _run(['venv', str(home), str(failing), 'rpm', str(envfile)], env).returncode == 1
    result = _build_ok(tmp_path, envfile)
    assert result.returncode == 1 and 'the UCM_FIPS_BUILD=1 build failed' in result.stderr
    working, _ = _fake_python(tmp_path, 'exit 0')
    assert _run(['venv', str(home), str(working), 'rpm', str(envfile)], env).returncode == 0
    assert _build_ok(tmp_path, envfile).returncode == 0


def test_missing_tools_are_reported_as_a_failed_build(tmp_path):
    bin_dir, _ = _toolbox(tmp_path, rustc_in_path=None)
    python, _ = _fake_python(tmp_path, 'exit 0')
    home, envfile = _home(tmp_path)
    assert _run(['venv', str(home), str(python), 'deb', str(envfile)],
                _env(tmp_path, extra={'PATH': str(bin_dir)})).returncode == 1
    assert _build_ok(tmp_path, envfile, UBUNTU).returncode == 1


def test_a_standard_install_ignores_an_old_failed_build(tmp_path):
    envfile = tmp_path / 'ucm.env'
    envfile.write_text('SECRET_KEY=a\n')
    (tmp_path / 'log').mkdir()
    (tmp_path / 'log' / 'fips-build.failed').write_text('build failed')
    assert _build_ok(tmp_path, envfile).returncode == 0


def _precheck(tmp_path, envfile, venv_python, os_release=ALMA, **toolbox):
    bin_dir, _ = _toolbox(tmp_path, **toolbox)
    home = tmp_path / 'opt'
    (home / 'venv' / 'bin').mkdir(parents=True)
    (home / 'venv' / 'bin' / 'python').symlink_to(venv_python)
    return _run(['update-precheck', str(home), str(envfile), 'rpm'],
                _env(tmp_path, os_release, {'PATH': str(bin_dir)}))


def test_the_updater_refuses_a_fips_build_without_tools(tmp_path):
    envfile = tmp_path / 'ucm.env'
    envfile.write_text('UCM_FIPS_BUILD=1\n')
    result = _precheck(tmp_path, envfile, _stub(tmp_path / 'python3.12'), rustc_in_path=None)
    assert result.returncode == 1
    assert 'cargo/rustc>=1.83' in result.stderr and 'sudo dnf install -y python3.12-devel' in result.stderr


def test_the_updater_checks_the_interpreter_of_the_venv(tmp_path):
    envfile = tmp_path / 'ucm.env'
    envfile.write_text('UCM_FIPS_BUILD=1\n')
    result = _precheck(tmp_path, envfile, _stub(tmp_path / 'python3.9', 'exit 1'), rustc_in_path='1.92.0')
    assert result.returncode == 1 and 'python>=3.12' in result.stderr
    ok = tmp_path / 'ok'
    ok.mkdir()
    assert _precheck(ok, envfile, _stub(ok / 'python3.12'), rustc_in_path='1.92.0').returncode == 0


def test_the_updater_precheck_is_a_no_op_for_a_standard_install(tmp_path):
    envfile = tmp_path / 'ucm.env'
    envfile.write_text('SECRET_KEY=a\n')
    result = _precheck(tmp_path, envfile, _stub(tmp_path / 'python3'), DEBIAN, rustc_in_path=None)
    assert result.returncode == 0 and result.stderr == ''


# ------------------------------------------------------------ fips-finish

def _finish(tmp_path, envfile, flag, os_release=ALMA, active=True):
    """The venv's python is real; backend/fips_mode.py answers provider_active()."""
    home = tmp_path / 'opt'
    (home / 'venv' / 'bin').mkdir(parents=True, exist_ok=True)
    (home / 'venv' / 'bin' / 'python').symlink_to(sys.executable)
    (home / 'backend').mkdir()
    (home / 'backend' / 'fips_mode.py').write_text(f'def provider_active():\n    return {active}\n')
    (tmp_path / 'fips_enabled').write_text(f'{flag}\n')
    return _run(['fips-finish', str(home), str(envfile), str(tmp_path / 'data'), 'ucm'], _env(tmp_path, os_release))


def test_a_standard_install_on_a_fips_host_gets_the_advice(tmp_path):
    envfile = tmp_path / 'ucm.env'
    envfile.write_text('SECRET_KEY=a\n')
    result = _finish(tmp_path, envfile, 1)
    assert result.returncode == 0
    assert f'host is in FIPS mode: set UCM_FIPS_BUILD=1 in {envfile} and reinstall' in result.stdout
    assert 'UCM_FIPS' not in envfile.read_text()


def test_a_standard_install_elsewhere_says_nothing(tmp_path):
    envfile = tmp_path / 'ucm.env'
    envfile.write_text('SECRET_KEY=a\n')
    result = _finish(tmp_path, envfile, 0)
    assert result.returncode == 0 and result.stdout == ''


def test_a_fips_host_turns_fips_mode_on(tmp_path):
    envfile = tmp_path / 'ucm.env'
    envfile.write_text('UCM_FIPS_BUILD=1\n')
    result = _finish(tmp_path, envfile, 1)
    assert result.returncode == 0, result.stderr
    assert _values(envfile)['UCM_FIPS'] == ['1']
    assert 'FIPS provider is active' in result.stdout
    assert 'readiness check skipped: no database yet' in result.stdout


def test_an_explicit_ucm_fips_0_is_kept(tmp_path):
    envfile = tmp_path / 'ucm.env'
    envfile.write_text('UCM_FIPS_BUILD=1\nUCM_FIPS=0\n')
    assert _finish(tmp_path, envfile, 1).returncode == 0
    assert _values(envfile)['UCM_FIPS'] == ['0']


def test_an_inactive_provider_is_reported(tmp_path):
    envfile = tmp_path / 'ucm.env'
    envfile.write_text('UCM_FIPS_BUILD=1\n')
    result = _finish(tmp_path, envfile, 1, active=False)
    assert result.returncode == 0
    assert 'the service refuses to start' in result.stdout


@pytest.mark.parametrize('os_release, command', [
    (ALMA, 'sudo fips-mode-setup --enable'),
    (UBUNTU, 'sudo pro enable fips-updates'),
])
def test_a_host_outside_fips_mode_is_told_how_to_enable_it(tmp_path, os_release, command):
    envfile = tmp_path / 'ucm.env'
    envfile.write_text('UCM_FIPS_BUILD=1\n')
    result = _finish(tmp_path, envfile, 0, os_release)
    assert result.returncode == 0
    assert 'not in FIPS mode' in result.stdout and command in result.stdout
    assert 'UCM_FIPS=' not in envfile.read_text().replace('UCM_FIPS_BUILD=', '')
