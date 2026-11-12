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
    """Fail closed: after redirection every path is a file of root's sudoers.d, and nothing
    expands or moves at run time (the suite runs as root on a host that has these files)."""
    assert '/etc/sudoers.d/' in body
    body = body.replace('/etc/sudoers.d/', f'{root}/etc/sudoers.d/')
    code = '\n'.join(line for line in body.splitlines() if not line.lstrip().startswith('#'))
    assert not re.search(r'[$~`\\]|\.\.|\bcd\b', code), 'refusing to run, the fragment expands or moves'
    ok = f'{root}/etc/sudoers.d/'
    # Any word holding a slash, relative ones included
    stray = [t for t in re.findall(r'[^\s;|&<>()"\']*/[^\s;|&<>()"\']*', code)
             if not t.startswith(ok) or '/' in t[len(ok):] or '//' in t]
    assert not stray, f'refusing to run, path outside the sandbox: {stray}'
    return body


@pytest.mark.parametrize('odd', [
    '/etc//sudoers.d/ucm', '/etc/./sudoers.d/ucm', '/etc/sudoers.d/../shadow', '/var/x',
    '/etc/sudoers.dX/ucm', '"$UCM_CONFIG/sudoers"', '$HOME/x', '~root/x', '$(printf x)',
    '`printf x`', 'x\\', 'x; cd', 'etc/sudoers.d/ucm', 'x/../../root'])
def test_confine_refuses_what_leaves_or_expands_out_of_the_sandbox(tmp_path, odd):
    # The suite runs as root on a host that has these files: nothing may expand at run time
    with pytest.raises(AssertionError):
        _confine(f'rm -f /etc/sudoers.d/ucm {odd}\n', tmp_path)


def test_confine_keeps_a_fragment_naming_only_the_sandbox(tmp_path):
    body = _confine('# drop the files (the watcher restarts it)\nrm -f /etc/sudoers.d/ucm-service /etc/sudoers.d/ucm\n',
                    tmp_path)
    assert f'{tmp_path}/etc/sudoers.d/ucm-service' in body


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
