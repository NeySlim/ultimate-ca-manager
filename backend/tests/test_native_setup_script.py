"""packaging/scripts/native-setup.sh, run for real against temporary files and fake tools.

The DEB postinst and the RPM %post both call it: ucm.env completion, the
UCM_FIPS_BUILD=1 build-tool check, the venv build and the host FIPS step.
"""
import os
import pathlib
import shutil
import signal
import stat
import subprocess
import sys
import time

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[2]
SCRIPT = ROOT / 'packaging' / 'scripts' / 'native-setup.sh'
BASH = shutil.which('bash')
UTILS = ('sed', 'awk', 'sort', 'grep', 'dirname', 'tail', 'head', 'tr', 'cat', 'wc',
         'mktemp', 'rm', 'mv', 'mkdir', 'touch', 'chmod', 'chown', 'openssl', 'env', 'cp',
         'readlink', 'python3')

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
        # Absent unless a test says otherwise: the host's own ucm service is never queried
        'UCM_SETUP_SYSTEMD_RUN': str(tmp_path / 'no-systemd'),
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
    assert len(values['SECRET_KEY']) == 1 and len(values['SECRET_KEY'][0]) == 64, values
    int(values['SECRET_KEY'][0], 16)
    # Nothing reads a JWT secret: none is generated
    assert 'JWT_SECRET_KEY' not in values
    assert values['DATABASE_PATH'] == ['/opt/ucm/data/ucm.db']
    assert values['DATA_DIR'] == ['/opt/ucm/data']
    assert values['HTTPS_PORT'] == ['8443'] and values['HTTP_PROTOCOL_PORT'] == ['8080']
    # No default password: the first start generates one into the data directory
    assert 'INITIAL_ADMIN_PASSWORD' not in values
    assert values['UCM_FIPS_BUILD'] == ['1']
    assert stat.S_IMODE(envfile.stat().st_mode) == 0o600


@pytest.mark.parametrize('line', ['INITIAL_ADMIN_PASSWORD=changeme123', 'export INITIAL_ADMIN_PASSWORD="changeme123"'])
def test_the_password_older_packages_wrote_is_dropped(tmp_path, line):
    """An existing account is untouched; a later database reset generates instead."""
    envfile = tmp_path / 'ucm.env'
    envfile.write_text(f'SECRET_KEY=keep-me\n{line}\nLOG_LEVEL=INFO\n')
    envfile.chmod(0o600)
    assert _run(['env', str(envfile), '/d'], _env(tmp_path)).returncode == 0
    assert envfile.read_text() == 'SECRET_KEY=keep-me\nLOG_LEVEL=INFO\n'
    assert stat.S_IMODE(envfile.stat().st_mode) == 0o600


def test_a_password_the_operator_chose_stays_in_the_file(tmp_path):
    envfile = tmp_path / 'ucm.env'
    envfile.write_text('SECRET_KEY=keep-me\nINITIAL_ADMIN_PASSWORD=changeme1234\n')
    assert _run(['env', str(envfile), '/d'], _env(tmp_path)).returncode == 0
    assert _values(envfile)['INITIAL_ADMIN_PASSWORD'] == ['changeme1234']


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
    assert 'JWT_SECRET_KEY' not in values
    # A configured install is not handed the first-start defaults again
    assert 'INITIAL_ADMIN_PASSWORD' not in values and 'LOG_LEVEL' not in values


@pytest.mark.parametrize('empty', ['SECRET_KEY=', 'SECRET_KEY=""', "export SECRET_KEY=''", 'SECRET_KEY = '])
def test_an_empty_secret_is_filled_in_place(tmp_path, empty):
    envfile = tmp_path / 'ucm.env'
    envfile.write_text(f'# head\n{empty}\nJWT_SECRET_KEY=x\nDATA_DIR=\nTAIL=1\n')
    assert _run(['env', str(envfile), '/d'], _env(tmp_path)).returncode == 0
    lines = envfile.read_text().splitlines()
    assert lines[0] == '# head' and lines[2:5] == ['JWT_SECRET_KEY=x', 'DATA_DIR=/d', 'TAIL=1'], lines
    key, _, value = lines[1].partition('=')
    assert key == 'SECRET_KEY' and len(value) == 64, lines
    values = _values(envfile)
    assert len(values['SECRET_KEY']) == 1 and values['DATA_DIR'] == ['/d']


def test_a_value_set_earlier_is_kept_when_a_later_line_empties_it(tmp_path):
    envfile = tmp_path / 'ucm.env'
    envfile.write_text('SECRET_KEY=keep-me\nSECRET_KEY=\nJWT_SECRET_KEY=x\n')
    assert _run(['env', str(envfile), '/d'], _env(tmp_path)).returncode == 0
    values = _values(envfile)['SECRET_KEY']
    assert values[0] == 'keep-me' and len(values) == 2 and len(values[1]) == 64


def test_a_default_with_sed_metacharacters_is_written_verbatim(tmp_path):
    envfile = tmp_path / 'ucm.env'
    envfile.write_text('DATA_DIR=\n')
    assert _run(['env', str(envfile), '/srv/a&b#c\\d'], _env(tmp_path)).returncode == 0
    assert _values(envfile)['DATA_DIR'] == ['/srv/a&b#c\\d']


def test_the_file_is_restricted_before_a_secret_is_written(tmp_path):
    """openssl, which produces each secret, sees the file mode at that moment."""
    bin_dir = tmp_path / 'bin'
    bin_dir.mkdir()
    for util in UTILS + ('stat',):
        real = shutil.which(util)
        if real and util != 'openssl':
            (bin_dir / util).symlink_to(real)
    envfile = tmp_path / 'ucm.env'
    envfile.write_text('UCM_FIPS_BUILD=1\n')
    envfile.chmod(0o644)
    modes = tmp_path / 'modes'
    _stub(bin_dir / 'openssl', f'stat -c %a {envfile} >> {modes}; echo {"ab" * 32}')
    result = _run(['env', str(envfile), '/d'], _env(tmp_path, extra={'PATH': str(bin_dir)}))
    assert result.returncode == 0, result.stderr
    assert modes.read_text().split() == ['600']


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

# Fake pip body: installing the requirements gives the venv a gunicorn, run by the venv's python
GUNICORN = 'case "$*" in *" -r "*) d=$(dirname "$0"); printf "#!$d/python\\n" > "$d/gunicorn"; chmod +x "$d/gunicorn";; esac'


def _fake_python(tmp_path, pip_body):
    """`python -m venv DIR` lays out a venv that writes DIR where the real one does (pyvenv.cfg,
    activate*, the pip shebang); its python runs scripts, so a stale shebang fails as for real.
    pip records its calls and the ucm state, lays out gunicorn with the requirements, then runs pip_body."""
    record = tmp_path / 'pip-calls'
    templates = tmp_path / 'templates'
    _stub(templates / 'pip',
          f'echo "ARGS $*" >> {record}\necho "PATH $PATH" >> {record}\necho "RUSTC ${{RUSTC:-}}" >> {record}\n'
          f'echo "UCM $(cat {tmp_path}/ucm-state 2>/dev/null)" >> {record}\n'
          f'prev=""; for a in "$@"; do [ "$prev" = -r ] && cat "$a" >> {record}; prev=$a; done\n{GUNICORN}\n{pip_body}')
    _stub(templates / 'python', f'''case "${{1:-}}" in
  -c) exit 0 ;;
  -) cat > /dev/null; echo "cryptography, hashlib and psycopg use the system OpenSSL" ;;
  *) exec {BASH} "$@" ;;
esac''')
    body = f'''if [ "$1" = -m ] && [ "$2" = venv ]; then
  mkdir -p "$3/bin" && cp {templates}/python "$3/bin/"
  {{ printf '#!%s/bin/python\\n' "$3"; tail -n +2 {templates}/pip; }} > "$3/bin/pip" && chmod +x "$3/bin/pip"
  printf 'home = /usr/bin\\ncommand = %s %s\\n' "$0" "$*" > "$3/pyvenv.cfg"
  printf 'VIRTUAL_ENV="%s"\\n' "$3" > "$3/bin/activate"
  printf 'setenv VIRTUAL_ENV "%s"\\n' "$3" > "$3/bin/activate.csh"
  printf 'set -gx VIRTUAL_ENV "%s"\\n' "$3" > "$3/bin/activate.fish"
fi
exit 0'''
    return _stub(tmp_path / 'python', body), record


def _home(tmp_path):
    home = tmp_path / 'opt'
    (home / 'venv').mkdir(parents=True)
    (home / 'venv' / 'previous').write_text('old venv')
    (home / 'requirements.txt').write_text('cryptography==50.0.2\npsycopg[binary]>=3.3,<4\nxmlsec>=1.3.13\nlxml>=5.0\n')
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
    assert 'ARGS install --no-binary cryptography,psycopg-c,lxml,xmlsec -r ' in calls
    assert 'psycopg[c]>=3.3,<4' in calls and 'psycopg[binary]' not in calls
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


# The service account owns /var/log/ucm: the build log and its marker are never written through a link
def _linked_build_files(tmp_path):
    (tmp_path / 'log').mkdir()
    victims = {}
    for name in ('fips-build.log', 'fips-build.failed'):
        victim = tmp_path / f'victim-{name}'
        victim.write_text('precious')
        victim.chmod(0o600)
        (tmp_path / 'log' / name).symlink_to(victim)
        victims[name] = victim
    return victims


def _untouched(victims):
    for victim in victims.values():
        assert victim.read_text() == 'precious' and stat.S_IMODE(victim.stat().st_mode) == 0o600, victim


def test_missing_tools_write_no_marker_through_a_link(tmp_path):
    victims = _linked_build_files(tmp_path)
    bin_dir, _ = _toolbox(tmp_path, rustc_in_path=None)
    python, _ = _fake_python(tmp_path, 'exit 0')
    home, envfile = _home(tmp_path)
    result = _run(['venv', str(home), str(python), 'deb', str(envfile)], _env(tmp_path, extra={'PATH': str(bin_dir)}))
    assert result.returncode == 1 and 'cargo/rustc>=1.83' in result.stderr, result.stderr
    _untouched(victims)
    marker = tmp_path / 'log' / 'fips-build.failed'
    assert not marker.is_symlink() and marker.read_text() == 'build tools missing\n'


@pytest.mark.parametrize('build, failed', [
    ('exit 0', False),
    ('case "$*" in *no-binary*) echo "error: linker cc failed"; exit 1;; esac; exit 0', True)])
@pytest.mark.parametrize('linked', [False, True])
def test_a_fips_build_keeps_its_log_and_marker(tmp_path, build, failed, linked):
    """A link laid at either path is replaced, never written through."""
    victims = _linked_build_files(tmp_path) if linked else {}
    bin_dir, _ = _toolbox(tmp_path, rustc_in_path='1.92.0')
    python, _ = _fake_python(tmp_path, build)
    home, envfile = _home(tmp_path)
    result = _run(['venv', str(home), str(python), 'rpm', str(envfile)], _env(tmp_path, ALMA, {'PATH': str(bin_dir)}))
    assert (result.returncode == 1) is failed, result.stderr
    log = tmp_path / 'log' / 'fips-build.log'
    assert stat.S_ISREG(log.lstat().st_mode)
    if failed:
        assert 'linker cc failed' in log.read_text() and 'linker cc failed' in result.stderr
        assert (tmp_path / 'log' / 'fips-build.failed').read_text() == 'build failed\n'
    else:
        assert 'cryptography, hashlib and psycopg use the system OpenSSL' in log.read_text()
        assert not (tmp_path / 'log' / 'fips-build.failed').exists()
    _untouched(victims)


def _venv_dir(path, works=True, gunicorn=True, tag='good'):
    (path / 'bin').mkdir(parents=True)
    _stub(path / 'bin' / 'python', 'exit 0' if works else 'exit 127')
    if gunicorn:
        _stub(path / 'bin' / 'gunicorn')
    (path / tag).write_text(tag)


