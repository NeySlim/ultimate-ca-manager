"""The root watcher installs only a release package: under data/updates, not a link, named as a
release asset, declaring the package ucm, and matching the release's .sha256 fetched by root.

packaging/scripts/ucm-watcher.sh runs for real under a temporary root (UCM_WATCHER_ROOT), with
stubs for dpkg, dpkg-query, dpkg-deb, apt-get, rpm and systemctl; the release digests come from a
directory standing for GitHub (UCM_WATCHER_RELEASES, honoured under UCM_WATCHER_ROOT only).
The stubs compare versions as dpkg and rpm do for the forms UCM releases take (X.Y, X.Y~rcN).
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
UTILS = ('date', 'tee', 'python3', 'bash', 'rm', 'dirname', 'cat', 'mv', 'cp', 'tr')

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
        # The ucm version in root's package database, and the one the package declares
        self.in_database = '98.0'
        self.declares = None
        stub_version_tools(self.bin, tmp_path)
        installed = f'echo 99.0 > {self.root}/opt/ucm/VERSION'
        _stub(self.bin / 'dpkg', f'{DPKG_COMPARE}\necho "dpkg $*" >> {self.calls}\n{installed}')
        _stub(self.bin / 'apt-get', f'echo "apt-get $*" >> {self.calls}')
        _stub(self.bin / 'rpm', f'case "$1" in -qp) case "$3" in *NAME*) cat {tmp_path}/declared;; '
                                f'*) cat {tmp_path}/declares;; esac;; -q) cat {tmp_path}/in_database;; '
                                f'--eval) "$(dirname "$0")/vercmp" lua "$2";; '
                                f'*) echo "rpm $*" >> {self.calls}; {installed};; esac')
        _stub(self.bin / 'dpkg-deb', f'case "$3" in Package) cat {tmp_path}/declared;; '
                                     f'*) cat {tmp_path}/declares;; esac')
        _stub(self.bin / 'systemctl', 'exit 0')

    def package(self, name='ucm_99.0_all.deb', body=b'genuine package', publish=True,
                published_digest=None, prefix=''):
        path = self.data / 'updates' / (prefix + name)
        path.write_bytes(body)
        if publish:
            digest = published_digest or hashlib.sha256(body).hexdigest()
            (self.releases / 'v99.0').mkdir(parents=True, exist_ok=True)
            (self.releases / 'v99.0' / f'{name}.sha256').write_text(f'{digest}  {name}\n')
        return path

    def run(self, pending, to_version='99.0', manifest=True):
        """pending: the trigger's text, or None when the test laid .update_pending itself."""
        (self.tmp / 'declared').write_text(self.declared)
        (self.tmp / 'in_database').write_text(self.in_database)
        (self.tmp / 'declares').write_text(self.declares or to_version.replace('-', '~'))
        if pending is not None:
            (self.data / '.update_pending').write_text(str(pending))
        if manifest:
            (self.data / '.update_manifest.json').write_text(
                json.dumps({'op_id': 'op', 'to_version': to_version}))
        env = {'PATH': str(self.bin), 'UCM_WATCHER_ROOT': str(self.root),
               'UCM_WATCHER_RELEASES': self.releases.as_uri(), 'TMPDIR': str(self.tmp)}
        done = self.done = subprocess.run([BASH, str(WATCHER)], env=env, capture_output=True, text=True)
        assert done.returncode == 0, done.stderr
        calls = self.calls.read_text().splitlines() if self.calls.exists() else []
        return json.loads((self.data / '.update_result.json').read_text()), calls


VERCMP = """import re, sys
def key(v):
    main, _, pre = v.partition("~")
    return tuple(int(n) for n in main.split(".")), 0 if pre else 1, pre
a, b = re.findall(r"'([^']*)'", sys.argv[2]) if sys.argv[1] == "lua" else sys.argv[1:3]
print((key(a) > key(b)) - (key(a) < key(b)))
"""
# dpkg --compare-versions A gt B, answered by the vercmp stub
DPKG_COMPARE = ('if [ "$1" = --compare-versions ]; then [ "$3" = gt ] || exit 2; '
                '[ "$("$(dirname "$0")/vercmp" "$2" "$4")" = 1 ]; exit; fi')


