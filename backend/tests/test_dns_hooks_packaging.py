"""Every package keeps /etc/ucm/dns-hooks root's: the ownership steps never give it to ucm."""
import os
import re
import subprocess
from pathlib import Path

import pytest

from tests.test_native_setup_script import chowned, tracing_python

ROOT = Path(__file__).resolve().parents[2]


def _package_chown_line(path):
    """The ownership step on the configuration directory, as a package writes it."""
    found = [l.strip() for l in (ROOT / path).read_text().splitlines()
             if 'own chown-tree' in l and 'UCM_CONFIG' in l and not l.strip().startswith('#')]
    assert len(found) == 1, (path, found)
    return found[0].replace('%{name}', '1')


def _hook_layout(tmp_path):
    config = tmp_path / 'etc-ucm'
    (config / 'dns-hooks').mkdir(parents=True)
    (config / 'dns-hooks' / 'hook.sh').write_text('#!/bin/sh\n')
    (config / 'ucm.env').write_text('X=1\n')
    (config / 'sub').mkdir()
    (config / 'sub' / 'dns-hooks').write_text('not the hook directory\n')
    return config


@pytest.mark.parametrize('path', ['packaging/debian/postinst', 'packaging/rpm/ucm.spec'])
def test_the_package_chown_skips_the_hook_directory(tmp_path, path):
    line = _package_chown_line(path)
    assert line.startswith('bash "$UCM_SETUP" own chown-tree "$UCM_CONFIG/" '), line
    config = _hook_layout(tmp_path)
    python, trace = tracing_python(tmp_path)
    env = {'PATH': os.environ['PATH'], 'UCM_CONFIG': str(config), 'UCM_USER': '1', 'UCM_GROUP': '1',
           'UCM_SETUP': str(ROOT / 'packaging/scripts/native-setup.sh'), 'UCM_PYTHON': python}
    subprocess.run(['/bin/sh', '-c', line], check=True, env=env)
    given = chowned(trace)
    assert {str(config), str(config / 'ucm.env'), str(config / 'sub' / 'dns-hooks')} <= set(given), given
    assert str(config / 'dns-hooks') not in given and str(config / 'dns-hooks' / 'hook.sh') not in given


def test_the_entrypoint_chown_skips_the_hook_directory(tmp_path):
    found = [l.strip() for l in (ROOT / 'docker/entrypoint.sh').read_text().splitlines()
             if 'chown' in l and '/etc/ucm' in l and not l.strip().startswith('#')]
    assert len(found) == 1, found
    line = found[0]
    # Only a find whose action is the chown stub below runs
    assert re.match(r'find /etc/ucm ', line), line
    config = _hook_layout(tmp_path)
    stub = tmp_path / 'bin'
    stub.mkdir()
    trace = tmp_path / 'trace'
    (stub / 'chown').write_text(f'#!/bin/sh\nshift; shift\nfor p; do echo "$p" >> {trace}; done\n')
    (stub / 'chown').chmod(0o755)
    line = line.replace('/etc/ucm', str(config))
    env = {'PATH': f'{stub}:{os.environ["PATH"]}'}
    subprocess.run(['/bin/sh', '-c', line], check=True, env=env)
    given = {os.path.normpath(p) for p in trace.read_text().split()}
    assert str(config / 'ucm.env') in given
    assert str(config / 'sub' / 'dns-hooks') in given
    assert str(config / 'dns-hooks') not in given
    assert str(config / 'dns-hooks' / 'hook.sh') not in given


def test_the_packages_ship_the_hook_directory_root_owned():
    rules = (ROOT / 'packaging/debian/rules').read_text()
    assert re.search(r'^\tinstall -d -m 0755 debian/ucm/etc/ucm/dns-hooks$', rules, re.M)
    spec = (ROOT / 'packaging/rpm/ucm.spec').read_text()
    assert 'install -d -m 0755 %{buildroot}%{_sysconfdir}/%{name}/dns-hooks' in spec
    assert re.search(r'^%dir %attr\(0755,root,root\) %\{_sysconfdir\}/%\{name\}/dns-hooks$', spec, re.M)
    dockerfile = (ROOT / 'Dockerfile').read_text()
    assert 'install -d -o root -g root -m 0755 /etc/ucm/dns-hooks' in dockerfile
    # Made after the chown that gives /etc/ucm to the service account
    assert dockerfile.index('install -d -o root -g root -m 0755 /etc/ucm/dns-hooks') > \
        dockerfile.index('chown -R ucm:ucm /opt/ucm /var/log/ucm /etc/ucm')
