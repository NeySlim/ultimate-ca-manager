"""Docker image: code, venv and start scripts are root's; the account owns only what it writes."""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
# What the service writes: its data volume, its logs, its configuration (dns-hooks excepted)
ACCOUNT_TREES = {'/opt/ucm/data', '/var/log/ucm', '/etc/ucm'}


def _instructions():
    """Dockerfile instructions, continuation lines joined, comments dropped."""
    text = re.sub(r'\\\n', ' ', (ROOT / 'Dockerfile').read_text())
    return [line.strip() for line in text.splitlines() if line.strip() and not line.lstrip().startswith('#')]


def test_no_copy_gives_a_file_to_the_account():
    copies = [i for i in _instructions() if i.startswith(('COPY ', 'ADD '))]
    assert any('backend/' in c for c in copies) and any('entrypoint.sh' in c for c in copies)
    given = [c for c in copies if '--chown' in c]
    assert given == [], given


def test_only_the_written_trees_are_chowned_to_the_account():
    runs = ' '.join(i for i in _instructions() if i.startswith('RUN '))
    # chown [options] owner paths..., up to the end of its command
    found = [(owner, paths.split()) for owner, paths in
             re.findall(r'\bchown\s+(?:-\S+\s+)*(\S+)\s+([^&;|]*)', runs)]
    assert found, 'the image no longer gives its data to the account'
    given = [p for owner, paths in found if owner.split(':')[0] == 'ucm' for p in paths]
    assert sorted(given) == sorted(ACCOUNT_TREES), found
    # The dns-hooks directory is made root's after the account receives /etc/ucm
    assert runs.index('chown -R ucm:ucm') < runs.index('install -d -o root -g root -m 0755 /etc/ucm/dns-hooks')


def test_no_group_or_other_write_is_left_on_root_files():
    # COPY keeps the build context's modes: a group- or world-writable file would stay writable
    runs = ' '.join(i for i in _instructions() if i.startswith('RUN '))
    assert re.search(r'find /opt/ucm /entrypoint\.sh [^&;]*-perm /022[^&;]*chmod go-w', runs), runs
