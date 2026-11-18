"""A `helm upgrade` to the chart of a new major is the operator's explicit action: the chart sets
UCM_ACCEPT_MAJOR_UPGRADE to the major of its appVersion, unless majorUpgrade.accept is false."""
import pathlib
import shutil
import subprocess

import pytest
import yaml

ROOT = pathlib.Path(__file__).resolve().parents[2]
CHART = ROOT / 'charts' / 'ucm'

pytestmark = pytest.mark.skipif(shutil.which('helm') is None, reason='helm not installed')


def _env(*args):
    out = subprocess.run(['helm', 'template', 't', str(CHART), '--set', 'secrets.secretKey=k', *args],
                         capture_output=True, text=True, check=True).stdout
    dep = next(d for d in yaml.safe_load_all(out) if d and d['kind'] == 'Deployment')
    return dep['spec']['template']['spec']['containers'][0]['env']


def _values(env, name):
    return [e.get('value') for e in env if e['name'] == name]


def test_the_chart_accepts_the_major_of_its_app_version():
    major = str(yaml.safe_load((CHART / 'Chart.yaml').read_text())['appVersion']).split('.')[0]
    assert major == '3'
    assert _values(_env(), 'UCM_ACCEPT_MAJOR_UPGRADE') == [major]


def test_the_value_is_a_string_for_kubernetes():
    """An env value must be a string: a bare 3 would fail the apply."""
    env = _env()
    assert all(isinstance(e['value'], str) for e in env if 'value' in e)


def test_the_operator_can_keep_the_image_gate():
    assert _values(_env('--set', 'majorUpgrade.accept=false'), 'UCM_ACCEPT_MAJOR_UPGRADE') == []


def test_extra_env_still_comes_last():
    """extraEnv follows the chart's entry: Kubernetes keeps the last of two same-named variables."""
    env = _env('--set', 'extraEnv[0].name=UCM_ACCEPT_MAJOR_UPGRADE', '--set-string', 'extraEnv[0].value=no')
    assert _values(env, 'UCM_ACCEPT_MAJOR_UPGRADE') == ['3', 'no']


@pytest.mark.parametrize('flags', [[], ['--set', 'ha.enabled=true', '--set', 'replicaCount=2',
                                        '--set', 'secrets.keyEncryptionKey=K', '--set', 'secrets.dbEncryptionKey=D',
                                        '--set', 'database.type=postgresql',
                                        '--set', 'database.databaseUrl=postgresql://u:p@db/ucm']],
                         ids=['sqlite', 'ha'])
def test_every_node_gets_it(flags):
    assert _values(_env(*flags), 'UCM_ACCEPT_MAJOR_UPGRADE') == ['3']
