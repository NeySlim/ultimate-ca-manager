"""The initial admin password through the image entrypoint and the Helm chart.

No default anywhere: unset, the application generates one into its data
directory. The chart generates its own into its Secret, kept across upgrades.
"""
import pathlib
import re
import shutil
import subprocess

import pytest
import yaml

ROOT = pathlib.Path(__file__).resolve().parents[2]
ENTRYPOINT = ROOT / 'docker' / 'entrypoint.sh'


def _admin_env_after_entrypoint(env):
    """Run the entrypoint's admin defaults and its export with ``env``."""
    body = ENTRYPOINT.read_text(encoding='utf-8')
    defaults = re.search(r'^# Initial Admin User.*?(?=^\s*$)', body, re.M | re.S).group(0)
    exports = '\n'.join(re.findall(r'^export INITIAL_ADMIN_\w+=.*$', body, re.M))
    script = 'UCM_FQDN=ucm.local\n' + defaults + '\n' + exports + '\n' \
        + 'printf "%s\\n%s\\n%s\\n%s\\n" "$INITIAL_ADMIN_USERNAME" "$INITIAL_ADMIN_EMAIL" ' \
        + '"$INITIAL_ADMIN_PASSWORD" "$INITIAL_ADMIN_PASSWORD_FILE"\n'
    out = subprocess.run(['bash', '-c', script], env={'PATH': '/usr/bin:/bin', **env},
                         capture_output=True, text=True, check=True).stdout.split('\n')
    return dict(zip(('username', 'email', 'password', 'password_file'), out))


def test_entrypoint_has_no_default_password():
    got = _admin_env_after_entrypoint({})
    assert got['password'] == '' and got['password_file'] == ''


@pytest.mark.parametrize('name', ['INITIAL_ADMIN_PASSWORD_FILE', 'UCM_INITIAL_ADMIN_PASSWORD_FILE'])
def test_entrypoint_passes_a_password_file_on(name):
    got = _admin_env_after_entrypoint({name: '/run/secrets/ucm_admin_password'})
    assert got['password_file'] == '/run/secrets/ucm_admin_password' and got['password'] == ''


def test_entrypoint_writes_no_password_into_its_env_file():
    """The .env it writes outlives the first start; the value stays in the operator's hands."""
    body = ENTRYPOINT.read_text(encoding='utf-8')
    heredoc = re.search(r"cat > /opt/ucm/\.env; \} 2>/dev/null <<EOF\n(.*?)\nEOF", body, re.S).group(1)
    assert 'INITIAL_ADMIN_USERNAME=' in heredoc
    assert 'INITIAL_ADMIN_PASSWORD' not in heredoc


def test_entrypoint_keeps_an_unprefixed_password():
    got = _admin_env_after_entrypoint({'INITIAL_ADMIN_PASSWORD': 'S3cret-from-helm'})
    assert got['password'] == 'S3cret-from-helm'


def test_entrypoint_prefixed_value_wins():
    got = _admin_env_after_entrypoint({'INITIAL_ADMIN_PASSWORD': 'old', 'UCM_INITIAL_ADMIN_PASSWORD': 'new'})
    assert got['password'] == 'new'


def _render(*args):
    rendered = subprocess.run(['helm', 'template', 't', str(ROOT / 'charts' / 'ucm'), *args],
                              capture_output=True, text=True, check=True).stdout
    return [d for d in yaml.safe_load_all(rendered) if d]


@pytest.mark.skipif(shutil.which('helm') is None, reason='helm not installed')
def test_helm_generates_a_password_into_its_secret():
    docs = _render()
    secret = next(d for d in docs if d['kind'] == 'Secret')
    value = secret['stringData']['UCM_INITIAL_ADMIN_PASSWORD']
    assert len(value) >= 20 and value != 'changeme123'
    assert value != _render()[[d['kind'] for d in docs].index('Secret')]['stringData'][
        'UCM_INITIAL_ADMIN_PASSWORD'], 'random per render without a cluster to look up'
    notes = (ROOT / 'charts' / 'ucm' / 'templates' / 'NOTES.txt').read_text()
    assert 'changeme123' not in notes and 'UCM_INITIAL_ADMIN_PASSWORD' in notes


@pytest.mark.skipif(shutil.which('helm') is None, reason='helm not installed')
def test_helm_value_reaches_the_application():
    docs = _render('--set', 'initialAdminPassword=S3cret-from-helm')
    secret = next(d for d in docs if d['kind'] == 'Secret')
    deploy = next(d for d in docs if d['kind'] == 'Deployment')
    env = {}
    for item in deploy['spec']['template']['spec']['containers'][0]['env']:
        ref = (item.get('valueFrom') or {}).get('secretKeyRef')
        if ref and ref['name'] == secret['metadata']['name']:
            env[item['name']] = secret['stringData'][ref['key']]
        elif 'value' in item:
            env[item['name']] = item['value']
    assert _admin_env_after_entrypoint(env)['password'] == 'S3cret-from-helm'