@pytest.mark.parametrize('broken', [{'gunicorn': False}, {'works': False}])
@pytest.mark.parametrize('build', ['exit 0', 'case "$*" in *no-binary*) exit 1;; esac; exit 0'])
def test_an_interrupted_build_does_not_cost_the_working_venv(tmp_path, broken, build):
    """A build killed after venv was moved aside leaves venv.prev (working) and an incomplete venv."""
    bin_dir, _ = _toolbox(tmp_path, rustc_in_path='1.92.0')
    python, _ = _fake_python(tmp_path, build)
    home, envfile = _home(tmp_path)
    shutil.rmtree(home / 'venv')
    _venv_dir(home / 'venv.prev')
    _venv_dir(home / 'venv', tag='partial', **broken)
    result = _run(['venv', str(home), str(python), 'rpm', str(envfile)], _env(tmp_path, ALMA, {'PATH': str(bin_dir)}))
    if build == 'exit 0':
        assert result.returncode == 0, result.stderr
    else:
        assert result.returncode == 1
        assert (home / 'venv' / 'good').exists() and not (home / 'venv' / 'partial').exists()
    assert not (home / 'venv.prev').exists()


def test_a_working_venv_is_preferred_to_a_leftover_prev(tmp_path):
    bin_dir, _ = _toolbox(tmp_path, rustc_in_path='1.92.0')
    python, _ = _fake_python(tmp_path, 'case "$*" in *no-binary*) exit 1;; esac; exit 0')
    home, envfile = _home(tmp_path)
    shutil.rmtree(home / 'venv')
    _venv_dir(home / 'venv.prev', tag='older')
    _venv_dir(home / 'venv', tag='current')
    result = _run(['venv', str(home), str(python), 'rpm', str(envfile)], _env(tmp_path, ALMA, {'PATH': str(bin_dir)}))
    assert result.returncode == 1
    assert (home / 'venv' / 'current').exists() and not (home / 'venv.prev').exists()


@pytest.mark.parametrize('layout, ok', [
    (None, False), ({'gunicorn': False}, False), ({'works': False}, False), ({}, True)])
def test_venv_ok(tmp_path, layout, ok):
    if layout is not None:
        _venv_dir(tmp_path / 'venv', **layout)
    assert (_run(['venv-ok', str(tmp_path)], _env(tmp_path)).returncode == 0) is ok


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
    # The previous venv was set aside at the switch, then dropped
    assert not (home / 'venv.prev').exists() and not (home / 'venv' / 'previous').exists()
    assert not (home / 'venv.next').exists()


# ------------------------------------------------------- running service

def _systemd(tmp_path, bin_dir, record, state='active', hold_stop=None, gap=''):
    """A booted systemd whose systemctl logs each call, with the venv's content at that moment.

    With hold_stop, `stop` stops ucm, writes its pid to that file and execs a sleep waiting to be
    killed: one process, since a shell outlives a SIGINT that misses its child of the moment."""
    (tmp_path / 'run-systemd').mkdir()
    (tmp_path / 'ucm-state').write_text(state)
    venv = tmp_path / 'opt' / 'venv'
    hold = f'echo $$ > {hold_stop}; {gap}exec {shutil.which("sleep")} 600' if hold_stop else ':'
    _stub(bin_dir / 'systemctl', f"""echo "SYSTEMCTL $* [$({shutil.which('ls')} {venv} 2>/dev/null | tr '\\n' ' ')]" >> {record}
state=$(cat {tmp_path}/ucm-state)
case "$1" in
  is-active) [ "$state" = active ] ;;
  stop) echo inactive > {tmp_path}/ucm-state; {hold} ;;
  start|restart) echo active > {tmp_path}/ucm-state ;;
esac""")
    return {'PATH': str(bin_dir), 'UCM_SETUP_SYSTEMD_RUN': str(tmp_path / 'run-systemd')}


