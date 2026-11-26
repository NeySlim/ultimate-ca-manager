"""packaging/scripts/ucm-watcher.sh installing a DEB with UCM_FIPS_BUILD=1, run for real under a
temporary root with the real native-setup.sh and stubs for dpkg, apt-get and systemctl."""
import hashlib
import json
import pathlib
import shutil
import subprocess

import pytest

from tests.test_native_setup_script import BASH, UBUNTU, _env, _stub, _toolbox

ROOT = pathlib.Path(__file__).resolve().parents[2]
WATCHER = ROOT / 'packaging' / 'scripts' / 'ucm-watcher.sh'
SETUP = ROOT / 'packaging' / 'scripts' / 'native-setup.sh'

pytestmark = pytest.mark.skipif(BASH is None or shutil.which('python3') is None,
                                reason='bash and python3 are required')


def _update(tmp_path, dpkg, apt_get, stale_marker=False):
    """Runs one update to 99.0 from 98.0; dpkg and apt-get are shell bodies, $R the root."""
    root = tmp_path / 'root'
    data = root / 'opt/ucm/data'
    (data / 'updates').mkdir(parents=True)
    (root / 'opt/ucm/scripts').mkdir()
    shutil.copy(SETUP, root / 'opt/ucm/scripts/native-setup.sh')
    (root / 'etc/ucm').mkdir(parents=True)
    (root / 'etc/ucm/ucm.env').write_text('SECRET_KEY=a\nUCM_FIPS_BUILD=1\n')
    (root / 'var/log/ucm').mkdir(parents=True)
    (root / 'opt/ucm/VERSION').write_text('98.0\n')
    package = data / 'updates' / 'ucm_99.0_all.deb'
    package.write_text('')
    # The release digest the watcher fetches as root (tests/test_update_watcher_claim.py)
    releases = tmp_path / 'releases'
    (releases / 'v99.0').mkdir(parents=True)
    (releases / 'v99.0' / 'ucm_99.0_all.deb.sha256').write_text(
        hashlib.sha256(b'').hexdigest() + '  ucm_99.0_all.deb\n')
    (data / '.update_pending').write_text(str(package))
    (data / '.update_manifest.json').write_text(json.dumps({'op_id': 'op', 'to_version': '99.0'}))

    bin_dir, _ = _toolbox(tmp_path, rustc_in_path='1.92.0')
    for util in ('date', 'tee', 'python3', 'bash', 'rm', 'dirname'):
        if not (bin_dir / util).exists():
            (bin_dir / util).symlink_to(shutil.which(util))
    (root / 'opt/ucm/venv/bin').mkdir(parents=True)
    (root / 'opt/ucm/venv/bin/python').symlink_to(_stub(tmp_path / 'python3.12'))
    calls = tmp_path / 'calls'
    _stub(bin_dir / 'dpkg', f'echo dpkg >> {calls}\nR={root}\n{dpkg}')
    _stub(bin_dir / 'apt-get', f'echo apt-get >> {calls}\nR={root}\n{apt_get}')
    _stub(bin_dir / 'systemctl', f'echo "$*" >> {tmp_path}/systemctl.calls')
    _stub(bin_dir / 'dpkg-deb', 'echo ucm')

    env = _env(tmp_path, UBUNTU, {'PATH': str(bin_dir), 'UCM_WATCHER_ROOT': str(root),
                                  'UCM_WATCHER_RELEASES': releases.as_uri(), 'TMPDIR': str(tmp_path),
                                  'UCM_SETUP_BUILD_LOG': str(root / 'var/log/ucm/fips-build.log')})
    if stale_marker:
        (root / 'var/log/ucm/fips-build.failed').write_text('build failed')
    result = subprocess.run([BASH, str(WATCHER)], env=env, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    steps = calls.read_text().split() if calls.exists() else []
    return json.loads((data / '.update_result.json').read_text()), steps


FAIL_BUILD = 'echo "build failed" > $R/var/log/ucm/fips-build.failed; exit 1'
INSTALL = 'echo 99.0 > $R/opt/ucm/VERSION; exit 0'


def test_a_failed_fips_build_is_not_rerun_by_apt_get(tmp_path):
    result, steps = _update(tmp_path, dpkg=f'echo 99.0 > $R/opt/ucm/VERSION; {FAIL_BUILD}', apt_get='exit 100')
    assert steps == ['dpkg']
    assert result['status'] == 'failed' and result['step'] == 'fips-build'
    assert 'UCM_FIPS_BUILD=1 build failed' in result['error']


def test_a_fips_build_failed_under_apt_get_is_reported_as_such(tmp_path):
    result, steps = _update(tmp_path, dpkg='exit 1', apt_get=FAIL_BUILD)
    assert steps == ['dpkg', 'apt-get']
    assert result['step'] == 'fips-build' and 'UCM_FIPS_BUILD=1 build failed' in result['error']


def test_an_apt_get_failure_without_build_failure_keeps_its_message(tmp_path):
    result, steps = _update(tmp_path, dpkg='exit 1', apt_get='exit 100')
    assert steps == ['dpkg', 'apt-get']
    assert result['step'] == 'apt-get' and result['error'].startswith('apt-get -f install failed')


def test_a_failure_left_by_an_earlier_update_is_not_blamed_on_this_one(tmp_path):
    result, steps = _update(tmp_path, dpkg='exit 1', apt_get=INSTALL, stale_marker=True)
    assert steps == ['dpkg', 'apt-get']
    assert result['status'] == 'installed', result


def test_a_successful_update(tmp_path):
    result, steps = _update(tmp_path, dpkg=INSTALL, apt_get='exit 0')
    assert steps == ['dpkg', 'apt-get']
    assert result['status'] == 'installed' and result['installed_version'] == '99.0'


# A restart asked for (interface, update) is not one StartLimitBurst counts: that limit is for crashes
INTENDED = ['reset-failed ucm', 'restart ucm']


def test_an_update_resets_the_start_limit_before_it_restarts_the_service(tmp_path):
    _update(tmp_path, dpkg=INSTALL, apt_get='exit 0')
    assert (tmp_path / 'systemctl.calls').read_text().splitlines() == INTENDED


def test_a_restart_asked_for_resets_the_start_limit_before_it_restarts_the_service(tmp_path):
    root = tmp_path / 'root'
    (root / 'opt/ucm/data').mkdir(parents=True)
    (root / 'var/log/ucm').mkdir(parents=True)
    (root / 'opt/ucm/data/.restart_requested').write_text('')
    bin_dir = tmp_path / 'bin'
    for util in ('date', 'tee', 'rm'):
        (bin_dir / util).parent.mkdir(exist_ok=True)
        (bin_dir / util).symlink_to(shutil.which(util))
    _stub(bin_dir / 'systemctl', f'echo "$*" >> {tmp_path}/systemctl.calls')
    result = subprocess.run([BASH, str(WATCHER)], capture_output=True, text=True,
                            env={'PATH': str(bin_dir), 'UCM_WATCHER_ROOT': str(root)})
    assert result.returncode == 0, result.stderr
    assert (tmp_path / 'systemctl.calls').read_text().splitlines() == INTENDED
    assert not (root / 'opt/ucm/data/.restart_requested').exists()
