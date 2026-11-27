"""The root watcher installs only a release package: under data/updates, not a link, named as a
release asset, declaring the package ucm at the target version above the installed one, and
matching the release's .sha256 fetched by root. A refusal installs nothing, clears the request
and leaves the service running.

packaging/scripts/ucm-watcher.sh runs for real under a temporary root (UCM_WATCHER_ROOT), with
stubs for dpkg, dpkg-query, dpkg-deb, apt-get, rpm, dnf, yum and systemctl; the release digests
come from a directory standing for GitHub (UCM_WATCHER_RELEASES, honoured under UCM_WATCHER_ROOT
only). The stubs compare versions as dpkg and rpm do for the forms UCM releases take.
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
UTILS = ('date', 'tee', 'python3', 'bash', 'rm', 'dirname', 'cat', 'mv', 'cp', 'tr', 'sed')

pytestmark = pytest.mark.skipif(BASH is None or shutil.which('python3') is None,
                                reason='bash and python3 are required')

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


def stub_version_tools(bin_dir, state):
    """vercmp, and dpkg-query reading state/in_database."""
    (bin_dir / 'vercmp').write_text(f'#!{shutil.which("python3")}\n{VERCMP}')
    (bin_dir / 'vercmp').chmod(0o755)
    _stub(bin_dir / 'dpkg-query', f'cat {state}/in_database')


class Host:
    def __init__(self, tmp_path, installed='98.0', target='99.0'):
        self.tmp = tmp_path
        self.root = tmp_path / 'root'
        self.data = self.root / 'opt/ucm/data'
        self.target = target
        (self.data / 'updates').mkdir(parents=True)
        (self.root / 'etc/ucm').mkdir(parents=True)
        (self.root / 'var/log/ucm').mkdir(parents=True)
        (self.root / 'opt/ucm/VERSION').write_text(installed + '\n')
        self.releases = tmp_path / 'releases'
        self.bin = tmp_path / 'bin'
        self.bin.mkdir()
        for util in UTILS:
            (self.bin / util).symlink_to(shutil.which(util))
        self.calls = tmp_path / 'calls'
        self.declared = 'ucm'
        # The ucm version in root's package database, and the one the package declares
        self.in_database = installed.replace('-', '~')
        self.declares = None
        stub_version_tools(self.bin, tmp_path)
        self.installs = f'echo {target} > {self.root}/opt/ucm/VERSION'
        _stub(self.bin / 'dpkg', f'{DPKG_COMPARE}\necho "dpkg $*" >> {self.calls}\n{self.installs}')
        _stub(self.bin / 'apt-get', f'echo "apt-get $*" >> {self.calls}')
        _stub(self.bin / 'rpm', f'case "$1" in -qp) case "$3" in *NAME*) cat {tmp_path}/declared;; '
                                f'*) cat {tmp_path}/declares;; esac;; -q) cat {tmp_path}/in_database;; '
                                f'--eval) "$(dirname "$0")/vercmp" lua "$2";; '
                                f'*) echo "rpm $*" >> {self.calls}; {self.installs};; esac')
        _stub(self.bin / 'dpkg-deb', f'case "$3" in Package) cat {tmp_path}/declared;; '
                                     f'*) cat {tmp_path}/declares;; esac')
        _stub(self.bin / 'systemctl', f'echo "systemctl $*" >> {self.calls}')

    def tool(self, name):
        """Puts dnf or yum on the PATH: it records its arguments and installs the target."""
        _stub(self.bin / name, f'echo "{name} $*" >> {self.calls}\n{self.installs}')

    def package(self, name=None, body=b'genuine package', publish=True, published_digest=None,
                tag=None, line_name=None):
        name = name or f'ucm_{self.target}_all.deb'
        path = self.data / 'updates' / name
        path.write_bytes(body)
        if publish:
            digest = published_digest or hashlib.sha256(body).hexdigest()
            release = self.releases / f'v{tag or self.target}'
            release.mkdir(parents=True, exist_ok=True)
            (release / f'{name}.sha256').write_text(f'{digest}  {line_name or name}\n')
        return path

    def run(self, pending, to_version=None, manifest=True):
        """pending: the trigger's text, or None when the test laid .update_pending itself."""
        to_version = self.target if to_version is None else to_version
        (self.tmp / 'declared').write_text(self.declared)
        (self.tmp / 'in_database').write_text(self.in_database)
        (self.tmp / 'declares').write_text(self.declares or to_version.replace('-', '~'))
        if pending is not None:
            (self.data / '.update_pending').write_text(str(pending))
        if manifest:
            (self.data / '.update_manifest.json').write_text(
                json.dumps({'op_id': 'op', 'from_version': '98.0', 'to_version': to_version}))
        env = {'PATH': str(self.bin), 'UCM_WATCHER_ROOT': str(self.root),
               'UCM_WATCHER_RELEASES': self.releases.as_uri(), 'TMPDIR': str(self.tmp)}
        done = self.done = subprocess.run([BASH, str(WATCHER)], env=env, capture_output=True, text=True)
        assert done.returncode == 0, done.stderr
        calls = self.calls.read_text().splitlines() if self.calls.exists() else []
        return json.loads((self.data / '.update_result.json').read_text()), calls


