"""DEB and RPM scripts grant no sudo and drop the sudoers files older packages wrote.

Only the delimited fragment is executed, with /etc/sudoers.d redirected into tmp_path.
"""
import pathlib
import subprocess

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[2]
SCRIPTS = {
    'packaging/debian/postinst': ('ucm-service', 'ucm'),
    'packaging/rpm/ucm.spec': ('ucm',),
}
OTHER = 'unrelated-admin-rule'


def _fragment(script):
    text = (ROOT / script).read_text(encoding='utf-8')
    return text.split('# sudoers-cleanup:', 1)[1].split('# end sudoers-cleanup', 1)[0]


def _run(script, root):
    body = '# sudoers-cleanup:' + _fragment(script)
    assert '/etc/sudoers.d' in body
    body = body.replace('/etc/sudoers.d', str(root / 'etc/sudoers.d'))
    return subprocess.run(['bash', '-e', '-c', body], capture_output=True, text=True, cwd=root)


@pytest.mark.parametrize('script', SCRIPTS)
def test_legacy_file_is_removed_and_others_kept(script, tmp_path):
    d = tmp_path / 'etc/sudoers.d'
    d.mkdir(parents=True)
    for name in (*SCRIPTS[script], OTHER):
        (d / name).write_text('x\n')
    assert _run(script, tmp_path).returncode == 0
    assert [p.name for p in d.iterdir()] == [OTHER]


@pytest.mark.parametrize('script', SCRIPTS)
def test_succeeds_without_sudoers_directory_and_creates_nothing(script, tmp_path):
    assert _run(script, tmp_path).returncode == 0
    assert not (tmp_path / 'etc').exists()


@pytest.mark.parametrize('script', SCRIPTS)
def test_the_script_writes_no_sudoers_file(script):
    text = (ROOT / script).read_text(encoding='utf-8')
    outside = text.replace(_fragment(script), '')
    for line in outside.splitlines():
        assert not ('sudoers.d' in line and ('>' in line or ' cp ' in line or 'install ' in line)), line


def test_the_sudoers_source_is_not_shipped():
    assert not (ROOT / 'packaging/sudoers').exists()
    assert 'sudoers' not in (ROOT / 'packaging/debian/rules').read_text(encoding='utf-8')


def test_build_job_installs_python3_pip():
    wf = (ROOT / '.github/workflows/build-release.yml').read_text(encoding='utf-8')
    assert any('apt-install.sh' in ln and 'debhelper' in ln and 'python3-pip' in ln.split() for ln in wf.splitlines())


def test_deb_daemon_reload_never_fails_the_install():
    text = (ROOT / 'packaging/debian' / ('post' + 'inst')).read_text(encoding='utf-8')
    lines = [ln.strip() for ln in text.splitlines() if ln.strip().startswith('systemctl daemon-reload')]
    assert lines and all(ln.endswith('|| true') for ln in lines), lines
