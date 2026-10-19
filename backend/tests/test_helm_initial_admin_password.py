"""The Helm chart's initialAdminPassword reaches the application.

The chart rendered INITIAL_ADMIN_PASSWORD while the image entrypoint only read
UCM_INITIAL_ADMIN_PASSWORD, which defaulted to changeme123 and was exported
over it: every Helm install started with the default password.
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
        + 'printf "%s\\n%s\\n%s\\n" "$INITIAL_ADMIN_USERNAME" "$INITIAL_ADMIN_EMAIL" "$INITIAL_ADMIN_PASSWORD"\n'
    out = subprocess.run(['bash', '-c', script], env={'PATH': '/usr/bin:/bin', **env},
                         capture_output=True, text=True, check=True).stdout.splitlines()
    return dict(zip(('username', 'email', 'password'), out))


def test_entrypoint_default_password_without_any_value():
    assert _admin_env_after_entrypoint({})['password'] == 'changeme123'


def test_entrypoint_keeps_an_unprefixed_password():
    got = _admin_env_after_entrypoint({'INITIAL_ADMIN_PASSWORD': 'S3cret-from-helm'})
    assert got['password'] == 'S3cret-from-helm'


def test_entrypoint_prefixed_value_wins():
    got = _admin_env_after_entrypoint({'INITIAL_ADMIN_PASSWORD': 'old', 'UCM_INITIAL_ADMIN_PASSWORD': 'new'})
    assert got['password'] == 'new'


@pytest.mark.skipif(shutil.which('helm') is None, reason='helm not installed')
def test_helm_value_reaches_the_application():
    rendered = subprocess.run(
        ['helm', 'template', 't', str(ROOT / 'charts' / 'ucm'),
         '--set', 'initialAdminPassword=S3cret-from-helm'],
        capture_output=True, text=True, check=True).stdout
    docs = [d for d in yaml.safe_load_all(rendered) if d]
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