@pytest.fixture
def host(tmp_path):
    return Host(tmp_path)


def _refused(result, calls, words, host=None):
    assert result['status'] == 'failed', result
    assert result['step'] == 'precheck', result
    assert words in result['error'], result
    assert not [c for c in calls if c.startswith(('dpkg', 'rpm', 'apt-get', 'dnf', 'yum'))], calls
    # A refusal leaves the service running and clears the request
    assert not [c for c in calls if c.startswith('systemctl')], calls
    if host is not None:
        assert not (host.data / '.update_pending').exists()
        assert (host.root / 'opt/ucm/VERSION').read_text().strip() == '98.0'
        assert not list(host.tmp.glob('ucm-update.*'))


def test_a_release_package_is_installed_from_a_checked_copy(host):
    package = host.package()
    result, calls = host.run(package)
    assert result['status'] == 'installed', result
    assert calls[0].startswith('dpkg -i ')
    installed = calls[0].split(' ', 2)[2]
    assert installed != str(package) and not installed.startswith(str(host.data))
    assert pathlib.Path(installed).name == package.name
    assert not package.exists()
    assert not pathlib.Path(installed).parent.exists()
    assert calls[-1] == 'systemctl restart ucm', calls


def test_the_copy_is_what_gets_installed_when_the_download_changes_after_the_check(host):
    """The service account may rewrite its download once root has read it: root installs its copy."""
    package = host.package()
    _stub(host.bin / 'dpkg', f'{DPKG_COMPARE}\necho "dpkg $*" >> {host.calls}\n'
                             f'cat "$2" > {host.tmp}/installed-body\n{host.installs}')
    result, _ = host.run(package)
    assert result['status'] == 'installed', result
    assert (host.tmp / 'installed-body').read_bytes() == b'genuine package'


def test_a_package_outside_updates_is_refused(host):
    elsewhere = host.tmp / 'anywhere'
    elsewhere.mkdir()
    package = elsewhere / 'ucm_99.0_all.deb'
    package.write_bytes(b'x')
    _refused(*host.run(package), 'not directly under', host)
    # The service account wrote that path: root deletes nothing outside updates/
    assert package.read_bytes() == b'x'


def test_any_file_named_by_the_trigger_is_left_alone(host):
    victim = host.tmp / 'shadow'
    victim.write_bytes(b'precious')
    _refused(*host.run(victim), 'not directly under', host)
    assert victim.read_bytes() == b'precious'


def test_a_path_climbing_out_of_updates_is_refused(host):
    elsewhere = host.data / 'ucm_99.0_all.deb'
    elsewhere.write_bytes(b'x')
    _refused(*host.run(f'{host.data}/updates/../ucm_99.0_all.deb'), 'not directly under', host)
    assert elsewhere.read_bytes() == b'x'


def test_updates_as_a_link_deletes_nothing_where_it_leads(host):
    elsewhere = host.tmp / 'elsewhere'
    elsewhere.mkdir()
    victim = elsewhere / 'ucm_99.0_all.deb'
    victim.write_bytes(b'precious')
    shutil.rmtree(host.data / 'updates')
    (host.data / 'updates').symlink_to(elsewhere)
    _refused(*host.run(host.data / 'updates' / 'ucm_99.0_all.deb'), 'not directly under', host)
    assert victim.read_bytes() == b'precious'


def test_a_package_in_a_subdirectory_of_updates_is_refused(host):
    (host.data / 'updates' / 'sub').mkdir()
    package = host.data / 'updates' / 'sub' / 'ucm_99.0_all.deb'
    package.write_bytes(b'x')
    _refused(*host.run(package), 'not directly under', host)


def test_a_symbolic_link_is_refused(host):
    target = host.tmp / 'evil.deb'
    target.write_bytes(b'genuine package')
    link = host.data / 'updates' / 'ucm_99.0_all.deb'
    link.symlink_to(target)
    (host.releases / 'v99.0').mkdir(parents=True)
    (host.releases / 'v99.0' / 'ucm_99.0_all.deb.sha256').write_text(
        hashlib.sha256(b'genuine package').hexdigest() + '  ucm_99.0_all.deb\n')
    _refused(*host.run(link), 'symbolic link', host)
    assert target.read_bytes() == b'genuine package'


@pytest.mark.parametrize('name', ['x.deb', 'ucm_99.0_amd64.deb', 'evil-99.0-1.fc43.noarch.rpm',
                                  'ucm_99.0_all.deb.sha256', 'ucm.rpm'])
def test_a_name_that_is_not_a_release_asset_is_refused(host, name):
    _refused(*host.run(host.package(name)), 'not one of a UCM release', host)


