"""In FIPS mode the image refuses to start when the module's MAC differs from the build's.

docker/fips-module.sh carries install_fips_module, which the entrypoint calls: it runs
fipsinstall (a fake openssl here) and compares the module-mac to the build reference.
"""
import os
import pathlib
import shutil
import stat
import subprocess

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[2]
HELPER = ROOT / 'docker' / 'fips-module.sh'
BUILD_MAC = '41:42:43:44:45:46:47:48:49:4A:4B:4C:4D:4E:4F:50:51:52:53:54:55:56:57:58:59:5A:61:62:63:64:65:66'
OTHER_MAC = '00:42:43:44:45:46:47:48:49:4A:4B:4C:4D:4E:4F:50:51:52:53:54:55:56:57:58:59:5A:61:62:63:64:65:66'

FAKE_OPENSSL = r'''#!/bin/bash
# fipsinstall -pedantic -module M -provider_name fips -out OUT: writes a module config
[ "$1" = fipsinstall ] || exit 2
out=""
while [ $# -gt 0 ]; do [ "$1" = -out ] && out=$2; shift; done
[ -n "${FAKE_FAIL:-}" ] && { echo "INSTALL FAILED"; exit 1; }
cat > "$out" <<EOF
[fips_sect]
activate = 1
conditional-errors = 1
security-checks = 1
module-mac = $FAKE_MAC
EOF
echo "INSTALL PASSED"
'''


@pytest.fixture
def bench(tmp_path):
    bindir = tmp_path / 'bin'
    bindir.mkdir()
    fake = bindir / 'openssl'
    fake.write_text(FAKE_OPENSSL)
    fake.chmod(fake.stat().st_mode | stat.S_IXUSR)
    run_dir = tmp_path / 'run'
    run_dir.mkdir()
    module = tmp_path / 'fips.so'
    module.write_bytes(b'module')
    return tmp_path


def _run(bench, reference, mac=BUILD_MAC, **extra):
    script = (f'. {HELPER}; install_fips_module "{bench / "fips.so"}" "{bench / "run"}" '
              f'"{reference}" && echo continued')
    env = {'PATH': f'{bench / "bin"}:/usr/bin:/bin', 'FAKE_MAC': mac, **extra}
    r = subprocess.run(['bash', '-c', script], env=env, capture_output=True, text=True)
    return r.returncode, r.stdout + r.stderr


def _reference(bench, content):
    ref = bench / 'fips-module.mac'
    ref.write_text(content)
    return ref


def test_matching_reference_continues_pos(bench):
    rc, out = _run(bench, _reference(bench, BUILD_MAC + '\n'))
    assert rc == 0 and 'continued' in out
    assert (bench / 'run' / 'fipsmodule.cnf').is_file()


def test_modified_module_is_refused_neg(bench):
    rc, out = _run(bench, _reference(bench, BUILD_MAC + '\n'), mac=OTHER_MAC)
    assert rc == 1 and 'continued' not in out
    assert 'modified since the image was built' in out


def test_missing_reference_is_refused_neg(bench):
    rc, out = _run(bench, bench / 'absent.mac')
    assert rc == 1 and 'continued' not in out
    assert 'missing or unreadable' in out
    # the refusal is the only text: no shell redirection error above it
    assert 'No such file' not in out and 'line ' not in out


@pytest.mark.parametrize('content', ['', '\n', 'not a mac\n', BUILD_MAC.lower(), BUILD_MAC[3:],
                                     BUILD_MAC + ':00', BUILD_MAC.replace(':', '')])
def test_empty_or_malformed_reference_is_refused_neg(bench, content):
    rc, out = _run(bench, _reference(bench, content))
    assert rc == 1 and 'continued' not in out
    assert 'missing or unreadable' in out and 'modified' not in out


@pytest.mark.skipif(os.geteuid() == 0, reason='root reads a mode 000 file')
def test_reference_without_read_permission_is_refused_neg(bench):
    ref = _reference(bench, BUILD_MAC)
    ref.chmod(0)
    rc, out = _run(bench, ref)
    assert rc == 1 and 'continued' not in out


def test_config_without_module_mac_is_refused_neg(bench):
    # an empty module-mac in the runtime config never equals an empty reference
    rc, out = _run(bench, _reference(bench, BUILD_MAC), mac='')
    assert rc == 1 and 'continued' not in out


def test_failed_self_tests_are_refused_neg(bench):
    rc, out = _run(bench, _reference(bench, BUILD_MAC), FAKE_FAIL='1')
    assert rc == 1 and 'self-tests' in out and 'INSTALL FAILED' in out


def test_build_records_the_mac_the_runtime_compares_pos(bench):
    # the build writes the reference with fips_module_mac from the same helper
    cnf = bench / 'build.cnf'
    cnf.write_text(f'[fips_sect]\nmodule-mac = {BUILD_MAC}\ninstall-mac = 00:11\n')
    mac = subprocess.run(['bash', '-c', f'. {HELPER}; fips_module_mac "{cnf}"'],
                         env={'PATH': '/usr/bin:/bin'}, capture_output=True, text=True)
    assert mac.returncode == 0 and mac.stdout.strip() == BUILD_MAC
    rc, out = _run(bench, _reference(bench, mac.stdout))
    assert rc == 0 and 'continued' in out


@pytest.mark.parametrize('shell', ['bash', 'dash'])
def test_the_build_shell_can_source_the_helper_pos(bench, shell):
    """The Dockerfile sources the helper under /bin/sh (dash) with set -eu: it must parse there."""
    sh = shutil.which(shell)
    if not sh:
        pytest.skip(f'no {shell} on this host')
    cnf = bench / 'build.cnf'
    cnf.write_text(f'[fips_sect]\nmodule-mac = {BUILD_MAC}\n')
    r = subprocess.run([sh, '-c', f'set -eu; . {HELPER}; fips_module_mac "{cnf}"'],
                       env={'PATH': '/usr/bin:/bin'}, capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    assert r.stdout.strip() == BUILD_MAC
