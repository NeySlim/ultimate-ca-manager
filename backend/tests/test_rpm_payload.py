"""The RPM, built from its spec as the release builds it (on a stand-in of the sources):
the data directories it lays down carry the owner and mode the installation gives them."""
import os
import shutil
import subprocess
import tarfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SPEC = ROOT / 'packaging' / 'rpm' / 'ucm.spec'
DATA = '/opt/ucm/data'
# Owner and mode once %post and a first start have run (%post: chown to ucm, data 0750;
# the service: sessions and private 0700)
EXPECTED = {DATA: 0o750, **{f'{DATA}/{d}': 0o755 for d in ('ca', 'certs', 'crl', 'scep', 'backups')},
            f'{DATA}/private': 0o700, f'{DATA}/sessions': 0o700}

pytestmark = pytest.mark.skipif(not shutil.which('rpmbuild'), reason='rpmbuild is not installed')


def _sources(top):
    """The files %install reads: the packaging ones as they are, the application a stand-in."""
    src = top / 'ucm-0.0.0'
    for rel in ('packaging', 'LICENSE', 'NOTICE', 'COMMERCIAL-LICENSE.md', 'VERSION'):
        (shutil.copytree if (ROOT / rel).is_dir() else shutil.copy)(ROOT / rel, src / rel)
    (src / 'backend').mkdir()
    (src / 'backend' / 'requirements.txt').write_text('flask\n')
    (src / 'backend' / 'app.py').write_text('x = 1\n')
    (src / 'frontend' / 'dist').mkdir(parents=True)
    (src / 'frontend' / 'dist' / 'index.html').write_text('<html></html>\n')
    (top / 'SOURCES').mkdir()
    with tarfile.open(top / 'SOURCES' / 'ucm-0.0.0.tar.gz', 'w:gz') as tar:
        tar.add(src, arcname='ucm-0.0.0')


@pytest.fixture(scope='module')
def payload(tmp_path_factory):
    top = tmp_path_factory.mktemp('rpmbuild')
    _sources(top)
    env = {k: v for k, v in os.environ.items() if k != 'SOURCE_DATE_EPOCH'}
    built = subprocess.run(['rpmbuild', '-bb', '--define', f'_topdir {top}',
                            '--define', '_unitdir /usr/lib/systemd/system', str(SPEC)],
                           capture_output=True, text=True, timeout=300, env=env)
    assert built.returncode == 0, built.stderr[-3000:]
    rpm = next((top / 'RPMS' / 'noarch').glob('ucm-0.0.0-1*.rpm'))
    dump = subprocess.run(['rpm', '-qp', '--qf', '[%{FILENAMES}\t%{FILEMODES:octal}\t%{FILEUSERNAME}\t'
                           '%{FILEGROUPNAME}\n]', str(rpm)], capture_output=True, text=True, timeout=60, env=env)
    assert dump.returncode == 0, dump.stderr
    return {path: (int(mode, 8), user, group) for path, mode, user, group
            in (line.split('\t') for line in dump.stdout.splitlines())}


def test_each_data_directory_is_laid_down_as_the_installation_leaves_it(payload):
    got = {p: v for p, v in payload.items() if p == DATA or p.startswith(DATA + '/')}
    assert got == {p: (0o40000 | mode, 'ucm', 'ucm') for p, mode in EXPECTED.items()}


def test_the_package_still_carries_the_application_and_its_scripts(payload):
    for path in ('/opt/ucm/VERSION', '/opt/ucm/requirements.txt', '/opt/ucm/start-ucm.sh',
                 '/opt/ucm/backend/app.py', '/opt/ucm/frontend/dist/index.html',
                 '/opt/ucm/scripts/archive-leftovers.sh', '/usr/lib/systemd/system/ucm.service'):
        assert path in payload, path