def test_a_held_stop_dies_of_a_sigint_its_shell_alone_receives(tmp_path):
    """The held stop execs its sleep in the shell's own pid: once the sleep runs, a SIGINT ends it,
    with no child left for the shell to wait for."""
    bin_dir = tmp_path / 'bin'
    held = tmp_path / 'held'
    _systemd(tmp_path, bin_dir, tmp_path / 'record', hold_stop=held)
    proc = subprocess.Popen([str(bin_dir / 'systemctl'), 'stop', 'ucm'], start_new_session=True,
                            preexec_fn=_default_signals)
    try:
        _wait_for_held_stop(held, proc)
        os.kill(proc.pid, signal.SIGINT)
        assert proc.wait(timeout=5) == -signal.SIGINT
    finally:
        try:
            os.killpg(proc.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        proc.wait()


def _calls(record):
    return [line.split(' [')[0] if line.startswith('SYSTEMCTL') else line.split()[0] + ' ' + line.split()[1]
            for line in record.read_text().splitlines() if line.startswith(('SYSTEMCTL', 'ARGS'))]


def test_a_running_service_is_stopped_only_once_its_new_venv_is_built(tmp_path):
    bin_dir, _ = _toolbox(tmp_path, rustc_in_path=None)
    python, record = _fake_python(tmp_path, 'exit 0')
    home, envfile = _home(tmp_path)
    envfile.write_text('SECRET_KEY=a\n')
    extra = _systemd(tmp_path, bin_dir, record)
    result = _run(['venv', str(home), str(python), 'deb', str(envfile)], _env(tmp_path, DEBIAN, extra))
    assert result.returncode == 0, result.stderr
    assert _calls(record) == ['ARGS install'] * 3 + ['SYSTEMCTL is-active --quiet ucm', 'SYSTEMCTL stop ucm']
    # Stopped while the previous venv is still in place
    assert 'SYSTEMCTL stop ucm [previous ]' in record.read_text()
    # Started again by the package script, after the permissions and the FIPS step
    assert (home / 'venv' / 'bin' / 'gunicorn').exists()
    assert not [c for c in _calls(record) if c.startswith('SYSTEMCTL start')]


@pytest.mark.parametrize('state, booted', [('inactive', True), ('active', False)])
def test_a_stopped_service_or_a_chroot_is_left_alone(tmp_path, state, booted):
    bin_dir, _ = _toolbox(tmp_path, rustc_in_path=None)
    python, record = _fake_python(tmp_path, 'exit 0')
    home, envfile = _home(tmp_path)
    envfile.write_text('SECRET_KEY=a\n')
    extra = _systemd(tmp_path, bin_dir, record, state)
    if not booted:
        extra.pop('UCM_SETUP_SYSTEMD_RUN')
    result = _run(['venv', str(home), str(python), 'deb', str(envfile)], _env(tmp_path, DEBIAN, extra))
    assert result.returncode == 0, result.stderr
    expected = ['SYSTEMCTL is-active --quiet ucm'] if booted else []
    assert [c for c in _calls(record) if c.startswith('SYSTEMCTL')] == expected


@pytest.mark.parametrize('fips', [True, False])
def test_the_service_runs_during_the_whole_build(tmp_path, fips):
    bin_dir, _ = _toolbox(tmp_path, rustc_in_path='1.92.0')
    python, record = _fake_python(tmp_path, 'exit 0')
    home, envfile = _home(tmp_path)
    if not fips:
        envfile.write_text('SECRET_KEY=a\n')
    _stub(home / 'venv' / 'bin' / 'pip')  # `pip show gssapi` succeeds: reinstalled too
    extra = _systemd(tmp_path, bin_dir, record)
    result = _run(['venv', str(home), str(python), 'rpm', str(envfile)], _env(tmp_path, ALMA, extra))
    assert result.returncode == 0, result.stderr
    lines = record.read_text().splitlines()
    # pip, requirements, pyjks, then the Kerberos reinstall
    assert [line for line in lines if line.startswith('UCM')] == ['UCM active'] * 4
    assert "ARGS install --quiet pyspnego[kerberos]" in lines
    calls = _calls(record)
    assert calls[-2:] == ['SYSTEMCTL is-active --quiet ucm', 'SYSTEMCTL stop ucm']
    assert all(c.startswith('ARGS') for c in calls[:-2])


def test_requests_kerberos_of_a_2x_venv_becomes_pyspnego_kerberos(tmp_path):
    """A 2.254 venv with requests-kerberos only: the Microsoft CA Kerberos sign-in now needs gssapi."""
    bin_dir, _ = _toolbox(tmp_path, rustc_in_path='1.92.0')
    python, record = _fake_python(tmp_path, 'exit 0')
    home, envfile = _home(tmp_path)
    envfile.write_text('SECRET_KEY=a\n')
    _stub(home / 'venv' / 'bin' / 'pip', 'case "$*" in "show gssapi") exit 1;; esac; exit 0')
    extra = _systemd(tmp_path, bin_dir, record)
    result = _run(['venv', str(home), str(python), 'deb', str(envfile)], _env(tmp_path, DEBIAN, extra))
    assert result.returncode == 0, result.stderr
    lines = record.read_text().splitlines()
    assert "ARGS install --quiet pyspnego[kerberos]" in lines
    assert not any('requests-kerberos' in line for line in lines if line.startswith('ARGS install'))
    calls = _calls(record)
    assert calls[-2:] == ['SYSTEMCTL is-active --quiet ucm', 'SYSTEMCTL stop ucm']
    assert all(c.startswith('ARGS') for c in calls[:-2])


def test_pykerberos_of_a_2x_venv_becomes_pyspnego_kerberos(tmp_path):
    """A 2.254 venv whose WinRM Kerberos came from pywinrm[kerberos] holds pykerberos alone."""
    bin_dir, _ = _toolbox(tmp_path, rustc_in_path='1.92.0')
    python, record = _fake_python(tmp_path, 'exit 0')
    home, envfile = _home(tmp_path)
    envfile.write_text('SECRET_KEY=a\n')
    _stub(home / 'venv' / 'bin' / 'pip', 'case "$*" in "show pykerberos") exit 0;; "show "*) exit 1;; esac; exit 0')
    result = _run(['venv', str(home), str(python), 'deb', str(envfile)], _env(tmp_path, DEBIAN, {'PATH': str(bin_dir)}))
    assert result.returncode == 0, result.stderr
    installs = [line for line in record.read_text().splitlines() if line.startswith('ARGS install')]
    assert installs == [
        'ARGS install --quiet --upgrade pip',
        f'ARGS install --quiet -r {home}/requirements.txt',
        'ARGS install --quiet --no-deps pyjks==20.0.0',
        'ARGS install --quiet pyspnego[kerberos]',
    ]


def test_a_venv_without_any_kerberos_library_gets_none(tmp_path):
    bin_dir, _ = _toolbox(tmp_path, rustc_in_path='1.92.0')
    python, record = _fake_python(tmp_path, 'exit 0')
    home, envfile = _home(tmp_path)
    envfile.write_text('SECRET_KEY=a\n')
    _stub(home / 'venv' / 'bin' / 'pip', 'case "$*" in "show "*) exit 1;; esac; exit 0')
    result = _run(['venv', str(home), str(python), 'deb', str(envfile)], _env(tmp_path, DEBIAN, {'PATH': str(bin_dir)}))
    assert result.returncode == 0, result.stderr
    assert not any('pyspnego' in line for line in record.read_text().splitlines())


@pytest.mark.parametrize('fips', [True, False])
def test_a_failed_build_never_stops_the_service(tmp_path, fips):
    """PyPI unreachable or a failed compilation: ucm goes on running the venv it had."""
    bin_dir, _ = _toolbox(tmp_path, rustc_in_path='1.92.0')
    python, record = _fake_python(tmp_path, 'case "$*" in *" -r "*) exit 1;; esac; exit 0')
    home, envfile = _home(tmp_path)
    if not fips:
        envfile.write_text('SECRET_KEY=a\n')
    shutil.rmtree(home / 'venv')
    _venv_dir(home / 'venv')
    extra = _systemd(tmp_path, bin_dir, record)
    result = _run(['venv', str(home), str(python), 'rpm', str(envfile)], _env(tmp_path, ALMA, extra))
    assert result.returncode != 0
    assert 'ARGS install' in _calls(record) and _systemctl_lines(record) == []
    assert (tmp_path / 'ucm-state').read_text().strip() == 'active'
    assert (home / 'venv' / 'good').exists()
    assert not (home / 'venv.prev').exists() and not (home / 'venv.next').exists()


def test_a_failed_build_without_a_working_previous_venv_starts_nothing(tmp_path):
    bin_dir, _ = _toolbox(tmp_path, rustc_in_path=None)
    python, record = _fake_python(tmp_path, 'case "$*" in *-r*) exit 1;; esac; exit 0')
    home, envfile = _home(tmp_path)
    envfile.write_text('SECRET_KEY=a\n')
    extra = _systemd(tmp_path, bin_dir, record)
    result = _run(['venv', str(home), str(python), 'deb', str(envfile)], _env(tmp_path, DEBIAN, extra))
    assert result.returncode != 0
    assert [c for c in _calls(record) if c.startswith('SYSTEMCTL')] == []


@pytest.mark.parametrize('fips', [True, False])
def test_the_final_venv_holds_no_path_of_venv_next(tmp_path, fips):
    """Shebangs, activate scripts and pyvenv.cfg name the final directory; a binary is left as it is."""
    bin_dir, _ = _toolbox(tmp_path, rustc_in_path='1.92.0')
    binary = b'\x7fELF\x00\x00 %s \x00'
    python, _ = _fake_python(tmp_path, 'case "$*" in *pyjks*) d=$(dirname "$0"); '
                                       'printf \'\\177ELF\\000\\000 %s \\000\' "${d%/bin}" > "$d/native";; esac')
    home, envfile = _home(tmp_path)
    if not fips:
        envfile.write_text('SECRET_KEY=a\n')
    result = _run(['venv', str(home), str(python), 'rpm', str(envfile)], _env(tmp_path, ALMA, {'PATH': str(bin_dir)}))
    assert result.returncode == 0, result.stderr
    venv = home / 'venv'
    assert not (home / 'venv.next').exists()
    assert (venv / 'bin' / 'gunicorn').read_text().splitlines()[0] == f'#!{venv}/bin/python'
    assert (venv / 'bin' / 'pip').read_text().splitlines()[0] == f'#!{venv}/bin/python'
    assert f'-m venv {venv} --prompt venv' in (venv / 'pyvenv.cfg').read_text()
    for name in ('activate', 'activate.csh', 'activate.fish'):
        assert f'"{venv}"' in (venv / 'bin' / name).read_text()
    texts = [f for f in venv.rglob('*') if f.is_file() and f.name != 'native']
    assert texts and not [f for f in texts if 'venv.next' in f.read_text()]
    assert (venv / 'bin' / 'native').read_bytes() == binary % str(home / 'venv.next').encode()
    assert _run(['venv-ok', str(home)], _env(tmp_path)).returncode == 0


@pytest.mark.parametrize('build', ['exit 0', 'case "$*" in *" -r "*) exit 1;; esac; exit 0'])
def test_a_leftover_venv_next_is_replaced(tmp_path, build):
    bin_dir, _ = _toolbox(tmp_path, rustc_in_path=None)
    python, _ = _fake_python(tmp_path, build)
    home, envfile = _home(tmp_path)
    envfile.write_text('SECRET_KEY=a\n')
    _venv_dir(home / 'venv.next', tag='stale')
    result = _run(['venv', str(home), str(python), 'deb', str(envfile)], _env(tmp_path, DEBIAN, {'PATH': str(bin_dir)}))
    assert (result.returncode == 0) is (build == 'exit 0'), result.stderr
    assert not (home / 'venv.next').exists() and not (home / 'venv' / 'stale').exists()
    assert (home / 'venv' / 'previous').exists() is (build != 'exit 0')


def _held_gunicorn(started, exit_code=None):
    """Fake pip body: the new venv's gunicorn creates `started` on --version and waits to be killed,
    or with exit_code, fails."""
    sleep = shutil.which('sleep')
    body = started.parent / f'gunicorn-body-{exit_code}'
    body.write_text('[ "$1" = --version ] || exit 0\n' + (
        f'exit {exit_code}\n' if exit_code is not None else
        f"trap 'kill $p 2>/dev/null; exit 1' TERM INT HUP\n{sleep} 30 & p=$!; touch {started}; wait $p\n"))
    return (f'case "$*" in *" -r "*) d=$(dirname "$0"); '
            f'{{ printf "#!$d/python\\n"; cat {body}; }} > "$d/gunicorn";; esac')


@pytest.mark.parametrize('sig', [signal.SIGTERM, signal.SIGINT, signal.SIGHUP])
@pytest.mark.parametrize('point', ['stopped', 'switched'])
def test_an_interruption_after_the_stop_restarts_the_service_on_the_previous_venv(tmp_path, sig, point):
    """Cut once ucm is stopped: before the switch (systemctl stop still running), or after it,
    while the new venv is being checked."""
    _cut_after_the_stop(tmp_path, sig, point)


def test_a_sigint_between_the_witness_and_the_held_stop_still_lands(tmp_path):
    """The window a slow machine opens: the fake's shell, waiting for a child that exits normally,
    outlives the SIGINT and then execs the sleep, which never gets it."""
    _cut_after_the_stop(tmp_path, signal.SIGINT, 'stopped',
                        gap=f"{shutil.which('sh')} -c 'trap \"\" INT; {shutil.which('sleep')} 1'; ")


def _cut_after_the_stop(tmp_path, sig, point, gap=''):
    bin_dir, _ = _toolbox(tmp_path, rustc_in_path=None)
    held = tmp_path / 'held'
    python, record = _fake_python(tmp_path, _held_gunicorn(held) if point == 'switched' else 'exit 0')
    home, envfile = _home(tmp_path)
    envfile.write_text('SECRET_KEY=a\n')
    shutil.rmtree(home / 'venv')
    _venv_dir(home / 'venv')
    extra = _systemd(tmp_path, bin_dir, record, hold_stop=held if point == 'stopped' else None, gap=gap)
    proc = _spawn(tmp_path, home, python, envfile, extra)
    (_wait_for_held_stop if point == 'stopped' else _wait_for)(held, proc)
    os.killpg(proc.pid, sig)
    _out, err = _reap(proc)
    assert proc.returncode != 0, err
    # The build was complete before the stop
    assert _calls(record)[:3] == ['ARGS install'] * 3
    assert (home / 'venv' / 'good').exists()
    assert not (home / 'venv.prev').exists() and not (home / 'venv.next').exists()
    assert _systemctl_lines(record) == RESTARTED
    assert (tmp_path / 'ucm-state').read_text().strip() == 'active'


def test_a_new_venv_that_does_not_start_is_rolled_back(tmp_path):
    bin_dir, _ = _toolbox(tmp_path, rustc_in_path=None)
    python, record = _fake_python(tmp_path, _held_gunicorn(tmp_path / 'unused', exit_code=1))
    home, envfile = _home(tmp_path)
    envfile.write_text('SECRET_KEY=a\n')
    shutil.rmtree(home / 'venv')
    _venv_dir(home / 'venv')
    extra = _systemd(tmp_path, bin_dir, record)
    result = _run(['venv', str(home), str(python), 'deb', str(envfile)], _env(tmp_path, DEBIAN, extra))
    assert result.returncode == 1
    assert 'the new Python environment does not start' in result.stderr
    assert 'Restored the previous Python environment.' in result.stderr
    assert (home / 'venv' / 'good').exists()
    assert not (home / 'venv.prev').exists() and not (home / 'venv.next').exists()
    assert _systemctl_lines(record) == RESTARTED


def test_a_first_install_cut_after_the_switch_leaves_no_venv(tmp_path):
    bin_dir, _ = _toolbox(tmp_path, rustc_in_path=None)
    held = tmp_path / 'held'
    python, _ = _fake_python(tmp_path, _held_gunicorn(held))
    home, envfile = _home(tmp_path)
    envfile.write_text('SECRET_KEY=a\n')
    shutil.rmtree(home / 'venv')
    proc = _spawn(tmp_path, home, python, envfile, {'PATH': str(bin_dir)})
    _wait_for(held, proc)
    assert (home / 'venv' / 'bin' / 'gunicorn').exists()  # switched, not yet checked
    os.killpg(proc.pid, signal.SIGTERM)
    _reap(proc)
    assert proc.returncode != 0
    assert not (home / 'venv').exists() and not (home / 'venv.next').exists()


def _default_signals():
    for sig in (signal.SIGINT, signal.SIGTERM, signal.SIGHUP):
        signal.signal(sig, signal.SIG_DFL)


@pytest.mark.parametrize('sig', [signal.SIGTERM, signal.SIGINT, signal.SIGHUP])
@pytest.mark.parametrize('step', ['*no-binary*', '*" -r "*', '*pyjks*'])
def test_an_interrupted_build_keeps_the_previous_venv_and_the_running_service(tmp_path, sig, step):
    """The signal reaches the whole process group while pip runs, as when dpkg or the updater is stopped.

    At the pyjks step the new venv already has gunicorn, yet it is incomplete."""
    fips = step == '*no-binary*'
    bin_dir, _ = _toolbox(tmp_path, rustc_in_path='1.92.0')
    started = tmp_path / 'pip-started'
    # Like pip finishing a write, the fake takes a moment to die and writes into its venv meanwhile.
    # `started` appears once the sleep exists and `wait` lets the trap run at once (a signal sent
    # before the sleep's fork waited 30 s); the trap kills the sleep, which ignores SIGINT in background.
    sleep = shutil.which('sleep')
    python, record = _fake_python(tmp_path, f'''case "$*" in {step})
  trap 'kill $p 2>/dev/null; {sleep} 0.3; : > "$(dirname "$0")/late"; exit 1' TERM INT HUP
  {sleep} 30 & p=$!; touch {started}; wait $p;;
esac; exit 0''')
    home, envfile = _home(tmp_path)
    if not fips:
        envfile.write_text('SECRET_KEY=a\n')
    shutil.rmtree(home / 'venv')
    _venv_dir(home / 'venv')
    extra = _systemd(tmp_path, bin_dir, record)
    proc = subprocess.Popen([BASH, str(SCRIPT), 'venv', str(home), str(python), 'rpm', str(envfile)],
                            env=_env(tmp_path, ALMA, extra), stdin=subprocess.DEVNULL,
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                            text=True, start_new_session=True, preexec_fn=_default_signals)
    deadline = time.monotonic() + 15
    while not started.exists() and proc.poll() is None and time.monotonic() < deadline:
        time.sleep(0.05)
    assert started.exists(), proc.communicate(timeout=5)
    os.killpg(proc.pid, sig)
    _out, err = _reap(proc)
    assert proc.returncode != 0, err
    assert (home / 'venv' / 'good').exists() and not (home / 'venv.prev').exists()
    assert not (home / 'venv' / 'bin' / 'late').exists() and not (home / 'venv.next').exists()
    assert _systemctl_lines(record) == []
    assert (tmp_path / 'ucm-state').read_text().strip() == 'active'


def test_a_failed_first_fips_build_leaves_no_venv_that_looks_usable(tmp_path):
    """Refused by the build or by verify_fips_venv, a venv with gunicorn must not stay behind."""
    bin_dir, _ = _toolbox(tmp_path, rustc_in_path='1.92.0')
    python, _ = _fake_python(tmp_path, 'case "$*" in *no-binary*) exit 1;; esac; exit 0')
    home, envfile = _home(tmp_path)
    shutil.rmtree(home / 'venv')
    result = _run(['venv', str(home), str(python), 'rpm', str(envfile)], _env(tmp_path, ALMA, {'PATH': str(bin_dir)}))
    assert result.returncode == 1
    assert _run(['venv-ok', str(home)], _env(tmp_path)).returncode != 0
    assert not (home / 'venv.next').exists()


def _reap(proc, timeout=20, pipes=True):
    """communicate() (or wait() once the pipes are closed); on a timeout, fail with what
    was still running in the script's session and what it printed, then kill it."""
    try:
        return proc.communicate(timeout=timeout) if pipes else (proc.wait(timeout=timeout), None)
    except subprocess.TimeoutExpired:
        tree = subprocess.run(['ps', '-ww', '-o', 'pid,ppid,pgid,stat,etime,args', '-s', str(proc.pid)],
                              capture_output=True, text=True).stdout
        os.killpg(proc.pid, signal.SIGKILL)
        try:
            out, err = proc.communicate(timeout=10) if pipes else ('', '')
        except subprocess.TimeoutExpired:  # a child outside the session still holds the pipes
            out, err = '(pipes still held open)', ''
        pytest.fail(f'script still running after {timeout} s\n--- processes\n{tree}'
                    f'--- stdout\n{out}\n--- stderr\n{err}')


def _slow_pip(step, started):
    """Fake pip body that sleeps at the given step and, like pip, takes a moment to die."""
    sleep = shutil.which('sleep')
    return f'''case "$*" in {step})
  trap 'kill $p 2>/dev/null; {sleep} 0.3; : > "$(dirname "$0")/late"; exit 1' TERM INT HUP
  {sleep} 30 & p=$!; touch {started}; wait $p;;
esac; exit 0'''


def _spawn(tmp_path, home, python, envfile, extra, stderr=subprocess.PIPE):
    return subprocess.Popen([BASH, str(SCRIPT), 'venv', str(home), str(python), 'rpm', str(envfile)],
                            env=_env(tmp_path, ALMA, extra), stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                            stderr=stderr, text=True, start_new_session=True, preexec_fn=_default_signals)


def _wait_for(path, proc):
    deadline = time.monotonic() + 15
    while not path.exists() and proc.poll() is None and time.monotonic() < deadline:
        time.sleep(0.05)
    assert path.exists(), proc.communicate(timeout=5)


def _wait_for_held_stop(witness, proc, timeout=15):
    """Until the held `systemctl stop` runs the sleep: before its exec, a SIGINT can reach its shell
    while that waits for a child exiting normally, and the shell then goes on to the sleep."""
    deadline = time.monotonic() + timeout
    while proc.poll() is None and time.monotonic() < deadline:
        try:
            if pathlib.Path(f'/proc/{int(witness.read_text())}/comm').read_text().strip() == 'sleep':
                return
        except (OSError, ValueError):  # not written yet, or written halfway
            pass
        time.sleep(0.05)
    if proc.poll() is None:  # the script and its held stop would otherwise outlive the test
        os.killpg(proc.pid, signal.SIGKILL)
    try:
        said = proc.communicate(timeout=5)
    except subprocess.TimeoutExpired:
        said = '(pipes still held open)'
    pytest.fail(f'the held stop never reached its sleep: {said}')


def test_a_stop_that_never_holds_fails_the_wait_and_leaves_no_process(tmp_path):
    proc = subprocess.Popen([shutil.which('sleep'), '600'], start_new_session=True, stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE, text=True)
    try:
        with pytest.raises(pytest.fail.Exception, match='never reached its sleep'):
            _wait_for_held_stop(tmp_path / 'held', proc, timeout=0.3)
        assert proc.poll() is not None
    finally:
        # A failing assertion must not leave the sleep behind either
        if proc.poll() is None:
            os.killpg(proc.pid, signal.SIGKILL)
            proc.wait(timeout=5)
        proc.communicate(timeout=5)


def _systemctl_lines(record):
    return [line for line in record.read_text().splitlines() if line.startswith('SYSTEMCTL')]


RESTARTED = ['SYSTEMCTL is-active --quiet ucm [bin good ]', 'SYSTEMCTL stop ucm [bin good ]',
             'SYSTEMCTL reset-failed ucm [bin good ]', 'SYSTEMCTL start ucm [bin good ]']


@pytest.mark.parametrize('trigger', ['pip fails', 'SIGHUP', 'SIGHUP after the switch', 'new venv fails'])
def test_a_dead_terminal_does_not_cut_the_recovery_short(tmp_path, trigger):
    """After an SSH disconnection every write to the terminal fails; the recovery must still finish."""
    bin_dir, _ = _toolbox(tmp_path, rustc_in_path=None)
    started = tmp_path / 'pip-started'
    body = {'pip fails': 'case "$*" in *" -r "*) exit 1;; esac; exit 0',
            'SIGHUP': _slow_pip('*" -r "*', started),
            'SIGHUP after the switch': _held_gunicorn(started),
            'new venv fails': _held_gunicorn(started, exit_code=1)}[trigger]
    python, record = _fake_python(tmp_path, body)
    home, envfile = _home(tmp_path)
    envfile.write_text('SECRET_KEY=a\n')
    shutil.rmtree(home / 'venv')
    _venv_dir(home / 'venv')
    extra = _systemd(tmp_path, bin_dir, record)
    with open('/dev/full', 'w') as dead:
        proc = _spawn(tmp_path, home, python, envfile, extra, stderr=dead)
        if trigger.startswith('SIGHUP'):
            _wait_for(started, proc)
            os.killpg(proc.pid, signal.SIGHUP)
        _reap(proc)
    assert proc.returncode != 0
    assert (home / 'venv' / 'good').exists() and not (home / 'venv.prev').exists()
    assert not (home / 'venv.next').exists()
    stopped = trigger in ('SIGHUP after the switch', 'new venv fails')
    assert _systemctl_lines(record) == (RESTARTED if stopped else [])


@pytest.mark.parametrize('case', ['standard pip fails', 'fips build succeeds', 'kerberos reinstall'])
def test_a_closed_session_does_not_cost_the_service(tmp_path, case):
    """ssh without a tty, or a pipe reader that dies: every later write raises SIGPIPE.

    With Kerberos support in the previous venv, bash writes before the switch."""
    fips = case == 'fips build succeeds'
    bin_dir, _ = _toolbox(tmp_path, rustc_in_path='1.92.0')
    started, go = tmp_path / 'pip-started', tmp_path / 'go'
    step = '*no-binary*' if fips else '*" -r "*'
    wait = f'while [ ! -e {go} ]; do {shutil.which("sleep")} 0.05; done'
    python, record = _fake_python(tmp_path, f'case "$*" in {step}) touch {started}; {wait}; '
                                            f'exit {1 if case == "standard pip fails" else 0};; esac; exit 0')
    home, envfile = _home(tmp_path)
    if not fips:
        envfile.write_text('SECRET_KEY=a\n')
    shutil.rmtree(home / 'venv')
    _venv_dir(home / 'venv')
    if case == 'kerberos reinstall':
        _stub(home / 'venv' / 'bin' / 'pip')  # `pip show gssapi` succeeds
    extra = _systemd(tmp_path, bin_dir, record)
    proc = _spawn(tmp_path, home, python, envfile, extra)
    _wait_for(started, proc)
    proc.stdout.close()
    proc.stderr.close()
    go.touch()
    _reap(proc, pipes=False)
    # The first write after the build ("Stopping UCM", "Reinstalling") ends the run before the stop:
    # ucm goes on running the previous venv
    assert proc.returncode == (141 if case != 'standard pip fails' else 1)
    assert (home / 'venv' / 'good').exists()
    assert _systemctl_lines(record) == (RESTARTED[:1] if fips else [])
    assert (tmp_path / 'ucm-state').read_text().strip() == 'active'
    if fips:
        # The build itself succeeded: the update is reported as cut short, not as a failed build
        report = _build_ok(tmp_path, envfile)
        assert report.returncode == 1 and 'did not complete' in report.stderr
        assert 'build failed' not in report.stderr
    assert not (home / 'venv.prev').exists() and not (home / 'venv.next').exists()


def test_a_signal_while_the_previous_venv_is_dropped_keeps_the_new_one(tmp_path):
    """The build is complete once the drop of venv.prev starts: an interruption must not undo it."""
    bin_dir, _ = _toolbox(tmp_path, rustc_in_path=None)
    removing = tmp_path / 'rm-started'
    (bin_dir / 'rm').unlink()
    _stub(bin_dir / 'rm', f'case "$2" in */venv.prev) if [ -d "$2" ]; then {shutil.which("rm")} -f "$2/bin/gunicorn"; '
                          f'touch {removing}; {shutil.which("sleep")} 1; fi;; esac\nexec {shutil.which("rm")} "$@"')
    python, record = _fake_python(tmp_path, 'exit 0')
    home, envfile = _home(tmp_path)
    envfile.write_text('SECRET_KEY=a\n')
    shutil.rmtree(home / 'venv')
    _venv_dir(home / 'venv')
    extra = _systemd(tmp_path, bin_dir, record)
    proc = _spawn(tmp_path, home, python, envfile, extra)
    _wait_for(removing, proc)
    os.killpg(proc.pid, signal.SIGINT)
    _reap(proc)
    assert (home / 'venv' / 'bin' / 'gunicorn').exists() and not (home / 'venv' / 'good').exists()
    assert _systemctl_lines(record)[-1].startswith('SYSTEMCTL start ucm')


def test_a_malformed_requirements_file_leaves_no_temporary_file(tmp_path):
    bin_dir, _ = _toolbox(tmp_path, rustc_in_path='1.92.0')
    python, _ = _fake_python(tmp_path, 'exit 0')
    home, envfile = _home(tmp_path)
    (home / 'requirements.txt').write_text('cryptography==50.0.2\n')
    tmpdir = tmp_path / 'tmp'
    tmpdir.mkdir()
    result = _run(['venv', str(home), str(python), 'rpm', str(envfile)],
                  _env(tmp_path, ALMA, {'PATH': str(bin_dir), 'TMPDIR': str(tmpdir)}))
    assert result.returncode == 1 and 'psycopg[binary] not found once' in result.stderr
    assert list(tmpdir.iterdir()) == [] and (home / 'venv' / 'previous').exists()


def test_a_second_signal_does_not_cut_the_recovery_short(tmp_path):
    """Ctrl-C pressed again while the new venv, cut after the switch, is being removed."""
    bin_dir, _ = _toolbox(tmp_path, rustc_in_path=None)
    started, removing = tmp_path / 'held', tmp_path / 'rm-started'
    (bin_dir / 'rm').unlink()
    _stub(bin_dir / 'rm', f'[ "$*" = "-rf {tmp_path}/opt/venv" ] && {{ touch {removing}; {shutil.which("sleep")} 1; }}\n'
                          f'exec {shutil.which("rm")} "$@"')
    python, record = _fake_python(tmp_path, _held_gunicorn(started))
    home, envfile = _home(tmp_path)
    envfile.write_text('SECRET_KEY=a\n')
    shutil.rmtree(home / 'venv')
    _venv_dir(home / 'venv')
    extra = _systemd(tmp_path, bin_dir, record)
    proc = _spawn(tmp_path, home, python, envfile, extra)
    _wait_for(started, proc)
    os.killpg(proc.pid, signal.SIGINT)
    _wait_for(removing, proc)
    os.killpg(proc.pid, signal.SIGINT)
    _reap(proc)
    assert proc.returncode != 0
    assert (home / 'venv' / 'good').exists() and not (home / 'venv.prev').exists()
    assert _systemctl_lines(record) == RESTARTED


@pytest.mark.parametrize('trigger', ['pip fails', 'SIGTERM'])
def test_an_incomplete_first_venv_does_not_pass_venv_ok(tmp_path, trigger):
    """Cut at the last pip step, a first install's venv already has gunicorn: it must go."""
    bin_dir, _ = _toolbox(tmp_path, rustc_in_path=None)
    started = tmp_path / 'pip-started'
    body = (f'{GUNICORN}\ncase "$*" in *pyjks*) exit 1;; esac; exit 0' if trigger == 'pip fails'
            else _slow_pip('*pyjks*', started))
    python, _ = _fake_python(tmp_path, body)
    home, envfile = _home(tmp_path)
    envfile.write_text('SECRET_KEY=a\n')
    shutil.rmtree(home / 'venv')
    proc = _spawn(tmp_path, home, python, envfile, {'PATH': str(bin_dir)})
    if trigger == 'SIGTERM':
        _wait_for(started, proc)
        os.killpg(proc.pid, signal.SIGTERM)
    _reap(proc)
    assert proc.returncode != 0
    assert _run(['venv-ok', str(home)], _env(tmp_path)).returncode != 0


def test_a_failed_fips_build_reports_the_restore_after_doing_it(tmp_path):
    bin_dir, _ = _toolbox(tmp_path, rustc_in_path='1.92.0')
    python, _ = _fake_python(tmp_path, 'case "$*" in *no-binary*) exit 1;; esac; exit 0')
    home, envfile = _home(tmp_path)
    result = _run(['venv', str(home), str(python), 'rpm', str(envfile)], _env(tmp_path, ALMA, {'PATH': str(bin_dir)}))
    assert result.returncode == 1
    err = result.stderr
    assert err.index('the UCM_FIPS_BUILD=1 build failed') < err.index('Kept the previous Python environment.')
    assert (home / 'venv' / 'previous').exists()


def test_an_interrupted_fips_build_leaves_no_temporary_file(tmp_path):
    bin_dir, _ = _toolbox(tmp_path, rustc_in_path='1.92.0')
    started = tmp_path / 'pip-started'
    python, _ = _fake_python(tmp_path, _slow_pip('*no-binary*', started))
    home, envfile = _home(tmp_path)
    tmpdir = tmp_path / 'tmp'
    tmpdir.mkdir()
    proc = _spawn(tmp_path, home, python, envfile, {'PATH': str(bin_dir), 'TMPDIR': str(tmpdir)})
    _wait_for(started, proc)
    assert list(tmpdir.iterdir())  # the requirements copy exists during the build
    os.killpg(proc.pid, signal.SIGTERM)
    _reap(proc)
    assert list(tmpdir.iterdir()) == []


def test_missing_build_tools_never_stop_the_service(tmp_path):
    bin_dir, _ = _toolbox(tmp_path, rustc_in_path=None)
    python, record = _fake_python(tmp_path, 'exit 0')
    home, envfile = _home(tmp_path)
    extra = _systemd(tmp_path, bin_dir, record)
    result = _run(['venv', str(home), str(python), 'deb', str(envfile)], _env(tmp_path, UBUNTU, extra))
    assert result.returncode == 1 and 'cargo/rustc>=1.83' in result.stderr
    assert not record.exists() and (tmp_path / 'ucm-state').read_text() == 'active'


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
    # Shown in the UI: the next step is the update, not a package manager command
    assert 'then run the update again.' in result.stderr
    assert 'dpkg --configure' not in result.stderr and 'dnf reinstall' not in result.stderr


@pytest.mark.parametrize('rustc, cleared', [('1.92.0', True), (None, False)])
def test_a_passed_precheck_clears_the_failure_of_an_earlier_attempt(tmp_path, rustc, cleared):
    """The watcher then blames on this update only a marker its own install left."""
    envfile = tmp_path / 'ucm.env'
    envfile.write_text('UCM_FIPS_BUILD=1\n')
    marker = tmp_path / 'log' / 'fips-build.failed'
    marker.parent.mkdir()
    marker.write_text('build failed')
    result = _precheck(tmp_path, envfile, _stub(tmp_path / 'python3.12'), rustc_in_path=rustc)
    assert (result.returncode == 0) is cleared, result.stderr
    assert marker.exists() is not cleared


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
    (UBUNTU, 'sudo pro enable fips '),
])
def test_a_host_outside_fips_mode_is_told_how_to_enable_it(tmp_path, os_release, command):
    envfile = tmp_path / 'ucm.env'
    envfile.write_text('UCM_FIPS_BUILD=1\n')
    result = _finish(tmp_path, envfile, 0, os_release)
    assert result.returncode == 0
    assert 'not in FIPS mode' in result.stdout and command in result.stdout
    assert 'fips-updates' not in result.stdout
    assert 'UCM_FIPS=' not in envfile.read_text().replace('UCM_FIPS_BUILD=', '')


