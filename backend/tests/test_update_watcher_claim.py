"""The root watcher installs only a release package: under data/updates, not a link, named as a
release asset, declaring the package ucm, and matching the release's .sha256 fetched by root.

packaging/scripts/ucm-watcher.sh runs for real under a temporary root (UCM_WATCHER_ROOT), with
stubs for dpkg, dpkg-deb, apt-get, rpm and systemctl; the release digests come from a directory
standing for GitHub (UCM_WATCHER_RELEASES, honoured under UCM_WATCHER_ROOT only).
"""
import hashlib
import json
import pathlib
import shutil
import subprocess

import pytest

from tests.test_native_setup_script import BASH, _stub

ROOT = pathlib.Path(__file__).resolve().parents[2]
WATCHER = ROOT / 'packaging' / 'scripts' / 'ucm-watcher.sh'
UTILS = ('date', 'tee', 'python3', 'bash', 'rm', 'dirname', 'cat', 'mv', 'cp')

pytestmark = pytest.mark.skipif(BASH is None or shutil.which('python3') is None,
                                reason='bash and python3 are required')


class Host:
    def __init__(self, tmp_path):
        self.tmp = tmp_path
        self.root = tmp_path / 'root'
        self.data = self.root / 'opt/ucm/data'
        (self.data / 'updates').mkdir(parents=True)
        (self.root / 'etc/ucm').mkdir(parents=True)
        (self.root / 'var/log/ucm').mkdir(parents=True)
        (self.root / 'opt/ucm/VERSION').write_text('98.0\n')
        self.releases = tmp_path / 'releases'
        self.bin = tmp_path / 'bin'
        self.bin.mkdir()
        for util in UTILS:
            (self.bin / util).symlink_to(shutil.which(util))
        self.calls = tmp_path / 'calls'
        self.declared = 'ucm'
        installed = f'echo 99.0 > {self.root}/opt/ucm/VERSION'
        _stub(self.bin / 'dpkg', f'echo "dpkg $*" >> {self.calls}\n{installed}')
        _stub(self.bin / 'apt-get', f'echo "apt-get $*" >> {self.calls}')
        _stub(self.bin / 'rpm', f'case "$1" in -qp) cat {tmp_path}/declared;; '
                                f'*) echo "rpm $*" >> {self.calls}; {installed};; esac')
        _stub(self.bin / 'dpkg-deb', f'cat {tmp_path}/declared')
        _stub(self.bin / 'systemctl', 'exit 0')

    def package(self, name='ucm_99.0_all.deb', body=b'genuine package', publish=True,
                published_digest=None):
        path = self.data / 'updates' / name
        path.write_bytes(body)
        if publish:
            digest = published_digest or hashlib.sha256(body).hexdigest()
            (self.releases / 'v99.0').mkdir(parents=True, exist_ok=True)
            (self.releases / 'v99.0' / f'{name}.sha256').write_text(f'{digest}  {name}\n')
        return path

    def run(self, pending, to_version='99.0'):
        (self.tmp / 'declared').write_text(self.declared)
        (self.data / '.update_pending').write_text(str(pending))
        (self.data / '.update_manifest.json').write_text(
            json.dumps({'op_id': 'op', 'to_version': to_version}))
        env = {'PATH': str(self.bin), 'UCM_WATCHER_ROOT': str(self.root),
               'UCM_WATCHER_RELEASES': self.releases.as_uri(), 'TMPDIR': str(self.tmp)}
        done = subprocess.run([BASH, str(WATCHER)], env=env, capture_output=True, text=True)
        assert done.returncode == 0, done.stderr
        calls = self.calls.read_text().splitlines() if self.calls.exists() else []
        return json.loads((self.data / '.update_result.json').read_text()), calls


@pytest.fixture
def host(tmp_path):
    return Host(tmp_path)


def _refused(result, calls, words):
    assert result['status'] == 'failed', result
    assert result['step'] == 'precheck', result
    assert words in result['error'], result
    assert not [c for c in calls if c.startswith(('dpkg', 'rpm', 'apt-get'))], calls


def test_a_release_package_is_installed_from_a_checked_copy(host):
    package = host.package()
    result, calls = host.run(package)
    assert result['status'] == 'installed', result
    assert calls[0].startswith('dpkg -i ')
    installed = calls[0].split(' ', 2)[2]
    assert installed != str(package) and not installed.startswith(str(host.data))
    assert not package.exists()
    assert not pathlib.Path(installed).parent.exists()


def test_a_package_outside_updates_is_refused(host):
    elsewhere = host.tmp / 'anywhere'
    elsewhere.mkdir()
    package = elsewhere / 'ucm_99.0_all.deb'
    package.write_bytes(b'x')
    _refused(*host.run(package), 'not directly under')


def test_a_package_in_a_subdirectory_of_updates_is_refused(host):
    (host.data / 'updates' / 'sub').mkdir()
    package = host.data / 'updates' / 'sub' / 'ucm_99.0_all.deb'
    package.write_bytes(b'x')
    _refused(*host.run(package), 'not directly under')


def test_a_symbolic_link_is_refused(host):
    target = host.tmp / 'evil.deb'
    target.write_bytes(b'genuine package')
    link = host.data / 'updates' / 'ucm_99.0_all.deb'
    link.symlink_to(target)
    (host.releases / 'v99.0').mkdir(parents=True)
    (host.releases / 'v99.0' / 'ucm_99.0_all.deb.sha256').write_text(
        hashlib.sha256(b'genuine package').hexdigest() + '  ucm_99.0_all.deb\n')
    _refused(*host.run(link), 'symbolic link')


@pytest.mark.parametrize('name', ['x.deb', 'ucm_99.0_amd64.deb', 'evil-99.0-1.fc43.noarch.rpm',
                                  'ucm_99.0_all.deb.sha256'])
def test_a_name_that_is_not_a_release_asset_is_refused(host, name):
    _refused(*host.run(host.package(name)), 'not one of a UCM release')


def test_a_package_unlike_the_release_digest_is_refused(host):
    package = host.package(published_digest=hashlib.sha256(b'the real one').hexdigest())
    _refused(*host.run(package), 'does not match the release digest')


def test_a_release_without_a_digest_is_refused(host):
    _refused(*host.run(host.package(publish=False)), 'could not fetch the release digest')


def test_a_manifest_without_a_target_version_is_refused(host):
    _refused(*host.run(host.package(), to_version=''), 'no valid target version')


def test_a_package_not_named_ucm_is_refused(host):
    host.declared = 'openssh-server'
    _refused(*host.run(host.package()), 'not named ucm')


def test_an_rpm_without_dnf_or_yum_is_upgraded_without_force(host):
    package = host.package('ucm-el9-99.0-1.el9.noarch.rpm')
    result, calls = host.run(package)
    assert result['status'] == 'installed', result
    assert len(calls) == 1 and calls[0].startswith('rpm -U ') and '--force' not in calls[0], calls


def test_a_release_candidate_asset_name_is_accepted(host):
    name = 'ucm_99.0.rc1_all.deb'
    body = b'rc package'
    path = host.data / 'updates' / name
    path.write_bytes(body)
    (host.releases / 'v99.0-rc1').mkdir(parents=True)
    # The digest line keeps the package's own name, with its tilde
    (host.releases / 'v99.0-rc1' / f'{name}.sha256').write_text(
        hashlib.sha256(body).hexdigest() + '  ucm_99.0~rc1_all.deb\n')
    (host.root / 'opt/ucm/VERSION').write_text('98.0\n')
    result, calls = host.run(path, to_version='99.0-rc1')
    assert calls and calls[0].startswith('dpkg -i '), (result, calls)