def stub_version_tools(bin_dir, tmp_path):
    """vercmp, and dpkg-query reading tmp_path/in_database."""
    (bin_dir / 'vercmp').write_text(f'#!{shutil.which("python3")}\n{VERCMP}')
    (bin_dir / 'vercmp').chmod(0o755)
    _stub(bin_dir / 'dpkg-query', f'cat {tmp_path}/in_database')


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
    # The service account wrote that path: root deletes nothing outside updates/
    assert package.read_bytes() == b'x'


def test_any_file_named_by_the_trigger_is_left_alone(host):
    victim = host.tmp / 'shadow'
    victim.write_bytes(b'precious')
    _refused(*host.run(victim), 'not directly under')
    assert victim.read_bytes() == b'precious'


def test_updates_as_a_link_deletes_nothing_where_it_leads(host):
    elsewhere = host.tmp / 'elsewhere'
    elsewhere.mkdir()
    victim = elsewhere / 'ucm_99.0_all.deb'
    victim.write_bytes(b'precious')
    shutil.rmtree(host.data / 'updates')
    (host.data / 'updates').symlink_to(elsewhere)
    _refused(*host.run(host.data / 'updates' / 'ucm_99.0_all.deb'), 'not directly under')
    assert victim.read_bytes() == b'precious'


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
    assert target.read_bytes() == b'genuine package'



def test_a_package_over_one_gib_is_refused(host):
    path = host.data / 'updates' / 'ucm_99.0_all.deb'
    with open(path, 'wb') as f:
        f.truncate((1 << 30) + 1)
    _refused(*host.run(path), 'over 1 GiB')
    assert not list(host.tmp.glob('ucm-update.*'))

@pytest.mark.parametrize('name', ['x.deb', 'ucm_99.0_amd64.deb', 'evil-99.0-1.fc43.noarch.rpm',
                                  'ucm_99.0_all.deb.sha256'])
def test_a_name_that_is_not_a_release_asset_is_refused(host, name):
    _refused(*host.run(host.package(name)), 'not one of a UCM release')


def test_a_package_unlike_the_release_digest_is_refused(host):
    package = host.package(published_digest=hashlib.sha256(b'the real one').hexdigest())
    _refused(*host.run(package), 'does not match the release digest')
    assert not package.exists()


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


@pytest.mark.parametrize('name', ['ucm_99.0_all.deb', 'ucm-el9-99.0-1.el9.noarch.rpm'])
def test_a_rolling_update_download_named_by_its_turn_is_installed(host, name):
    # update_campaign names each turn's download <12 hex>-<asset>; the digest is the asset's
    package = host.package(name, prefix='26792dcad0d0-')
    result, calls = host.run(package)
    assert result['status'] == 'installed', result
    installed = calls[0].split()[-1]
    assert pathlib.Path(installed).name == name


FAMILIES = ['ucm_99.0_all.deb', 'ucm-99.0-1.fc43.noarch.rpm']


@pytest.mark.parametrize('name', FAMILIES)
@pytest.mark.parametrize('in_database', ['99.5', '99.0'])
def test_a_target_not_above_the_installed_package_is_refused(host, name, in_database):
    # A genuine older (or the same) release would reopen what the installed one fixed
    host.in_database = in_database
    package = host.package(name)
    _refused(*host.run(package), 'is not above the installed version')


@pytest.mark.parametrize('name', FAMILIES)
def test_a_release_candidate_is_upgraded_to_its_stable(host, name):
    host.in_database = '99.0~rc1'
    result, calls = host.run(host.package(name))
    assert result['status'] == 'installed', result


@pytest.mark.parametrize('name', FAMILIES)
def test_a_package_declaring_another_version_than_the_target_is_refused(host, name):
    host.declares = '97.0'
    _refused(*host.run(host.package(name)), 'not the update target')


def test_an_unreadable_package_database_refuses_the_update(host):
    host.in_database = ''
    _refused(*host.run(host.package()), 'cannot be read from the package database')


def test_a_refused_precheck_leaves_no_copy_in_roots_temporary_directory(host):
    setup = host.root / 'opt/ucm/scripts/native-setup.sh'
    setup.parent.mkdir(parents=True)
    setup.write_text('echo "no compiler for the FIPS build"; exit 1\n')
    result, calls = host.run(host.package())
    _refused(result, calls, 'no compiler')
    assert not list(host.tmp.glob('ucm-update.*'))