def test_a_generated_secret_never_appears_in_a_command_line(tmp_path):
    """Every external command is wrapped and logs its argv; the secret must not be there."""
    secret = 'cd' * 32
    bin_dir = tmp_path / 'bin'
    log = tmp_path / 'argv.log'
    for util in UTILS + ('mktemp', 'rm', 'cat', 'stat'):
        real = shutil.which(util)
        if real and util != 'openssl':
            _stub(bin_dir / util, f'printf "%s\\n" "$0 $*" >> {log}\nexec {real} "$@"')
    _stub(bin_dir / 'openssl', f'echo {secret}')
    envfile = tmp_path / 'ucm.env'
    envfile.write_text('SECRET_KEY=\nJWT_SECRET_KEY=\n')
    result = _run(['env', str(envfile), '/d'], _env(tmp_path, extra={'PATH': str(bin_dir)}))
    assert result.returncode == 0, result.stderr
    assert _values(envfile)['SECRET_KEY'] == [secret]
    assert log.exists() and secret not in log.read_text()


# ----------------------------------------------------------------- banner

def _banner(tmp_path, pkg, softhsm=False,
            hostname='[ "$1" = -I ] && echo "192.0.2.10 2001:db8::10 " || echo ucm.example.test',
            env_text='HTTPS_PORT=9443\nINITIAL_ADMIN_PASSWORD=s3cret\n'):
    bin_dir = tmp_path / 'bin'
    _stub(bin_dir / 'hostname', hostname)
    status = 'install ok installed' if softhsm is True else softhsm
    _stub(bin_dir / 'dpkg-query', f'[ "$*" = \'-W -f=${{Status}} softhsm2\' ] && printf %s \'{status}\'' if softhsm else 'exit 1')
    _stub(bin_dir / 'dpkg', 'exit 1')
    _stub(bin_dir / 'rpm', '[ "$*" = "-q softhsm" ]' if softhsm else 'exit 1')
    envfile = tmp_path / 'ucm.env'
    envfile.write_text(env_text)
    path = f"{bin_dir}:{os.environ.get('PATH', '/usr/bin:/bin')}"
    return envfile, _run(['banner', str(envfile), pkg], _env(tmp_path, extra={'PATH': path}))