def test_a_package_unlike_the_release_digest_is_refused(host):
    package = host.package(published_digest=hashlib.sha256(b'the real one').hexdigest())
    result, calls = host.run(package)
    _refused(result, calls, 'does not match the release digest', host)
    assert 'does not match the release digest' in host.done.stdout
    assert not package.exists()


def test_a_release_without_a_digest_is_refused(host):
    _refused(*host.run(host.package(publish=False)), 'could not fetch the release digest', host)
    assert 'could not fetch the release digest' in host.done.stdout


def test_the_digest_of_another_package_does_not_cover_this_one(host):
    package = host.package(line_name='ucm-el9-99.0-1.el9.noarch.rpm')
    _refused(*host.run(package), 'does not match the release digest', host)


def test_the_digest_comes_from_the_target_release(host):
    # Published under another release only: the target's .sha256 is the one that counts
    host.package(tag='97.0')
    _refused(*host.run(host.data / 'updates' / 'ucm_99.0_all.deb'), 'could not fetch the release digest', host)


def test_a_manifest_without_a_target_version_is_refused(host):
    _refused(*host.run(host.package(), to_version=''), 'no valid target version', host)


def test_a_missing_manifest_is_refused(host):
    _refused(*host.run(host.package(), manifest=False), 'no valid target version', host)


def test_a_package_not_named_ucm_is_refused(host):
    host.declared = 'openssh-server'
    _refused(*host.run(host.package()), 'not named ucm', host)


def test_an_rpm_without_dnf_or_yum_is_upgraded_without_force(host):
    package = host.package('ucm-el9-99.0-1.el9.noarch.rpm')
    result, calls = host.run(package)
    assert result['status'] == 'installed', result
    assert calls[0].startswith('rpm -U ') and '--force' not in calls[0], calls
    assert calls[1:] == ['systemctl restart ucm'], calls


@pytest.mark.parametrize('tool,verb', [('dnf', 'dnf install -y '), ('yum', 'yum localinstall -y ')])
def test_dnf_and_yum_install_the_checked_copy(host, tool, verb):
    host.tool(tool)
    package = host.package('ucm-99.0-1.fc43.noarch.rpm')
    result, calls = host.run(package)
    assert result['status'] == 'installed', result
    assert calls[0].startswith(verb), calls
    installed = calls[0][len(verb):]
    assert pathlib.Path(installed).name == package.name and not installed.startswith(str(host.data))


@pytest.mark.parametrize('tool', ['dnf', 'yum'])
def test_dnf_and_yum_install_nothing_refused(host, tool):
    host.tool(tool)
    package = host.package('ucm-99.0-1.fc43.noarch.rpm', published_digest='0' * 64)
    _refused(*host.run(package), 'does not match the release digest', host)


def test_a_release_candidate_asset_name_is_accepted(host):
    name = 'ucm_99.0.rc1_all.deb'
    # The digest line keeps the package's own name, with its tilde
    path = host.package(name, tag='99.0-rc1', line_name='ucm_99.0~rc1_all.deb')
    result, calls = host.run(path, to_version='99.0-rc1')
    assert calls and calls[0].startswith('dpkg -i '), (result, calls)


FAMILIES = ['ucm_99.0_all.deb', 'ucm-99.0-1.fc43.noarch.rpm']


@pytest.mark.parametrize('name', FAMILIES)
@pytest.mark.parametrize('in_database', ['99.5', '99.0'])
def test_a_target_not_above_the_installed_package_is_refused(host, name, in_database):
    # A genuine older (or the same) release would reopen what the installed one fixed
    host.in_database = in_database
    _refused(*host.run(host.package(name)), 'is not above the installed version', host)


@pytest.mark.parametrize('name', FAMILIES)
def test_a_release_candidate_is_upgraded_to_its_stable(host, name):
    host.in_database = '99.0~rc1'
    result, calls = host.run(host.package(name))
    assert result['status'] == 'installed', result


@pytest.mark.parametrize('name', FAMILIES)
def test_a_package_declaring_another_version_than_the_target_is_refused(host, name):
    host.declares = '97.0'
    _refused(*host.run(host.package(name)), 'not the update target', host)


def test_an_unreadable_package_database_refuses_the_update(host):
    host.in_database = ''
    _refused(*host.run(host.package()), 'cannot be read from the package database', host)


def test_a_refused_precheck_leaves_no_copy_in_roots_temporary_directory(host):
    setup = host.root / 'opt/ucm/scripts/native-setup.sh'
    setup.parent.mkdir(parents=True)
    setup.write_text('echo "no compiler for the FIPS build"; exit 1\n')
    _refused(*host.run(host.package()), 'no compiler', host)


def test_a_refusal_leaves_a_restart_asked_for_to_its_own_run(host):
    (host.data / '.restart_requested').write_text('')
    _refused(*host.run(host.package(publish=False)), 'could not fetch the release digest', host)
    assert (host.data / '.restart_requested').exists()
