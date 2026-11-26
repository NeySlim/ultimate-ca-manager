"""Every package keeps /etc/ucm/dns-hooks root's: the ownership steps never give it to ucm."""
import os
import re
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]


def _config_chown_lines():
    """The find ... chown step on the configuration directory, as each package writes it."""
    lines = {}
    for name, path in (('postinst', 'packaging/debian/postinst'), ('spec', 'packaging/rpm/ucm.spec')):
        found = [l.strip() for l in (ROOT / path).read_text().splitlines()
                 if l.strip().startswith('find ') and 'chown' in l and 'UCM_CONFIG' in l]
        assert len(found) == 1, (path, found)
        lines[name] = found[0].replace('%{name}', 'svc')
    found = [l.strip() for l in (ROOT / 'docker/entrypoint.sh').read_text().splitlines()
             if 'chown' in l and '/etc/ucm' in l and not l.strip().startswith('#')]
    assert len(found) == 1, found
    lines['entrypoint'] = found[0]
    return lines


@pytest.mark.parametrize('source', ['postinst', 'spec', 'entrypoint'])
def test_the_configuration_chown_skips_the_hook_directory(tmp_path, source):
    line = _config_chown_lines()[source]
    # Only a find whose action is the chown stub below runs
    assert re.match(r'find ("\$UCM_CONFIG/"|\$UCM_CONFIG/|/etc/ucm) ', line), line
    config = tmp_path / 'etc-ucm'
    (config / 'dns-hooks').mkdir(parents=True)
    (config / 'dns-hooks' / 'hook.sh').write_text('#!/bin/sh\n')
    (config / 'ucm.env').write_text('X=1\n')
    (config / 'sub').mkdir()
    (config / 'sub' / 'dns-hooks').write_text('not the hook directory\n')
    stub = tmp_path / 'bin'
    stub.mkdir()
    trace = tmp_path / 'trace'
    (stub / 'chown').write_text(f'#!/bin/sh\nshift; shift\nfor p; do echo "$p" >> {trace}; done\n')
    (stub / 'chown').chmod(0o755)
    line = line.replace('/etc/ucm', str(config))
    env = {'PATH': f'{stub}:{os.environ["PATH"]}', 'UCM_CONFIG': str(config),
           'UCM_USER': 'svc', 'UCM_GROUP': 'svc'}
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