def test_the_banner_brackets_ipv6_addresses(tmp_path):
    envfile, result = _banner(tmp_path, 'deb')
    assert result.returncode == 0, result.stderr
    urls = [line.split()[-1] for line in result.stdout.splitlines() if 'https://' in line]
    assert urls == ['https://ucm.example.test:9443', 'https://192.0.2.10:9443', 'https://[2001:db8::10]:9443']
    assert f' Password: the one you provided (INITIAL_ADMIN_PASSWORD in {envfile})' in result.stdout
    assert 's3cret' not in result.stdout
    assert f' Config:   {envfile}' in result.stdout


@pytest.mark.parametrize('env_text, path', [
    ('HTTPS_PORT=9443\nDATA_DIR=/srv/ucm\n', '/srv/ucm/initial-admin-password'),
    ('HTTPS_PORT=9443\nINITIAL_ADMIN_PASSWORD=\n', '/opt/ucm/data/initial-admin-password'),
])
def test_the_banner_says_where_the_generated_password_will_be(tmp_path, env_text, path):
    _, result = _banner(tmp_path, 'deb', env_text=env_text)
    assert result.returncode == 0, result.stderr
    assert f'sudo cat {path}' in result.stdout
    assert 'changeme123' not in result.stdout


def test_the_banner_names_a_password_file(tmp_path):
    _, result = _banner(tmp_path, 'rpm', env_text='INITIAL_ADMIN_PASSWORD_FILE=/root/admin.pw\n')
    assert ' Password: the one you provided (INITIAL_ADMIN_PASSWORD_FILE=/root/admin.pw)' in result.stdout


@pytest.mark.parametrize('pkg, softhsm, line', [
    ('deb', True, '  [ok] softhsm2 (HSM support)'),
    # Unpacked by the same apt run, configured after ucm
    ('deb', 'install ok unpacked', '  [ok] softhsm2 (HSM support)'),
    ('deb', 'install ok half-configured', '  [ok] softhsm2 (HSM support)'),
    ('deb', 'install ok triggers-awaited', '  [ok] softhsm2 (HSM support)'),
    ('deb', 'install ok triggers-pending', '  [ok] softhsm2 (HSM support)'),
    ('deb', 'hold ok installed', '  [ok] softhsm2 (HSM support)'),
    ('deb', 'deinstall ok config-files', '  [ ]  softhsm2 - HSM support (apt install softhsm2)'),
    ('deb', 'unknown ok not-installed', '  [ ]  softhsm2 - HSM support (apt install softhsm2)'),
    ('deb', False, '  [ ]  softhsm2 - HSM support (apt install softhsm2)'),
    ('rpm', True, '  [ok] softhsm (HSM support)'),
    ('rpm', False, '  [ ]  softhsm - HSM support (dnf install softhsm)'),
])
def test_the_banner_names_the_hsm_package_of_the_distribution(tmp_path, pkg, softhsm, line):
    _, result = _banner(tmp_path, pkg, softhsm)
    assert result.returncode == 0, result.stderr
    assert line in result.stdout.splitlines()


def test_a_failed_host_lookup_does_not_cut_the_banner_short(tmp_path):
    _, result = _banner(tmp_path, 'rpm', hostname='exit 127')
    assert result.returncode == 0, result.stderr
    assert ' Admin:    admin' in result.stdout
    assert result.stdout.rstrip().endswith('============================================')


def test_a_failed_write_leaves_no_copy_of_the_secret(tmp_path):
    bin_dir = tmp_path / 'bin'
    for util in UTILS:
        real = shutil.which(util)
        if real and util != 'openssl':
            (bin_dir / util).parent.mkdir(parents=True, exist_ok=True)
            (bin_dir / util).symlink_to(real)
    _stub(bin_dir / 'openssl', f'echo {"ef" * 32}')
    # The final rename fails (a full disk, say)
    failing = _stub(tmp_path / 'failing-python',
                    'code=$3; shift 3\n'
                    f'exec {sys.executable} -I -c "import os'
                    '\ndef rename(*a, **k): raise OSError(28, \'No space left on device\')'
                    '\nos.rename = rename\n$code" "$@"')
    conf = tmp_path / 'etc'
    conf.mkdir()
    envfile = conf / 'ucm.env'
    envfile.write_text('SECRET_KEY=\n')
    result = _run(['env', str(envfile), '/d'],
                  _env(tmp_path, extra={'PATH': str(bin_dir), 'UCM_PYTHON': str(failing)}))
    assert result.returncode != 0
    assert [p.name for p in conf.iterdir()] == ['ucm.env'] and envfile.read_text() == 'SECRET_KEY=\n'


def _sourced_banner(tmp_path, env_text):
    """cmd_banner and the helpers it calls, sourced alone: the script itself never runs."""
    import re as _re
    body = SCRIPT.read_text(encoding='utf-8')
    def function(name):
        one_line = _re.search(rf'^{name}\(\) \{{ .*\}}$', body, _re.M)
        return (one_line or _re.search(rf'^{name}\(\) \{{\n.*?^\}}$', body, _re.M | _re.S)).group(0)
    helper = _re.search(r"^OWN_PY='\n.*?^'$", body, _re.M | _re.S).group(0)
    funcs = '\n'.join([helper] + [function(name) for name in ('own', 'env_value', 'env_has', 'cmd_banner')])
    bin_dir = tmp_path / 'bin'
    bin_dir.mkdir()
    for tool, script in (('hostname', 'echo ucm.example.test'), ('dpkg-query', 'exit 1'), ('rpm', 'exit 1')):
        (bin_dir / tool).write_text(f'#!/bin/sh\n{script}\n')
        (bin_dir / tool).chmod(0o755)
    envfile = tmp_path / 'ucm.env'
    envfile.write_text(env_text)
    return subprocess.run([BASH, '-c', funcs + f'\ncmd_banner {envfile} deb'],
                          env={'PATH': f'{bin_dir}:/usr/bin:/bin'}, capture_output=True, text=True)


def test_the_banner_says_both_sources_refuse_the_start(tmp_path):
    result = _sourced_banner(tmp_path, 'INITIAL_ADMIN_PASSWORD=Op-Chosen-1!\n'
                                       'INITIAL_ADMIN_PASSWORD_FILE=/root/admin.pw\n')
    assert result.returncode == 0, result.stderr
    assert 'both set' in result.stdout and 'refused' in result.stdout
    assert 'the one you provided' not in result.stdout and 'Op-Chosen-1!' not in result.stdout


def test_the_banner_names_the_configured_administrator(tmp_path):
    result = _sourced_banner(tmp_path, 'INITIAL_ADMIN_USERNAME=operator\n')
    assert result.returncode == 0, result.stderr
    assert ' Admin:    operator' in result.stdout


# ----------------------------------------------------------------- without hostname

def _path_without_hostname(tmp_path):
    """Every command of the host but hostname, as on a Fedora 43 image without it."""
    bin_dir = tmp_path / 'nohostname'
    bin_dir.mkdir()
    for d in ('/usr/local/bin', '/usr/bin', '/bin', '/usr/sbin', '/sbin'):
        if not os.path.isdir(d):
            continue
        for name in os.listdir(d):
            target = bin_dir / name
            if name != 'hostname' and not target.exists() and not target.is_symlink():
                os.symlink(os.path.join(d, name), target)
    return str(bin_dir)


