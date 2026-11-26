"""The custom_command DNS provider runs only hooks of the host's root-owned hook directory."""
import os
import sys

import pytest

from services.acme.dns_providers import create_provider
from services.acme.dns_providers import custom_command as cc
from services.acme.dns_providers.custom_command import CustomCommandDnsProvider


@pytest.fixture
def hooks(tmp_path, monkeypatch):
    """A hook directory owned by the test account, trusted in place of root."""
    d = tmp_path / 'dns-hooks'
    d.mkdir()
    d.chmod(0o755)
    monkeypatch.setattr(cc, 'HOOKS_DIR', str(d))
    monkeypatch.setattr(cc, '_HOOK_OWNER_UID', os.getuid())
    return d


def _hook(directory, name, body='print("ok")', mode=0o755):
    path = directory / name
    path.write_text(f'#!{sys.executable}\n{body}\n')
    path.chmod(mode)
    return path


def _create(cmd):
    p = create_provider('custom_command', {'create_command': cmd, 'timeout_seconds': '10'})
    return p.create_txt_record('example.com', '_acme-challenge.example.com', 'v')


def test_a_hook_named_in_the_directory_runs_with_its_arguments(hooks, tmp_path):
    out = tmp_path / 'out'
    _hook(hooks, 'record.py', "import os, sys\n"
          "open(sys.argv[1], 'w').write(os.environ['ACTION'] + '|' + sys.argv[2])")
    ok, msg = _create(f"record.py {out} 'two words'")
    assert ok, msg
    assert out.read_text() == 'create|two words'


@pytest.mark.parametrize('cmd', ['/bin/sh -c id', f'{sys.executable} -c 1', '/usr/bin/env true'])
def test_an_absolute_program_is_refused_at_run_time(hooks, cmd):
    ok, msg = _create(cmd)
    assert not ok
    assert str(hooks) in msg and 'hook' in msg


@pytest.mark.parametrize('name', ['../x', 'sub/x', '.hidden', ''])
def test_a_name_that_leaves_the_directory_is_refused(hooks, tmp_path, name):
    _hook(tmp_path, 'x')
    ok, _msg = _create(f"'{name}'")
    assert not ok


def test_a_symlink_out_of_the_directory_is_refused(hooks, tmp_path):
    target = _hook(tmp_path, 'outside')
    (hooks / 'link').symlink_to(target)
    ok, msg = _create('link')
    assert not ok and 'outside' in msg.lower()


def test_a_symlink_inside_the_directory_is_followed(hooks, tmp_path):
    out = tmp_path / 'out'
    _hook(hooks, 'real', f"open({str(out)!r}, 'w').write('ran')")
    (hooks / 'alias').symlink_to(hooks / 'real')
    ok, msg = _create('alias')
    assert ok, msg
    assert out.read_text() == 'ran'


def test_a_directory_writable_by_others_is_refused(hooks):
    _hook(hooks, 'h')
    hooks.chmod(0o777)
    ok, msg = _create('h')
    assert not ok and 'writable' in msg


def test_a_hook_writable_by_its_group_is_refused(hooks):
    _hook(hooks, 'h', mode=0o775)
    ok, msg = _create('h')
    assert not ok and 'writable' in msg


def test_a_directory_not_owned_by_root_is_refused(hooks, monkeypatch):
    _hook(hooks, 'h')
    monkeypatch.setattr(cc, '_HOOK_OWNER_UID', os.getuid() + 1)
    ok, msg = _create('h')
    assert not ok and 'owned' in msg


def test_a_linked_hook_directory_is_refused(tmp_path, monkeypatch):
    real = tmp_path / 'real'
    real.mkdir()
    _hook(real, 'h')
    (tmp_path / 'link').symlink_to(real)
    monkeypatch.setattr(cc, 'HOOKS_DIR', str(tmp_path / 'link'))
    monkeypatch.setattr(cc, '_HOOK_OWNER_UID', os.getuid())
    ok, _msg = _create('h')
    assert not ok


def test_a_missing_hook_is_refused(hooks):
    ok, msg = _create('absent')
    assert not ok and 'absent' in msg


def test_test_connection_checks_the_hooks(hooks):
    _hook(hooks, 'h')
    good = create_provider('custom_command', {'create_command': 'h', 'delete_command': 'h x'})
    assert good.test_connection()[0]
    bad = create_provider('custom_command', {'create_command': 'h', 'delete_command': '/bin/true'})
    assert not bad.test_connection()[0]


@pytest.mark.parametrize('creds', [
    {'create_command': '/bin/sh -c id'},
    {'create_command': 'h', 'delete_command': '/usr/bin/true'},
    {'create_command': '../h'},
])
def test_saving_a_command_that_is_not_a_hook_name_is_refused(creds):
    with pytest.raises(ValueError) as exc:
        CustomCommandDnsProvider.validate_credentials(creds)
    assert 'dns-hooks' in str(exc.value)


def test_saving_a_hook_name_is_accepted():
    CustomCommandDnsProvider.validate_credentials({'create_command': 'cf-dns.sh --zone x', 'delete_command': ''})


def test_the_api_refuses_an_absolute_command(auth_client):
    r = auth_client.post('/api/v2/dns-providers', json={
        'name': 'r31a-cmd', 'provider_type': 'custom_command',
        'credentials': {'create_command': "/bin/sh -c 'id > /tmp/x'"}})
    assert r.status_code == 400, r.get_json()
    assert 'dns-hooks' in r.get_json()['message']


def test_the_api_saves_a_hook_name_and_refuses_an_absolute_one_on_edit(auth_client):
    r = auth_client.post('/api/v2/dns-providers', json={
        'name': 'r31a-hook', 'provider_type': 'custom_command',
        'credentials': {'create_command': 'cf-dns.sh'}})
    assert r.status_code == 201, r.get_json()
    pid = r.get_json()['data']['id']
    try:
        r = auth_client.patch(f'/api/v2/dns-providers/{pid}',
                              json={'credentials': {'create_command': '/bin/sh -c id'}})
        assert r.status_code == 400
        assert 'dns-hooks' in r.get_json()['message']
    finally:
        auth_client.delete(f'/api/v2/dns-providers/{pid}')


def test_default_directory_is_the_documented_one():
    assert cc.HOOKS_DIR == '/etc/ucm/dns-hooks'
    assert cc._HOOK_OWNER_UID == 0

