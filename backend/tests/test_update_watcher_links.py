"""The root watcher writes nothing through a link the service account lays in a directory it owns.

The service account writes /opt/ucm/data and /var/log/ucm: a link there must not make root
append to, truncate, chmod or read another file. The watcher runs for real under a temporary
root, as in tests/test_update_watcher_claim.py.
"""
import json
import os
import shutil
import stat
import subprocess

from tests.test_native_setup_script import _stub
from tests.test_update_watcher_claim import BASH, WATCHER, host  # noqa: F401 (fixture)

INJECTED = "'\ntouch /tmp/pwned\n#"


def _victim(host, name='victim', body='precious', mode=0o600):
    victim = host.tmp / name
    victim.write_text(body)
    victim.chmod(mode)
    return victim


def test_the_log_is_never_appended_through_a_link(host):
    victim = _victim(host)
    (host.root / 'var/log/ucm/ucm.log').symlink_to(victim)
    result, _ = host.run(INJECTED)
    assert result['status'] == 'failed' and result['step'] == 'precheck', result
    assert victim.read_text() == 'precious'
    assert stat.S_IMODE(victim.stat().st_mode) == 0o600


def test_a_line_break_in_the_trigger_starts_no_line_of_its_own(host):
    host.run(INJECTED)
    lines = host.done.stdout.splitlines()
    assert any('Invalid or missing package path' in line for line in lines), lines
    assert 'touch /tmp/pwned' not in lines and '#' not in lines, lines


def test_a_restart_appends_nothing_through_a_link(host):
    victim = _victim(host)
    (host.root / 'var/log/ucm/ucm.log').symlink_to(victim)
    (host.data / '.restart_requested').write_text('')
    done = subprocess.run([BASH, str(WATCHER)], capture_output=True, text=True,
                          env={'PATH': str(host.bin), 'UCM_WATCHER_ROOT': str(host.root)})
    assert done.returncode == 0, done.stderr
    assert 'Restart requested' in done.stdout
    assert victim.read_text() == 'precious'


def test_the_result_is_never_written_through_a_link(host):
    victim = _victim(host)
    (host.data / '.update_result.json.tmp').symlink_to(victim)
    result, _ = host.run(host.package())
    assert result['status'] == 'installed', result
    assert victim.read_text() == 'precious'
    assert stat.S_IMODE(victim.stat().st_mode) == 0o600
    written = host.data / '.update_result.json'
    assert not written.is_symlink() and stat.S_ISREG(written.lstat().st_mode)
    assert stat.S_IMODE(written.stat().st_mode) == 0o644


def test_a_trigger_that_is_a_link_is_not_read(host):
    secret = _victim(host, 'secret', body='root-only-secret-line')
    (host.data / '.update_pending').symlink_to(secret)
    result, _ = host.run(None)
    assert result['status'] == 'failed' and result['step'] == 'precheck', result
    assert 'root-only-secret-line' not in host.done.stdout + host.done.stderr
    assert 'root-only-secret-line' not in json.dumps(result)
    assert secret.read_text() == 'root-only-secret-line'


def test_a_claimed_manifest_that_is_a_link_is_not_read(host):
    secret = _victim(host, 'secret.json', body=json.dumps({'op_id': 'SECRET-OP', 'to_version': '99.0'}))
    (host.data / '.update_manifest.processing').symlink_to(secret)
    result, _ = host.run(host.package(), manifest=False)
    assert result['op_id'] is None, result
    assert result['status'] == 'failed' and 'no valid target version' in result['error'], result
    assert os.path.exists(secret)


def test_a_claimed_manifest_link_to_a_directory_receives_nothing(host):
    """The claim renames over .update_manifest.processing: a link there is replaced, never entered."""
    elsewhere = host.tmp / 'root-dir'
    elsewhere.mkdir()
    (host.data / '.update_manifest.processing').symlink_to(elsewhere)
    result, _ = host.run(host.package())
    assert list(elsewhere.iterdir()) == []
    assert result['op_id'] == 'op' and result['status'] == 'installed', result


def test_a_manifest_too_large_for_an_argument_still_gets_its_result(host):
    """64 KiB of invalid UTF-8 grows threefold once decoded: over what one exec argument may hold."""
    head = json.dumps({'op_id': 'op', 'to_version': '99.0', 'pad': ''})[:-2].encode()
    body = head + b'\xff' * ((1 << 16) - len(head) - 2) + b'"}'
    (host.data / '.update_manifest.json').write_bytes(body)
    result, _ = host.run(host.package(), manifest=False)
    assert result['op_id'] == 'op' and result['status'] == 'installed', result


def test_an_error_too_large_for_an_argument_still_gets_its_result(host):
    """A precheck message the account can make grow (a FIPS build log line, say) is cut before the exec."""
    scripts = host.root / 'opt/ucm/scripts'
    scripts.mkdir(parents=True)
    (scripts / 'native-setup.sh').write_text('[ "$1" != update-precheck ] && exit 0\n'
                                             'head -c 300000 /dev/zero | tr "\\0" x; exit 1\n')
    (host.bin / 'head').symlink_to(shutil.which('head'))
    result, _ = host.run(host.package())
    assert result['status'] == 'failed' and result['step'] == 'precheck', result
    assert result['error'] == 'x' * 500, len(result['error'] or '')


def test_a_claimed_manifest_path_that_is_a_directory_is_refused_and_the_service_restarted(host):
    """rename(2) cannot replace a directory: the update is refused, its result written, ucm started."""
    (host.data / '.update_manifest.processing' / 'inside').mkdir(parents=True)
    _stub(host.bin / 'systemctl', f'echo "systemctl $*" >> {host.calls}')
    result, calls = host.run(host.package())
    assert result['status'] == 'failed' and result['step'] == 'precheck', result
    assert 'is a directory' in result['error'], result
    assert not [c for c in calls if c.startswith(('dpkg', 'rpm', 'apt-get'))], calls
    assert 'systemctl restart ucm' in calls, calls
    assert not (host.data / '.update_pending').exists()
