"""DEB and RPM scripts grant no sudo and drop the sudoers files older packages wrote.

Only the delimited fragment is executed, with /etc/sudoers.d redirected into tmp_path.
Tests marked "text guard" read script text and do not run it.
"""
import re
import pathlib
import subprocess

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[2]
SCRIPTS = {
    'packaging/debian/postinst': ('ucm-service', 'ucm'),
    'packaging/rpm/ucm.spec': ('ucm-service', 'ucm'),
}
OTHER = 'unrelated-admin-rule'


def _fragment(script):
    text = (ROOT / script).read_text(encoding='utf-8')
    return text.split('# sudoers-cleanup:', 1)[1].split('# end sudoers-cleanup', 1)[0]


def _confine(body, root):
    """Fail closed: after redirection no absolute path may point outside root."""
    assert '/etc/sudoers.d' in body
    body = body.replace('/etc/sudoers.d', str(root / 'etc/sudoers.d'))
    ok = str(root / 'etc/sudoers.d') + '/'
    stray = [t for t in re.findall(r'(?<![\w.])/[\w./-]*', body) if not t.startswith(ok) or '..' in t]
    assert not stray, f'refusing to run, path outside the sandbox: {stray}'
    return body


def test_confine_refuses_another_spelling_of_the_path(tmp_path):
    for odd in ('rm -f /etc//sudoers.d/ucm', 'rm -f /etc/./sudoers.d/ucm', 'rm -f /etc/sudoers.d/ucm /etc/sudoers.d/x\nrm -f /etc/sudoers.d/../shadow', 'rm -f /etc/sudoers.d/ucm; rm -f /var/x'):
        with pytest.raises(AssertionError):
            _confine(odd, tmp_path)
    assert str(tmp_path) in _confine('rm -f /etc/sudoers.d/ucm', tmp_path)


def _run(script, root):
    body = _confine('# sudoers-cleanup:' + _fragment(script), root)
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
def test_the_script_writes_no_sudoers_file_text_guard(script):
    text = (ROOT / script).read_text(encoding='utf-8')
    outside = text.replace(_fragment(script), '')
    for line in outside.splitlines():
        assert not ('sudoers.d' in line and ('>' in line or ' cp ' in line or 'install ' in line)), line


def test_the_sudoers_source_is_not_shipped_text_guard():
    assert not (ROOT / 'packaging/sudoers').exists()
    assert 'sudoers' not in (ROOT / 'packaging/debian/rules').read_text(encoding='utf-8')


@pytest.mark.parametrize('wf', ['build-release.yml', 'test-channel.yml'])
def test_deb_build_jobs_install_pip_and_setuptools_text_guard(wf):
    text = (ROOT / '.github/workflows' / wf).read_text(encoding='utf-8')
    lines = [ln.split() for ln in text.splitlines() if 'apt-install.sh' in ln and 'debhelper' in ln]
    assert lines and all('python3-pip' in w and 'python3-setuptools' in w for w in lines)


def test_deb_daemon_reload_never_fails_the_install_text_guard():
    text = (ROOT / 'packaging/debian' / ('post' + 'inst')).read_text(encoding='utf-8')
    lines = [ln.strip() for ln in text.splitlines() if ln.strip().startswith('systemctl daemon-reload')]
    assert lines and all(ln.endswith('|| true') for ln in lines), lines