def test_without_hostname_the_banner_and_the_name_come_from_uname(tmp_path):
    path = _path_without_hostname(tmp_path)
    name = os.uname().nodename
    result = _run(['host-name'], _env(tmp_path, extra={'PATH': path}))
    assert (result.returncode, result.stdout, result.stderr) == (0, f'{name}\n', '')
    envfile = tmp_path / 'ucm.env'
    envfile.write_text('HTTPS_PORT=9443\n')
    result = _run(['banner', str(envfile), 'rpm'], _env(tmp_path, extra={'PATH': path}))
    assert result.returncode == 0 and 'command not found' not in result.stderr, result.stderr
    assert f' Access:   https://{name}:9443' in result.stdout, result.stdout


def test_with_hostname_its_fully_qualified_name_comes_first(tmp_path):
    bin_dir = tmp_path / 'bin'
    _stub(bin_dir / 'hostname', '[ "$1" = -f ] && echo ucm.example.test || echo ucm')
    result = _run(['host-name'], _env(tmp_path, extra={'PATH': f"{bin_dir}:{os.environ.get('PATH', '/usr/bin:/bin')}"}))
    assert result.stdout == 'ucm.example.test\n'


# ------------------------------------------------------------ HTTPS certificate

def _owner():
    import grp
    import pwd
    return pwd.getpwuid(os.getuid()).pw_name, grp.getgrgid(os.getgid()).gr_name


def _https_cert(tmp_path, data, fqdn='ucm.example.test'):
    """The host's name is stubbed: a build machine's own can be anything."""
    user, group = _owner()
    bin_dir = tmp_path / 'hostbin'
    _stub(bin_dir / 'hostname', f'case "$1" in -f) echo {fqdn};; -I) echo 192.0.2.7;; *) echo {fqdn.split(".")[0]};; esac')
    path = f"{bin_dir}:{os.environ.get('PATH', '/usr/bin:/bin')}"
    return _run(['https-cert', str(data), user, group], _env(tmp_path, extra={'PATH': path}))


def _cert_names(cert):
    from cryptography import x509
    parsed = x509.load_pem_x509_certificate(cert.read_bytes())
    cn = parsed.subject.get_attributes_for_oid(x509.NameOID.COMMON_NAME)[0].value
    san = parsed.extensions.get_extension_for_class(x509.SubjectAlternativeName).value
    return cn, san.get_values_for_type(x509.DNSName)


def test_a_name_past_64_characters_keeps_its_first_label_as_common_name(tmp_path):
    """A common name holds 64 characters (RFC 5280 ub-common-name); the full name stays in the SAN."""
    fqdn = 'runnervm0abcd1.x2yz3abcdefghijklmnopqrstuvwx.bx.internal.cloudapp.net'
    assert len(fqdn) > 64
    data = tmp_path / 'data'
    data.mkdir()
    result = _https_cert(tmp_path, data, fqdn=fqdn)
    assert result.returncode == 0, result.stderr
    cn, dns = _cert_names(data / 'https_cert.pem')
    assert cn == 'runnervm0abcd1' and dns == [fqdn, 'localhost']


@pytest.mark.parametrize('fqdn', ['l' * 70 + '.example.test', 'n' * 70])
def test_a_first_label_past_64_characters_is_cut_at_64(tmp_path, fqdn):
    data = tmp_path / 'data'
    data.mkdir()
    result = _https_cert(tmp_path, data, fqdn=fqdn)
    assert result.returncode == 0, result.stderr
    assert _cert_names(data / 'https_cert.pem') == (fqdn[:64], [fqdn, 'localhost'])


def test_an_openssl_failure_says_why(tmp_path):
    data = tmp_path / 'data'
    data.mkdir()
    _stub(tmp_path / 'hostbin' / 'openssl', 'echo "..+++++*" >&2; echo "-----" >&2; echo "unable to load provider" >&2; exit 1')
    result = _https_cert(tmp_path, data)
    assert result.returncode != 0, result.stderr
    assert result.stderr.strip() == 'ERROR: HTTPS certificate not generated: unable to load provider', result.stderr
    assert not (data / 'https_cert.pem').exists()


def test_a_short_name_is_the_common_name(tmp_path):
    data = tmp_path / 'data'
    data.mkdir()
    assert _https_cert(tmp_path, data).returncode == 0
    assert _cert_names(data / 'https_cert.pem') == ('ucm.example.test', ['ucm.example.test', 'localhost'])


def test_a_missing_certificate_is_generated_with_its_modes(tmp_path):
    data = tmp_path / 'data'
    data.mkdir()
    result = _https_cert(tmp_path, data)
    assert result.returncode == 0, result.stderr
    key, cert = data / 'https_key.pem', data / 'https_cert.pem'
    assert key.read_text().startswith('-----BEGIN PRIVATE KEY-----')
    assert cert.read_text().startswith('-----BEGIN CERTIFICATE-----')
    assert stat.S_IMODE(key.stat().st_mode) == 0o600 and stat.S_IMODE(cert.stat().st_mode) == 0o644
    assert key.stat().st_uid == os.getuid() and cert.stat().st_gid == os.getgid()


@pytest.mark.parametrize('name', ['https_key.pem', 'https_cert.pem'])
def test_a_link_the_service_account_laid_is_replaced_not_written_through(tmp_path, name):
    """Root generates while the service account owns the data directory: its link leads nowhere."""
    data = tmp_path / 'data'
    data.mkdir()
    victim = tmp_path / 'passwd'
    victim.write_text('root:x:0:0::/root:/bin/bash\n')
    victim.chmod(0o644)
    if name == 'https_cert.pem':
        # Dangling for [ -f ]: a link to a file that is not there yet
        (data / name).symlink_to(tmp_path / 'absent')
    else:
        (data / name).symlink_to(victim)
    result = _https_cert(tmp_path, data)
    assert result.returncode == 0, result.stderr
    assert victim.read_text() == 'root:x:0:0::/root:/bin/bash\n'
    assert stat.S_IMODE(victim.stat().st_mode) == 0o644
    assert not (tmp_path / 'absent').exists()
    for f in ('https_key.pem', 'https_cert.pem'):
        assert not (data / f).is_symlink() and stat.S_ISREG((data / f).lstat().st_mode), f
    assert stat.S_IMODE((data / 'https_key.pem').stat().st_mode) == 0o600


def test_an_existing_certificate_is_kept(tmp_path):
    data = tmp_path / 'data'
    data.mkdir()
    (data / 'https_cert.pem').write_text('operator cert')
    (data / 'https_key.pem').write_text('operator key')
    result = _https_cert(tmp_path, data)
    assert result.returncode == 0, result.stderr
    assert (data / 'https_key.pem').read_text() == 'operator key'
    assert (data / 'https_cert.pem').read_text() == 'operator cert'


def test_without_hostname_the_certificate_is_named_from_uname(tmp_path):
    data = tmp_path / 'data'
    data.mkdir()
    user, group = _owner()
    result = _run(['https-cert', str(data), user, group],
                  _env(tmp_path, extra={'PATH': _path_without_hostname(tmp_path)}))
    assert result.returncode == 0, result.stderr
    subject = subprocess.run(['openssl', 'x509', '-noout', '-subject', '-in', str(data / 'https_cert.pem')],
                             capture_output=True, text=True).stdout
    assert subject.replace(' ', '').startswith(f'subject=CN={os.uname().nodename},O=UCM'), subject


# ---------------------------------------------------- ucm.env as a link

def _env_victim(tmp_path, body='root ALL=(ALL:ALL) ALL\n'):
    victim = tmp_path / 'sudoers'
    victim.write_text(body)
    # Writable by its owner: the tests may run as any user
    victim.chmod(0o640)
    return victim


@pytest.mark.parametrize('command', [['env', '/opt/ucm/data'], ['env-ensure', 'DATA_DIR', '/d'], ['env-check']])
def test_a_ucm_env_link_is_refused_and_its_target_untouched(tmp_path, command):
    victim = _env_victim(tmp_path, 'UCM_FIPS_BUILD=1\n')
    envfile = tmp_path / 'ucm.env'
    envfile.symlink_to(victim)
    result = _run([command[0], str(envfile), *command[1:]], _env(tmp_path, extra={'UCM_FIPS_BUILD': '1'}))
    assert result.returncode == 1
    assert 'symbolic link or not a regular file' in result.stderr
    assert victim.read_text() == 'UCM_FIPS_BUILD=1\n' and stat.S_IMODE(victim.stat().st_mode) == 0o640
    assert envfile.is_symlink()


@pytest.mark.parametrize('command', [['env', '/opt/ucm/data'], ['env-ensure', 'DATA_DIR', '/d'], ['env-check']])
def test_a_hard_linked_ucm_env_is_refused_with_its_remedy(tmp_path, command):
    """A second name of a root file: refused like a link, before any read, with the same remedy."""
    victim = _env_victim(tmp_path, 'UCM_FIPS_BUILD=1\n')
    envfile = tmp_path / 'ucm.env'
    os.link(victim, envfile)
    result = _run([command[0], str(envfile), *command[1:]], _env(tmp_path))
    assert result.returncode == 1
    assert f'{envfile} is a hard link to another file: replace it with a regular file, then install again' \
        in result.stderr, result.stderr
    assert victim.read_text() == 'UCM_FIPS_BUILD=1\n' and stat.S_IMODE(victim.stat().st_mode) == 0o640


def test_a_dangling_ucm_env_link_creates_nothing(tmp_path):
    envfile = tmp_path / 'ucm.env'
    envfile.symlink_to(tmp_path / 'created-by-root')
    result = _run(['env', str(envfile), '/d'], _env(tmp_path))
    assert result.returncode == 1
    assert not (tmp_path / 'created-by-root').exists()


def test_a_ucm_env_that_is_not_a_file_is_refused(tmp_path):
    envfile = tmp_path / 'ucm.env'
    envfile.mkdir()
    result = _run(['env', str(envfile), '/d'], _env(tmp_path))
    assert result.returncode == 1 and 'not a regular file' in result.stderr


def test_the_fips_step_writes_no_ucm_env_through_a_link(tmp_path):
    victim = _env_victim(tmp_path, 'UCM_FIPS_BUILD=1\n')
    envfile = tmp_path / 'ucm.env'
    envfile.symlink_to(victim)
    (tmp_path / 'fips_enabled').write_text('1\n')
    result = _run(['fips-finish', str(tmp_path / 'home'), str(envfile), str(tmp_path / 'data'), 'ucm'],
                  _env(tmp_path))
    assert result.returncode == 1, result.stdout
    assert victim.read_text() == 'UCM_FIPS_BUILD=1\n' and stat.S_IMODE(victim.stat().st_mode) == 0o640


@pytest.mark.parametrize('absent', [True, False])
def test_a_new_ucm_env_is_created_restricted(tmp_path, absent):
    envfile = tmp_path / 'ucm.env'
    if not absent:
        envfile.write_text('UCM_FIPS_BUILD=1\n')
        envfile.chmod(0o644)
    assert _run(['env', str(envfile), '/d'], _env(tmp_path)).returncode == 0
    assert stat.S_ISREG(envfile.lstat().st_mode) and stat.S_IMODE(envfile.stat().st_mode) == 0o600


@pytest.mark.parametrize('before, after', [
    ('SECRET_KEY=a\n', 'SECRET_KEY=a\nDATA_DIR=/d\n'),
    ('SECRET_KEY=a', 'SECRET_KEY=a\nDATA_DIR=/d\n'),
    ('SECRET_KEY=a\nDATA_DIR=/srv\n', 'SECRET_KEY=a\nDATA_DIR=/srv\n'),
])
def test_env_ensure_adds_a_missing_key_and_keeps_the_mode(tmp_path, before, after):
    envfile = tmp_path / 'ucm.env'
    envfile.write_text(before)
    envfile.chmod(0o640)
    result = _run(['env-ensure', str(envfile), 'DATA_DIR', '/d'], _env(tmp_path))
    assert result.returncode == 0, result.stderr
    assert envfile.read_text() == after
    assert stat.S_IMODE(envfile.stat().st_mode) == 0o640 and not envfile.is_symlink()


