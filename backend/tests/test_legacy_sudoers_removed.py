"""Package scripts no longer write a sudoers file and remove the one older packages left."""
import re
import subprocess
from pathlib import Path

import pytest

PKG = Path(__file__).resolve().parents[2] / 'packaging'
SCRIPTS = {
    'deb': (PKG / 'debian' / 'postinst', 'ucm-service'),
    'rpm': (PKG / 'rpm' / 'ucm.spec', None),
}


def _fragment(path):
    m = re.search(r'# BEGIN legacy-sudoers.*?\n(.*?)# END legacy-sudoers', path.read_text(), re.S)
    assert m, 'legacy-sudoers fragment missing'
    return m.group(1)


def _run(path, root):
    # Only the extracted fragment runs, against a directory under tmp_path.
    return subprocess.run(['sh', '-ec', _fragment(path)], env={'UCM_SUDOERS_DIR': str(root), 'PATH': '/usr/bin:/bin'},
                          capture_output=True, text=True)


@pytest.mark.parametrize('kind', ['deb', 'rpm'])
def test_removes_legacy_files_only(tmp_path, kind):
    path, _ = SCRIPTS[kind]
    sd = tmp_path / 'sudoers.d'
    sd.mkdir()
    for name in ('ucm', 'ucm-service', 'admin-other'):
        (sd / name).write_text('x')
    assert _run(path, sd).returncode == 0
    left = {p.name for p in sd.iterdir()}
    assert 'ucm' not in left and 'admin-other' in left
    assert ('ucm-service' not in left) == (kind == 'deb')


@pytest.mark.parametrize('kind', ['deb', 'rpm'])
def test_succeeds_without_sudoers_dir_and_creates_nothing(tmp_path, kind):
    sd = tmp_path / 'absent'
    r = _run(SCRIPTS[kind][0], sd)
    assert r.returncode == 0, r.stderr
    assert not sd.exists()
    assert list(tmp_path.iterdir()) == []


def test_scripts_do_not_ship_sudoers():
    for name in ('debian/postinst', 'rpm/ucm.spec', 'debian/rules'):
        text = (PKG / name).read_text()
        assert not re.search(r'>\s*/etc/sudoers\.d|cp\b.*sudoers|install\b.*sudoers', text), name
    assert not (PKG / 'sudoers').exists()
