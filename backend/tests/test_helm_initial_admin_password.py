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