def _deploy_env(docs):
    deploy = next(d for d in docs if d['kind'] == 'Deployment')
    return deploy['spec']['template']['spec']['containers'][0]['env']


@pytest.mark.skipif(shutil.which('helm') is None, reason='helm not installed')
@pytest.mark.parametrize('name', ['INITIAL_ADMIN_PASSWORD_FILE', 'UCM_INITIAL_ADMIN_PASSWORD_FILE'])
def test_helm_a_password_file_in_extra_env_is_the_only_source(name):
    """Both sources set refuse the start: the chart's variable steps aside."""
    docs = _render('--set', f'extraEnv[0].name={name}',
                   '--set', 'extraEnv[0].value=/run/secrets/ucm_admin_password')
    names = [item['name'] for item in _deploy_env(docs)]
    assert 'UCM_INITIAL_ADMIN_PASSWORD' not in names and 'INITIAL_ADMIN_PASSWORD' not in names
    env = {i['name']: i['value'] for i in _deploy_env(docs) if 'value' in i}
    got = _admin_env_after_entrypoint(env)
    assert got['password'] == '' and got['password_file'] == '/run/secrets/ucm_admin_password'


@pytest.mark.skipif(shutil.which('helm') is None, reason='helm not installed')
def test_helm_other_extra_env_keeps_the_chart_password():
    docs = _render('--set', 'extraEnv[0].name=UCM_LOG_LEVEL', '--set', 'extraEnv[0].value=DEBUG')
    assert 'UCM_INITIAL_ADMIN_PASSWORD' in [item['name'] for item in _deploy_env(docs)]


def _notes(tmp_path, *args):
    """NOTES.txt as helm renders it, through a copy of the chart (helm template skips it)."""
    chart = tmp_path / 'chart'
    shutil.copytree(ROOT / 'charts' / 'ucm', chart)
    notes = (chart / 'templates' / 'NOTES.txt').read_text()
    (chart / 'templates' / '_notes_probe.tpl').write_text(
        '{{- define "notes.probe" -}}\n' + notes + '\n{{- end -}}\n')
    (chart / 'templates' / 'notes-probe.yaml').write_text(
        'apiVersion: v1\nkind: ConfigMap\nmetadata:\n  name: notes-probe\n'
        'data:\n  notes: {{ include "notes.probe" . | quote }}\n')
    out = subprocess.run(['helm', 'template', 't', str(chart), '--show-only',
                          'templates/notes-probe.yaml', *args],
                         capture_output=True, text=True, check=True).stdout
    return yaml.safe_load(out)['data']['notes']


@pytest.mark.skipif(shutil.which('helm') is None, reason='helm not installed')
def test_helm_notes_point_to_the_secret_on_install_only(tmp_path):
    installed = _notes(tmp_path / 'i')
    assert 'kubectl' in installed and 'UCM_INITIAL_ADMIN_PASSWORD' in installed
    upgraded = _notes(tmp_path / 'u', '--is-upgrade')
    assert 'UCM_INITIAL_ADMIN_PASSWORD' not in upgraded
    assert 'keeps its password' in upgraded


@pytest.mark.skipif(shutil.which('helm') is None, reason='helm not installed')
@pytest.mark.parametrize('args, forced', [
    ((), True),
    (('--set', 'initialAdminPassword=Operator-Chosen-1!'), False),
    (('--set', 'extraEnv[0].name=INITIAL_ADMIN_PASSWORD_FILE', '--set', 'extraEnv[0].value=/s'), False),
], ids=['generated', 'provided', 'file'])
def test_helm_a_password_it_generated_is_changed_at_first_login(args, forced):
    env = {i['name']: i.get('value') for i in _deploy_env(_render(*args))}
    assert (env.get('INITIAL_ADMIN_PASSWORD_FORCE_CHANGE') == '1') is forced


@pytest.mark.skipif(shutil.which('helm') is None, reason='helm not installed')
def test_helm_generated_password_has_no_character_to_misread():
    for _ in range(5):
        secret = next(d for d in _render() if d['kind'] == 'Secret')
        value = secret['stringData']['UCM_INITIAL_ADMIN_PASSWORD']
        assert len(value) == 24 and value.isalnum() and not set(value) & set('0Oo1lI')
