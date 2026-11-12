"""Package scripts no longer write a sudoers file and remove the ones older packages left."""
import re
import subprocess
from pathlib import Path

import pytest

PKG = Path(__file__).resolve().parents[2] / 'packaging'
SCRIPTS = {'deb': PKG / 'debian' / 'postinst', 'rpm': PKG / 'rpm' / 'ucm.spec'}
LEGACY = ('ucm', 'ucm-service')


def _fragment(path):
    m = re.search(r'# BEGIN legacy-sudoers.*?\n(.*?)# END legacy-sudoers', path.read_text(), re.S)
    assert m, 'legacy-sudoers fragment missing'
    return m.group(1)


def _sandboxed(fragment, root):
    """Redirect the hard-coded directory to root; refuse any script still naming a path outside it."""
    script = fragment.replace('/etc/sudoers.d', str(root))
    assert '/etc/' not in script, 'fragment still names /etc'
    for p in re.findall(r'(?<![\w$])/[\w./-]*', script):
        assert p.startswith(str(root)), f'path outside the sandbox: {p}'
    return script


def _run(path, root):
    script = _sandboxed(_fragment(path), root)  # fails closed before anything runs
    return subprocess.run(['sh', '-ec', script], env={'PATH': '/usr/bin:/bin'}, capture_output=True, text=True)


@pytest.mark.parametrize('kind', ['deb', 'rpm'])
def test_removes_both_legacy_names_only(tmp_path, kind):
    sd = tmp_path / 'sudoers.d'
    sd.mkdir()
    for name in (*LEGACY, 'admin-other'):
        (sd / name).write_text('x')
    assert _run(SCRIPTS[kind], sd).returncode == 0
    assert {p.name for p in sd.iterdir()} == {'admin-other'}


@pytest.mark.parametrize('kind', ['deb', 'rpm'])
def test_succeeds_without_sudoers_dir_and_creates_nothing(tmp_path, kind):
    sd = tmp_path / 'absent'
    r = _run(SCRIPTS[kind], sd)
    assert r.returncode == 0, r.stderr
    assert not sd.exists()
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize('spelling', ['/etc//sudoers.d/ucm', '/etc/./sudoers.d/ucm', '/usr/etc/x', '/var/tmp/x'])
def test_sandbox_refuses_a_fragment_with_another_spelling(tmp_path, spelling):
    with pytest.raises(AssertionError):
        _sandboxed(f'rm -f {spelling}\n', tmp_path)


def test_text_guard_scripts_do_not_ship_sudoers():
    """Text guard: reads the package scripts, does not run them."""
    for name in ('debian/postinst', 'rpm/ucm.spec', 'debian/rules'):
        text = (PKG / name).read_text()
        assert not re.search(r'>\s*/etc/sudoers\.d|cp\b.*sudoers|install\b.*sudoers', text), name
    assert not (PKG / 'sudoers').exists()


def test_text_guard_deb_daemon_reload_never_fails_the_install():
    """Text guard: every bare systemctl daemon-reload in the DEB script must be tolerated under set -e."""
    for line in (PKG / 'debian' / 'postinst').read_text().splitlines():
        if re.match(r'\s*systemctl daemon-reload', line):
            assert '|| true' in line, line


def test_text_guard_workflows_install_both_python_build_deps():
    """Text guard: reads the workflow files."""
    root = PKG.parent / '.github' / 'workflows'
    for name in ('build-release.yml', 'test-channel.yml'):
        lines = [l for l in (root / name).read_text().splitlines() if 'debhelper' in l]
        assert lines, name
        assert all('python3-pip' in l and 'python3-setuptools' in l for l in lines), name
