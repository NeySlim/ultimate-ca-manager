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
    # Compared as documents: helm versions differ on blank lines between them.
    def load(text):
        text = re.sub(r'checksum/secret: .*', 'checksum/secret: SUM', text)
        # Random at each render without a cluster to look the Secret up
        text = re.sub(r'UCM_INITIAL_ADMIN_PASSWORD: "[A-Za-z0-9]{24}"', 'UCM_INITIAL_ADMIN_PASSWORD: "GENERATED"', text)
        return [d for d in yaml.safe_load_all(text) if d]
    golden = GOLDEN.read_text().replace('@CHART@', 'ucm-' + chart['version']).replace('@APP@', chart['appVersion'])
    assert load(_helm().stdout) == load(golden)


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
    assert env['HSM_AUTO_INIT']['value'] == 'false'
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


def test_ha_startup_probe_outlasts_the_node_identifier_wait_pos():
    """A container killed and restarted in its pod waits for its old heartbeat to expire:
    the liveness probe must not kill it meanwhile."""
    from services.scheduler_leader import CLAIM_POLL_SECONDS, STALE_PASSES
    from services.scheduler_service import WAKE_INTERVAL_SECONDS
    container = _docs(*HA)['Deployment']['spec']['template']['spec']['containers'][0]
    probe = container['startupProbe']
    assert probe['httpGet']['path'] == '/health/live'
    longest_wait = STALE_PASSES * WAKE_INTERVAL_SECONDS + 2 * CLAIM_POLL_SECONDS
    assert probe['periodSeconds'] * probe['failureThreshold'] >= longest_wait + 60
    assert 'startupProbe' not in _docs()['Deployment']['spec']['template']['spec']['containers'][0]


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


def test_leaving_ha_keeps_the_encryption_key_pos():
    docs = _docs('--set', 'secrets.keyEncryptionKey=KEEPME')
    assert docs['Secret']['stringData']['KEY_ENCRYPTION_KEY'] == 'KEEPME'
    env = {e['name'] for e in docs['Deployment']['spec']['template']['spec']['containers'][0]['env']}
    assert 'KEY_ENCRYPTION_KEY' in env


def test_secret_with_a_key_is_kept_on_uninstall_pos():
    for args in (HA, ['--set', 'secrets.keyEncryptionKey=K']):
        ann = _docs(*args)['Secret']['metadata'].get('annotations', {})
        assert ann.get('helm.sh/resource-policy') == 'keep'


def test_data_pvc_outside_ha_has_no_keep_annotation_neg():
    pvcs = [d for d in yaml.safe_load_all(_helm(*PG).stdout) if d and d['kind'] == 'PersistentVolumeClaim']
    pvc = next(d for d in pvcs if d['metadata']['name'] == 't-ucm-data')
    assert 'annotations' not in pvc['metadata']


def test_ha_without_an_existing_data_pvc_renders_none_neg():
    # helm template has no cluster: lookup finds nothing, so no claim is created in HA
    pvcs = [d for d in yaml.safe_load_all(_helm(*HA).stdout) if d and d['kind'] == 'PersistentVolumeClaim']
    assert pvcs == []


def test_ha_with_a_former_data_pvc_still_renders_it_kept_and_unmounted_pos(tmp_path):
    # helm template cannot reach a cluster: the lookup is stubbed as finding the claim
    chart = tmp_path / 'ucm'
    shutil.copytree(CHART, chart)
    pvc_file = chart / 'templates' / 'pvc.yaml'
    src = pvc_file.read_text()
    found = '(lookup "v1" "PersistentVolumeClaim" .Release.Namespace $dataPvc)'
    assert src.count(found) == 1
    pvc_file.write_text(src.replace(found, 'true'))
    out = subprocess.run(['helm', 'template', 't', str(chart), '--set', 'secrets.secretKey=k', *HA],
                         capture_output=True, text=True, check=True).stdout
    docs = [d for d in yaml.safe_load_all(out) if d]
    pvcs = [d for d in docs if d['kind'] == 'PersistentVolumeClaim']
    assert [p['metadata']['name'] for p in pvcs] == ['t-ucm-data']
    assert pvcs[0]['metadata']['annotations']['helm.sh/resource-policy'] == 'keep'
    pod = next(d for d in docs if d['kind'] == 'Deployment')['spec']['template']['spec']
    assert pod['volumes'] == [{'name': 'data', 'emptyDir': {}}]