def test_a_ucm_env_swapped_for_a_directory_link_mid_write_receives_nothing(tmp_path):
    """The account owns /etc/ucm: a link laid after the check is replaced by the rename, not entered."""
    envfile = tmp_path / 'ucm.env'
    envfile.write_text('SECRET_KEY=a\n')
    elsewhere = tmp_path / 'root-dir'
    elsewhere.mkdir()
    bin_dir = tmp_path / 'bin'
    # chmod --reference is the last step before the rename: the link lands in that window
    _stub(bin_dir / 'chmod', f'{shutil.which("chmod")} "$@" || exit\n'
                             f'case "$1" in --reference=*) rm -f "${{1#--reference=}}"; '
                             f'ln -s {elsewhere} "${{1#--reference=}}";; esac')
    path = f'{bin_dir}:{os.environ.get("PATH", "/usr/bin:/bin")}'
    result = _run(['env-ensure', str(envfile), 'DATA_DIR', '/d'], _env(tmp_path, extra={'PATH': path}))
    assert result.returncode == 0, result.stderr
    assert list(elsewhere.iterdir()) == []
    assert not envfile.is_symlink() and envfile.read_text() == 'SECRET_KEY=a\nDATA_DIR=/d\n'


def test_the_certificate_is_written_by_the_interpreter_ucm_python_names(tmp_path):
    """The EL9 package requires python3.12, not python3: UCM_PYTHON names the one it has."""
    data = tmp_path / 'data'
    data.mkdir()
    bin_dir = tmp_path / 'bin'
    bin_dir.mkdir()
    for util in ('mktemp', 'rm', 'openssl', 'uname', 'cat'):
        (bin_dir / util).symlink_to(shutil.which(util))
    (bin_dir / 'python3.12').symlink_to(sys.executable)
    user, group = _owner()
    result = _run(['https-cert', str(data), user, group],
                  _env(tmp_path, extra={'PATH': str(bin_dir), 'UCM_PYTHON': 'python3.12'}))
    assert result.returncode == 0, result.stderr
    assert (data / 'https_key.pem').read_text().startswith('-----BEGIN PRIVATE KEY-----')
    assert (data / 'https_cert.pem').read_text().startswith('-----BEGIN CERTIFICATE-----')


# ------------------------------------------- ucm.env written only through descriptors
# Each writer of ucm.env, as (command, file before, environment): append, fill, drop, set in place
_ENV_WRITERS = {
    'append': (['env-ensure', 'DATA_DIR', '/d'], 'SECRET_KEY=a\n', {}),
    'fill': (['env', '/d'], 'SECRET_KEY=\n', {}),
    'drop': (['env', '/d'], f'SECRET_KEY={"a" * 64}\nINITIAL_ADMIN_PASSWORD=changeme123\n', {}),
    'set': (['env', '/d'], f'SECRET_KEY={"a" * 64}\nUCM_FIPS_BUILD=0\n', {'UCM_FIPS_BUILD': '1'}),
}


def _env_writer(tmp_path, kind, stubs=None, extra=None):
    command, before, env = _ENV_WRITERS[kind]
    envfile = tmp_path / 'ucm.env'
    envfile.write_text(before)
    envfile.chmod(0o640)
    victim = tmp_path / 'authorized_keys'
    victim.write_text('ssh-ed25519 AAAA root\n')
    # A mode no step gives ucm.env: one landing here shows
    victim.chmod(0o604)
    bin_dir = tmp_path / 'bin'
    for name, body in (stubs or {}).items():
        _stub(bin_dir / name, body.format(victim=victim, real=shutil.which(name)))
    path = f'{bin_dir}:{os.environ.get("PATH", "/usr/bin:/bin")}'
    result = _run([command[0], str(envfile), *command[1:]],
                  _env(tmp_path, extra={'PATH': path, **env, **(extra or {})}))
    return result, envfile, victim


def _victim_intact(victim):
    assert victim.read_text() == 'ssh-ed25519 AAAA root\n'
    assert stat.S_IMODE(victim.stat().st_mode) == 0o604


@pytest.mark.parametrize('kind', sorted(_ENV_WRITERS))
def test_a_temporary_file_swapped_for_a_link_never_reaches_its_target(tmp_path, kind):
    """The account owns /etc/ucm: a temporary file it could swap for a link right after mktemp."""
    result, envfile, victim = _env_writer(tmp_path, kind, {
        'mktemp': 't=$({real} "$@") || exit; rm -f "$t"; ln -s {victim} "$t"; echo "$t"'})
    assert result.returncode == 0, result.stderr
    _victim_intact(victim)
    assert not envfile.is_symlink() and stat.S_IMODE(envfile.stat().st_mode) in (0o640, 0o600)


@pytest.mark.parametrize('kind', sorted(_ENV_WRITERS))
def test_the_mode_of_ucm_env_never_lands_on_another_file(tmp_path, kind):
    """A link laid in place of the new file before its mode is set: only a descriptor is changed."""
    result, envfile, victim = _env_writer(tmp_path, kind, {
        'chmod': 'for a; do t=$a; done; case "$1" in --reference=*) rm -f "$t"; ln -s {victim} "$t";; esac\n'
                 'exec {real} "$@"',
        'chown': 'for a; do t=$a; done; case "$*" in *--reference=*) rm -f "$t"; ln -s {victim} "$t";; esac\n'
                 'exec {real} "$@"'})
    assert result.returncode == 0, result.stderr
    _victim_intact(victim)


def _racing_python(tmp_path, op, swap_back=False):
    """An interpreter that swaps ucm.env for a link to a victim when first asked for `op` on it;
    swap_back: a regular file is put back before the replacement, so that only the read raced."""
    wrapper = tmp_path / 'racing-python'
    envfile, raced = tmp_path / 'ucm.env', tmp_path / 'raced'
    back = (f'[ "$4" != replace ] || [ ! -L {envfile} ] || {{ rm -f {envfile}; echo X=1 > {envfile}; }}\n'
            if swap_back else '')
    _stub(wrapper, f'case $4 in {op}) [ -e {raced} ] || {{ touch {raced}; rm -f {envfile}; '
                   f'ln -s {tmp_path}/authorized_keys {envfile}; }};; esac\n{back}'
                   f'exec {sys.executable} "$@"')
    return str(wrapper)


@pytest.mark.parametrize('kind', sorted(_ENV_WRITERS))
def test_ucm_env_swapped_for_a_link_before_its_replacement_is_refused(tmp_path, kind):
    result, envfile, victim = _env_writer(tmp_path, kind, extra={'UCM_PYTHON': _racing_python(tmp_path, 'replace')})
    assert result.returncode != 0
    assert 'symbolic link or not a regular file' in result.stderr, result.stderr
    _victim_intact(victim)
    assert envfile.is_symlink()


@pytest.mark.parametrize('kind', sorted(_ENV_WRITERS))
def test_ucm_env_swapped_for_a_link_before_it_is_read_copies_nothing_from_it(tmp_path, kind):
    """Read through a link, another file (a key, /etc/shadow) would land in a file the account reads."""
    result, envfile, victim = _env_writer(tmp_path, kind, extra={'UCM_PYTHON': _racing_python(tmp_path, 'read', swap_back=True)})
    assert result.returncode != 0
    _victim_intact(victim)
    leaked = [p for p in tmp_path.iterdir() if p.is_file() and not p.is_symlink() and p != victim
              and 'AAAA root' in p.read_text(errors='replace')]
    assert leaked == [], leaked


def tracing_python(tmp_path):
    """An interpreter for own that records each chown (the absolute path it reaches) instead of
    making it, so that the ownership steps are checked without root; returns (it, the trace)."""
    trace = tmp_path / 'chown-trace'
    prelude = (
        "import os\n"
        "def _at(name, dir_fd=None):\n"
        "    return os.path.join(os.readlink('/proc/self/fd/%d' % dir_fd), name) if dir_fd is not None else name\n"
        "def _log(where, uid, gid):\n"
        f"    open('{trace}', 'a').write('%s %d:%d\\n' % (os.path.normpath(where), uid, gid))\n"
        "os.fchown = lambda fd, uid, gid: _log(os.readlink('/proc/self/fd/%d' % fd), uid, gid)\n"
        "os.chown = lambda name, uid, gid, dir_fd=None, follow_symlinks=True: _log(_at(name, dir_fd), uid, gid)\n")
    wrapper = _stub(tmp_path / 'tracing-python', f'code=$3; shift 3\nexec {sys.executable} -I -c "{prelude}$code" "$@"')
    return str(wrapper), trace


def chowned(trace):
    return [line.rsplit(' ', 1)[0] for line in trace.read_text().splitlines()] if trace.exists() else []


# --------------------------------------------------------------- own chown-tree

def _tree_layout(tmp_path):
    top = tmp_path / 'data'
    (top / 'ca' / '.ucm-archive-20261114T120000Z' / 'old').mkdir(parents=True)
    (top / 'ca' / '.ucm-archive-20261114T120000Z' / 'old' / 'leaf.key').write_text('key')
    (top / 'ca' / 'root.pem').write_text('pem')
    (top / 'dns-hooks').mkdir()
    (top / 'dns-hooks' / 'hook.sh').write_text('#!/bin/sh\n')
    (top / 'sub').mkdir()
    (top / 'sub' / 'dns-hooks').write_text('not the hook directory\n')
    outside = tmp_path / 'outside'
    (outside / 'deep').mkdir(parents=True)
    os.symlink(outside, top / 'link')
    return top, outside


def test_chown_tree_gives_everything_but_the_archives_and_the_skipped_entries(tmp_path):
    top, outside = _tree_layout(tmp_path)
    python, trace = tracing_python(tmp_path)
    result = _run(['own', 'chown-tree', f'{top}/', '7:8', 'dns-hooks'], _env(tmp_path, extra={'UCM_PYTHON': python}))
    assert result.returncode == 0, result.stderr
    given = chowned(trace)
    assert set(given) == {str(top), str(top / 'ca'), str(top / 'ca' / 'root.pem'), str(top / 'sub'),
                          str(top / 'sub' / 'dns-hooks'), str(top / 'link')}, given
    assert all(line.endswith(' 7:8') for line in trace.read_text().splitlines())


def test_chown_tree_follows_a_linked_top_but_no_link_inside(tmp_path):
    top, outside = _tree_layout(tmp_path)
    linked = tmp_path / 'linked-data'
    os.symlink(top, linked)
    python, trace = tracing_python(tmp_path)
    result = _run(['own', 'chown-tree', f'{linked}/', '7:8'], _env(tmp_path, extra={'UCM_PYTHON': python}))
    assert result.returncode == 0, result.stderr
    given = chowned(trace)
    assert str(top) in given and str(top / 'ca' / 'root.pem') in given, given
    assert not [g for g in given if g.startswith(str(outside))], given


def test_chown_tree_never_enters_a_directory_swapped_for_a_link_while_it_walks(tmp_path):
    """A name walked by path would be resolved through the link laid in its place: fwalk never is."""
    top, outside = _tree_layout(tmp_path)
    python, trace = tracing_python(tmp_path)
    # Once opened, sub is swapped for a link to the outside before the walk descends
    swap = f"shutil.rmtree('{top}/sub'); os.symlink('{outside}', '{top}/sub')"
    racing = _racing_tree(tmp_path, python, _after_first('open', 'sub', swap))
    result = _run(['own', 'chown-tree', f'{top}/', '7:8'], _env(tmp_path, extra={'UCM_PYTHON': racing}))
    assert result.returncode == 0, result.stderr
    assert (top / 'sub').is_symlink()
    assert not [g for g in chowned(trace) if g.startswith(str(outside))], chowned(trace)


def _racing_tree(tmp_path, python, race):
    """`python` with `race` (Python code) run before own: it changes the tree at one step of the walk."""
    return str(_stub(tmp_path / 'racing-tree-python', f'code=$3; shift 3\nexec {python} -I -c "{race}$code" "$@"'))


def _after_first(call, name, then):
    """Python code: the first `os.<call>` of entry `name` runs, then `then` changes the tree."""
    return (f"import shutil\n_real_{call} = os.{call}\n_raced = []\n"
            f"def _racing(n, *a, **k):\n"
            f"    r = _real_{call}(n, *a, **k)\n"
            f"    if n == '{name}' and not _raced:\n"
            f"        _raced.append(1); {then}\n"
            f"    return r\n"
            f"os.{call} = _racing\n")


