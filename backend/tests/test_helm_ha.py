"""Helm chart HA packaging: HA render, refusal without PostgreSQL, default render unchanged."""
import pathlib
import re
import shutil
import subprocess

import pytest
import yaml

ROOT = pathlib.Path(__file__).resolve().parents[2]
CHART = ROOT / 'charts' / 'ucm'
GOLDEN = pathlib.Path(__file__).parent / 'fixtures' / 'helm_default_render.yaml'
PG = ['--set', 'database.type=postgresql', '--set', 'database.databaseUrl=postgresql://u:p@db/ucm']
HA = ['--set', 'ha.enabled=true', '--set', 'replicaCount=2'] + PG

pytestmark = pytest.mark.skipif(shutil.which('helm') is None, reason='helm not installed')


def _helm(*args, check=True):
    return subprocess.run(['helm', 'template', 't', str(CHART), '--set', 'secrets.secretKey=k', *args],
                          capture_output=True, text=True, check=check)


def _docs(*args):
    return {d['kind']: d for d in yaml.safe_load_all(_helm(*args).stdout) if d}


def test_default_render_matches_the_pre_ha_render():
    chart = yaml.safe_load((CHART / 'Chart.yaml').read_text())
    out = _helm().stdout
    out = re.sub(r'checksum/secret: .*', 'checksum/secret: @SUM@', out)
    out = out.replace('ucm-' + chart['version'], '@CHART@').replace(chart['appVersion'], '@APP@')
    assert out == GOLDEN.read_text()


def test_ha_render_pos():
    docs = _docs(*HA)
    dep = docs['Deployment']
    assert dep['spec']['strategy'] == {'type': 'RollingUpdate',
                                       'rollingUpdate': {'maxUnavailable': 0, 'maxSurge': 1}}
    assert dep['spec']['replicas'] == 2
    pod = dep['spec']['template']['spec']
    env = {e['name']: e for e in pod['containers'][0]['env']}
    assert env['UCM_HA']['value'] == '1'
    assert env['UCM_NODE_ID']['valueFrom']['fieldRef']['fieldPath'] == 'metadata.name'
    assert env['KEY_ENCRYPTION_KEY']['valueFrom']['secretKeyRef']['key'] == 'KEY_ENCRYPTION_KEY'
    assert 'REDIS_URL' not in env
    assert 'KEY_ENCRYPTION_KEY' in docs['Secret']['stringData']
    assert docs['PodDisruptionBudget']['spec']['minAvailable'] == 1
    anti = pod['affinity']['podAntiAffinity']['preferredDuringSchedulingIgnoredDuringExecution']
    assert anti[0]['podAffinityTerm']['topologyKey'] == 'kubernetes.io/hostname'


def test_ha_has_no_etc_volume_or_pvc_neg():
    docs = _docs(*HA)
    pod = docs['Deployment']['spec']['template']['spec']
    assert [v['name'] for v in pod['volumes']] == ['data']
    assert pod['volumes'][0] == {'name': 'data', 'emptyDir': {}}
    assert all(m['name'] != 'etc' for m in pod['containers'][0]['volumeMounts'])
    assert 'PersistentVolumeClaim' not in docs


def test_ha_kek_is_a_valid_fernet_key():
    from cryptography.fernet import Fernet
    key = _docs(*HA)['Secret']['stringData']['KEY_ENCRYPTION_KEY']
    Fernet(key.encode())


def test_ha_redis_url_reaches_the_pod_pos():
    dep = _docs(*HA, '--set', 'redis.url=redis://r:6379/0')['Deployment']
    env = {e['name']: e.get('value') for e in dep['spec']['template']['spec']['containers'][0]['env']}
    assert env['REDIS_URL'] == 'redis://r:6379/0'


def test_ha_existing_claim_keeps_the_data_pvc_pos():
    dep = _docs(*HA, '--set', 'persistence.data.existingClaim=shared')['Deployment']
    vol = dep['spec']['template']['spec']['volumes'][0]
    assert vol['persistentVolumeClaim']['claimName'] == 'shared'


@pytest.mark.parametrize('args,message', [
    (['--set', 'ha.enabled=true', '--set', 'replicaCount=2'], 'database.type=postgresql'),
    (['--set', 'ha.enabled=true'] + PG, 'replicaCount >= 2'),
    (['--set', 'ha.enabled=true', '--set', 'replicaCount=2', '--set', 'database.type=postgresql'],
     'databaseUrl'),
])
def test_ha_render_is_refused_neg(args, message):
    r = _helm(*args, check=False)
    assert r.returncode != 0 and message in r.stderr


def test_without_ha_nothing_ha_is_rendered_neg():
    docs = _docs()
    assert 'PodDisruptionBudget' not in docs
    assert docs['Deployment']['spec']['strategy'] == {'type': 'Recreate'}
    assert 'KEY_ENCRYPTION_KEY' not in docs['Secret']['stringData']
