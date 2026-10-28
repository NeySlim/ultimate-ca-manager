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
         'readlink')

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
  -) cat > /dev/null; echo "cryptography, hashlib and psycopg2 use the system OpenSSL" ;;
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

def _systemd(tmp_path, bin_dir, record, state='active', hold_stop=None):
    """A booted systemd whose systemctl logs each call, with the venv's content at that moment.

    With hold_stop, `stop` stops ucm, creates that file and waits to be killed."""
    (tmp_path / 'run-systemd').mkdir()
    (tmp_path / 'ucm-state').write_text(state)
    venv = tmp_path / 'opt' / 'venv'
    hold = f'touch {hold_stop}; while :; do {shutil.which("sleep")} 0.05; done' if hold_stop else ':'
    _stub(bin_dir / 'systemctl', f"""echo "SYSTEMCTL $* [$({shutil.which('ls')} {venv} 2>/dev/null | tr '\\n' ' ')]" >> {record}
state=$(cat {tmp_path}/ucm-state)
case "$1" in
  is-active) [ "$state" = active ] ;;
  stop) echo inactive > {tmp_path}/ucm-state; {hold} ;;
  start|restart) echo active > {tmp_path}/ucm-state ;;
esac""")
    return {'PATH': str(bin_dir), 'UCM_SETUP_SYSTEMD_RUN': str(tmp_path / 'run-systemd')}


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
    _stub(home / 'venv' / 'bin' / 'pip')  # `pip show requests-kerberos` succeeds: reinstalled too
    extra = _systemd(tmp_path, bin_dir, record)
    result = _run(['venv', str(home), str(python), 'rpm', str(envfile)], _env(tmp_path, ALMA, extra))
    assert result.returncode == 0, result.stderr
    lines = record.read_text().splitlines()
    # pip, requirements, pyjks, then the two Kerberos reinstalls
    assert [line for line in lines if line.startswith('UCM')] == ['UCM active'] * 5
    assert 'ARGS install --quiet requests-kerberos' in lines and "ARGS install --quiet pyspnego[kerberos]" in lines
    calls = _calls(record)
    assert calls[-2:] == ['SYSTEMCTL is-active --quiet ucm', 'SYSTEMCTL stop ucm']
    assert all(c.startswith('ARGS') for c in calls[:-2])


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
    bin_dir, _ = _toolbox(tmp_path, rustc_in_path=None)
    held = tmp_path / 'held'
    python, record = _fake_python(tmp_path, _held_gunicorn(held) if point == 'switched' else 'exit 0')
    home, envfile = _home(tmp_path)
    envfile.write_text('SECRET_KEY=a\n')
    shutil.rmtree(home / 'venv')
    _venv_dir(home / 'venv')
    extra = _systemd(tmp_path, bin_dir, record, hold_stop=held if point == 'stopped' else None)
    proc = _spawn(tmp_path, home, python, envfile, extra)
    _wait_for(held, proc)
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


def _systemctl_lines(record):
    return [line for line in record.read_text().splitlines() if line.startswith('SYSTEMCTL')]


RESTARTED = ['SYSTEMCTL is-active --quiet ucm [bin good ]', 'SYSTEMCTL stop ucm [bin good ]',
             'SYSTEMCTL start ucm [bin good ]']


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

    With requests-kerberos in the previous venv, bash writes before the switch."""
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
        _stub(home / 'venv' / 'bin' / 'pip')  # `pip show requests-kerberos` succeeds
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
    assert result.returncode == 1 and 'psycopg2-binary not found once' in result.stderr
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
    (UBUNTU, 'sudo pro enable fips-updates'),
])
def test_a_host_outside_fips_mode_is_told_how_to_enable_it(tmp_path, os_release, command):
    envfile = tmp_path / 'ucm.env'
    envfile.write_text('UCM_FIPS_BUILD=1\n')
    result = _finish(tmp_path, envfile, 0, os_release)
    assert result.returncode == 0
    assert 'not in FIPS mode' in result.stdout and command in result.stdout
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
            hostname='[ "$1" = -I ] && echo "192.0.2.10 2001:db8::10 " || echo ucm.example.test'):
    bin_dir = tmp_path / 'bin'
    _stub(bin_dir / 'hostname', hostname)
    status = 'install ok installed' if softhsm is True else softhsm
    _stub(bin_dir / 'dpkg-query', f'[ "$*" = \'-W -f=${{Status}} softhsm2\' ] && printf %s \'{status}\'' if softhsm else 'exit 1')
    _stub(bin_dir / 'dpkg', 'exit 1')
    _stub(bin_dir / 'rpm', '[ "$*" = "-q softhsm" ]' if softhsm else 'exit 1')
    envfile = tmp_path / 'ucm.env'
    envfile.write_text('HTTPS_PORT=9443\nINITIAL_ADMIN_PASSWORD=s3cret\n')
    path = f"{bin_dir}:{os.environ.get('PATH', '/usr/bin:/bin')}"
    return envfile, _run(['banner', str(envfile), pkg], _env(tmp_path, extra={'PATH': path}))


def test_the_banner_brackets_ipv6_addresses(tmp_path):
    envfile, result = _banner(tmp_path, 'deb')
    assert result.returncode == 0, result.stderr
    urls = [line.split()[-1] for line in result.stdout.splitlines() if 'https://' in line]
    assert urls == ['https://ucm.example.test:9443', 'https://192.0.2.10:9443', 'https://[2001:db8::10]:9443']
    assert ' Admin:    admin / s3cret' in result.stdout
    assert f' Config:   {envfile}' in result.stdout


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
    assert ' Admin:    admin / s3cret' in result.stdout
    assert result.stdout.rstrip().endswith('============================================')


def test_a_failed_write_leaves_no_copy_of_the_secret(tmp_path):
    bin_dir = tmp_path / 'bin'
    for util in UTILS:
        real = shutil.which(util)
        if real and util not in ('openssl', 'mv'):
            (bin_dir / util).parent.mkdir(parents=True, exist_ok=True)
            (bin_dir / util).symlink_to(real)
    _stub(bin_dir / 'openssl', f'echo {"ef" * 32}')
    _stub(bin_dir / 'mv', 'exit 1')
    conf = tmp_path / 'etc'
    conf.mkdir()
    envfile = conf / 'ucm.env'
    envfile.write_text('SECRET_KEY=\n')
    result = _run(['env', str(envfile), '/d'], _env(tmp_path, extra={'PATH': str(bin_dir)}))
    assert result.returncode != 0
    assert [p.name for p in conf.iterdir()] == ['ucm.env'] and envfile.read_text() == 'SECRET_KEY=\n'