@pytest.mark.parametrize('owner', ['7:8', '0:0'])
def test_chown_tree_survives_a_directory_swapped_for_a_file_before_its_descent(tmp_path, owner):
    """The account can turn a directory it owns into a file once it is listed: that entry is
    passed by and named, the walk goes on."""
    top, _outside = _tree_layout(tmp_path)
    python, trace = tracing_python(tmp_path)
    swap = f"shutil.rmtree('{top}/sub'); open('{top}/sub', 'w').write('x')"
    racing = _racing_tree(tmp_path, python, _after_first('stat', 'sub', swap))
    result = _run(['own', 'chown-tree', f'{top}/', owner], _env(tmp_path, extra={'UCM_PYTHON': racing}))
    assert result.returncode == 0, result.stderr
    assert f'WARNING: {top}/sub: ' in result.stderr, result.stderr
    assert (top / 'sub').is_file()
    assert str(top / 'ca' / 'root.pem') in chowned(trace) and str(top / 'dns-hooks' / 'hook.sh') in chowned(trace)


def inode_tracing_python(tmp_path):
    """tracing_python, recording the inode each chown reaches instead of its name."""
    trace = tmp_path / 'inode-trace'
    prelude = (
        "import os\n_lstat = os.stat\n"
        f"def _log(st):\n    open('{trace}', 'a').write('%d\\n' % st.st_ino)\n"
        "os.fchown = lambda fd, uid, gid: _log(os.fstat(fd))\n"
        "os.chown = lambda name, uid, gid, dir_fd=None, follow_symlinks=True: "
        "_log(_lstat(name, dir_fd=dir_fd, follow_symlinks=follow_symlinks))\n")
    wrapper = _stub(tmp_path / 'inode-tracing-python', f'code=$3; shift 3\nexec {sys.executable} -I -c "{prelude}$code" "$@"')
    return str(wrapper), trace


@pytest.mark.parametrize('owner', ['7:8', '0:0'])
@pytest.mark.parametrize('step', ['stat', 'open'])
def test_chown_tree_never_reaches_a_file_linked_in_place_of_a_directory(tmp_path, owner, step):
    """A directory swapped for a hard link to a root file, once read or once opened, is changed
    through the descriptor of the directory, or not at all: never through its name."""
    top, _outside = _tree_layout(tmp_path)
    victim = tmp_path / 'shadow'
    victim.write_text('root:*:1::::::\n')
    victim.chmod(0o646)
    python, trace = inode_tracing_python(tmp_path)
    swap = f"shutil.rmtree('{top}/sub'); os.link('{victim}', '{top}/sub')"
    racing = _racing_tree(tmp_path, python, _after_first(step, 'sub', swap))
    result = _run(['own', 'chown-tree', f'{top}/', owner], _env(tmp_path, extra={'UCM_PYTHON': racing}))
    assert result.returncode == 0, result.stderr
    assert os.path.samefile(victim, top / 'sub')
    reached = trace.read_text().split()
    assert str(victim.stat().st_ino) not in reached and str((top / 'ca').stat().st_ino) in reached, reached
    assert stat.S_IMODE(victim.stat().st_mode) == 0o646


def test_chown_tree_leaves_what_is_neither_a_file_a_directory_nor_a_link(tmp_path):
    top, _outside = _tree_layout(tmp_path)
    os.mkfifo(top / 'ca' / 'pipe')
    python, trace = tracing_python(tmp_path)
    result = _run(['own', 'chown-tree', f'{top}/', '7:8'], _env(tmp_path, extra={'UCM_PYTHON': python}))
    assert result.returncode == 0, result.stderr
    assert str(top / 'ca' / 'pipe') not in chowned(trace) and str(top / 'ca' / 'root.pem') in chowned(trace)


def test_ucm_env_swapped_for_a_link_before_it_is_restricted_keeps_the_target_mode(tmp_path):
    """The mode a new ucm.env gets before its first secret is set by descriptor, never by path."""
    envfile = tmp_path / 'ucm.env'
    envfile.write_text('UCM_FIPS_BUILD=1\n')
    victim = tmp_path / 'shadow'
    victim.write_text('root:*:1::::::\n')
    victim.chmod(0o640)
    bin_dir = tmp_path / 'bin'
    # tail ends the lookup of SECRET_KEY, the last step before the file is restricted
    _stub(bin_dir / 'tail', f'[ -e {tmp_path}/raced ] || {{ touch {tmp_path}/raced; rm -f {envfile}; '
                            f'ln -s {victim} {envfile}; }}\nexec {shutil.which("tail")} "$@"')
    result = _run(['env', str(envfile), '/d'],
                  _env(tmp_path, extra={'PATH': f'{bin_dir}:{os.environ.get("PATH", "/usr/bin:/bin")}'}))
    assert result.returncode != 0
    assert stat.S_IMODE(victim.stat().st_mode) == 0o640 and victim.read_text() == 'root:*:1::::::\n'


@pytest.mark.parametrize('link_ok', [True, False])
def test_own_mode_leaves_a_link_and_what_it_points_to(tmp_path, link_ok):
    elsewhere = tmp_path / 'elsewhere'
    elsewhere.mkdir()
    elsewhere.chmod(0o770)
    (tmp_path / 'private').symlink_to(elsewhere)
    result = _run(['own', 'mode', str(tmp_path / 'private'), '700', *(['link-ok'] if link_ok else [])], _env(tmp_path))
    assert (result.returncode == 0) is link_ok, result.stderr
    assert stat.S_IMODE(elsewhere.stat().st_mode) == 0o770


def test_own_mode_with_a_final_slash_reaches_a_linked_data_directory(tmp_path):
    elsewhere = tmp_path / 'elsewhere'
    elsewhere.mkdir()
    (tmp_path / 'data').symlink_to(elsewhere)
    result = _run(['own', 'mode', f'{tmp_path}/data/', '750'], _env(tmp_path))
    assert result.returncode == 0, result.stderr
    assert stat.S_IMODE(elsewhere.stat().st_mode) == 0o750


# ------------------------------------------- the home is root's, the data the account's

def _home_layout(tmp_path):
    """/opt/ucm as a 3.0 or 2.254 package left it: everything the account's, some of it writable by all."""
    home = tmp_path / 'opt-ucm'
    for rel in ('scripts', 'venv/bin', 'venv/lib/data', 'backend/models', 'backend/data/ca', 'data/ca', 'frontend/dist'):
        (home / rel).mkdir(parents=True)
    for rel in ('scripts/ucm-watcher.sh', 'venv/bin/pip', 'venv/lib/data/x.py', 'backend/models/m.py',
                'backend/data/ca/old.pem', 'data/ca/root.pem', 'frontend/dist/index.html', 'VERSION'):
        (home / rel).write_text('x\n')
    (home / 'scripts' / 'ucm-watcher.sh').chmod(0o6777)
    (home / 'scripts').chmod(0o777)
    return home


def test_the_root_pass_gives_the_home_to_root_but_the_data_the_unit_writes(tmp_path):
    home = _home_layout(tmp_path)
    python, trace = tracing_python(tmp_path)
    result = _run(['own', 'chown-tree', f'{home}/', '0:0', 'data', 'backend/data'],
                  _env(tmp_path, extra={'UCM_PYTHON': python}))
    assert result.returncode == 0, result.stderr
    given = set(chowned(trace))
    for rel in ('', 'scripts', 'scripts/ucm-watcher.sh', 'venv', 'venv/bin/pip', 'venv/lib/data', 'venv/lib/data/x.py',
                'backend', 'backend/models/m.py', 'frontend/dist/index.html', 'VERSION'):
        assert os.path.normpath(home / rel) in given, rel
    assert not [g for g in given if g.startswith((str(home / 'data'), str(home / 'backend' / 'data')))], given
    # No group or other account may write what root runs, and no set-id bit outlives the pass
    assert stat.S_IMODE((home / 'scripts' / 'ucm-watcher.sh').stat().st_mode) == 0o755
    assert stat.S_IMODE((home / 'scripts').stat().st_mode) == 0o755


def test_the_account_pass_leaves_modes_alone(tmp_path):
    home = _home_layout(tmp_path)
    python, _trace = tracing_python(tmp_path)
    result = _run(['own', 'chown-tree', f'{home}/', '7:8'], _env(tmp_path, extra={'UCM_PYTHON': python}))
    assert result.returncode == 0, result.stderr
    assert stat.S_IMODE((home / 'scripts').stat().st_mode) == 0o777


def test_chown_tree_refuses_a_linked_top_named_without_a_final_slash(tmp_path):
    real = tmp_path / 'real'
    real.mkdir()
    (tmp_path / 'top').symlink_to(real)
    python, trace = tracing_python(tmp_path)
    result = _run(['own', 'chown-tree', str(tmp_path / 'top'), '7:8'], _env(tmp_path, extra={'UCM_PYTHON': python}))
    assert result.returncode == 3 and 'symbolic link or not a directory' in result.stderr, result.stderr
    assert chowned(trace) == []


# ------------------------------------------- a hard link to a root file is never touched

def _hard_linked(tmp_path, name='ucm.env'):
    """A file of root's (mode 0604, no step gives it) and, in the account's directory, a second name for it."""
    victim = tmp_path / 'shadow'
    victim.write_text('root:*:1::::::\n')
    victim.chmod(0o604)
    own_dir = tmp_path / 'etc-ucm'
    own_dir.mkdir()
    os.link(victim, own_dir / name)
    return victim, own_dir / name


def test_own_read_refuses_a_hard_link(tmp_path):
    victim, linked = _hard_linked(tmp_path)
    result = _run(['own', 'read', str(linked)], _env(tmp_path))
    assert result.returncode == 3 and 'hard link' in result.stderr, result.stderr
    assert result.stdout == ''


def test_own_replace_refuses_a_hard_link(tmp_path):
    victim, linked = _hard_linked(tmp_path)
    result = subprocess.run([BASH, str(SCRIPT), 'own', 'replace', str(linked)], env=_env(tmp_path),
                            input='X=1\n', capture_output=True, text=True)
    assert result.returncode == 3 and 'hard link' in result.stderr, result.stderr
    assert os.path.samefile(victim, linked) and victim.read_text() == 'root:*:1::::::\n'


def test_own_mode_refuses_a_hard_link(tmp_path):
    victim, linked = _hard_linked(tmp_path, 'private')
    result = _run(['own', 'mode', str(linked), '700'], _env(tmp_path))
    assert result.returncode == 3 and 'hard link' in result.stderr, result.stderr
    assert stat.S_IMODE(victim.stat().st_mode) == 0o604


@pytest.mark.parametrize('owner', ['7:8', '0:0'])
def test_chown_tree_leaves_a_hard_link_as_it_is(tmp_path, owner):
    victim, linked = _hard_linked(tmp_path, 'x.pem')
    (linked.parent / 'kept.pem').write_text('pem')
    python, trace = tracing_python(tmp_path)
    result = _run(['own', 'chown-tree', f'{linked.parent}/', owner], _env(tmp_path, extra={'UCM_PYTHON': python}))
    assert result.returncode == 0, result.stderr
    assert 'hard link' in result.stderr, result.stderr
    assert str(linked) not in chowned(trace) and str(linked.parent / 'kept.pem') in chowned(trace)
    assert stat.S_IMODE(victim.stat().st_mode) == 0o604


@pytest.mark.parametrize('ours', [True, False])
def test_the_root_pass_takes_back_a_hard_linked_file_of_the_account(tmp_path, ours):
    """A file the account laid under /opt/ucm and linked from its data is given to root all the
    same; a hard link to anyone else's file stays as it is."""
    victim, linked = _hard_linked(tmp_path, 'evil.pth')
    victim.chmod(0o666)
    account = os.getuid() if ours else os.getuid() + 1
    python, trace = tracing_python(tmp_path)
    result = _run(['own', 'chown-tree', f'{linked.parent}/', '0:0', f'--from={account}'],
                  _env(tmp_path, extra={'UCM_PYTHON': python}))
    assert result.returncode == 0, result.stderr
    assert (str(linked) in chowned(trace)) is ours, (chowned(trace), result.stderr)
    assert ('hard link' in result.stderr) is not ours, result.stderr
    assert stat.S_IMODE(victim.stat().st_mode) == (0o644 if ours else 0o666)
