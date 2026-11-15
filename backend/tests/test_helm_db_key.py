"""Helm chart: the shared database key of HA, the replica guard, the move to HA, a stable checksum."""
import base64
import pathlib
import shutil
import subprocess

import pytest
import yaml

ROOT = pathlib.Path(__file__).resolve().parents[2]
CHART = ROOT / 'charts' / 'ucm'
PG = ['--set', 'database.type=postgresql', '--set', 'database.databaseUrl=postgresql://u:p@db/ucm']
HA = ['--set', 'ha.enabled=true', '--set', 'replicaCount=2'] + PG
SECRET_LOOKUP = 'lookup "v1" "Secret" .Release.Namespace'

pytestmark = pytest.mark.skipif(shutil.which('helm') is None, reason='helm not installed')


def _render(*args, chart=CHART, check=True):
    return subprocess.run(['helm', 'template', 't', str(chart), *args],
                          capture_output=True, text=True, check=check)


def _docs(*args, chart=CHART):
    return {d['kind']: d for d in yaml.safe_load_all(_render(*args, chart=chart).stdout) if d}


def _env(docs):
    return {e['name']: e for e in docs['Deployment']['spec']['template']['spec']['containers'][0]['env']}


def _checksum(docs):
    return docs['Deployment']['spec']['template']['metadata']['annotations']['checksum/secret']


def _chart_with_existing_secret(tmp_path, data):
    """A copy of the chart whose Secret lookups find `data`, as on a cluster after the
    first install (helm template has no cluster to look it up in)."""
    chart = tmp_path / 'ucm'
    shutil.copytree(CHART, chart)
    found = 0
    for path in (chart / 'templates').iterdir():
        src = path.read_text()
        if SECRET_LOOKUP in src:
            found += src.count(SECRET_LOOKUP)
            src = src.replace(f'({SECRET_LOOKUP} $secretName)', '.Values.testExistingSecret')
            src = src.replace(f'({SECRET_LOOKUP} (include "ucm.secretName" .))', '.Values.testExistingSecret')
            assert SECRET_LOOKUP not in src, path.name
            path.write_text(src)
    assert found >= 2
    existing = {'data': {k: base64.b64encode(v.encode()).decode() for k, v in data.items()}}
    values = tmp_path / 'existing.yaml'
    values.write_text(yaml.safe_dump({'testExistingSecret': existing}))
    return chart, ['-f', str(values)]


def test_ha_secret_carries_a_fernet_database_key_passed_to_every_pod():
    from cryptography.fernet import Fernet
    docs = _docs(*HA)
    key = docs['Secret']['stringData']['UCM_DB_ENCRYPTION_KEY']
    Fernet(key.encode())
    ref = _env(docs)['UCM_DB_ENCRYPTION_KEY']['valueFrom']['secretKeyRef']
    assert ref['key'] == 'UCM_DB_ENCRYPTION_KEY'


def test_ha_database_key_is_kept_from_the_existing_secret_on_upgrade(tmp_path):
    first = _docs(*HA)['Secret']['stringData']
    chart, values = _chart_with_existing_secret(tmp_path, first)
    again = _docs(*HA, *values, '--is-upgrade', chart=chart)['Secret']['stringData']
    assert again['UCM_DB_ENCRYPTION_KEY'] == first['UCM_DB_ENCRYPTION_KEY']
    assert again['KEY_ENCRYPTION_KEY'] == first['KEY_ENCRYPTION_KEY']


def test_single_instance_gets_no_database_key_unless_given():
    docs = _docs()
    assert 'UCM_DB_ENCRYPTION_KEY' not in docs['Secret']['stringData']
    assert 'UCM_DB_ENCRYPTION_KEY' not in _env(docs)
    given = _docs('--set', 'secrets.dbEncryptionKey=GIVEN')
    assert given['Secret']['stringData']['UCM_DB_ENCRYPTION_KEY'] == 'GIVEN'
    assert 'UCM_DB_ENCRYPTION_KEY' in _env(given)


def test_several_replicas_without_ha_are_refused():
    r = _render('--set', 'replicaCount=3', check=False)
    assert r.returncode != 0
    assert 'replicaCount > 1 requires ha.enabled=true' in r.stderr


def test_moving_an_instance_to_ha_without_its_master_key_is_refused(tmp_path):
    # The single instance's Secret: no KEY_ENCRYPTION_KEY, its key is /etc/ucm/master.key
    chart, values = _chart_with_existing_secret(tmp_path, {'UCM_SECRET_KEY': 's'})
    r = _render(*HA, *values, '--is-upgrade', '--set', 'secrets.dbEncryptionKey=D', chart=chart, check=False)
    assert r.returncode != 0 and 'secrets.keyEncryptionKey' in r.stderr and 'master.key' in r.stderr
    r = _render(*HA, *values, '--is-upgrade', '--set', 'secrets.keyEncryptionKey=K', chart=chart, check=False)
    assert r.returncode != 0 and 'secrets.dbEncryptionKey' in r.stderr
    ok = _docs(*HA, *values, '--is-upgrade', '--set', 'secrets.keyEncryptionKey=K',
               '--set', 'secrets.dbEncryptionKey=D', chart=chart)
    assert ok['Secret']['stringData']['KEY_ENCRYPTION_KEY'] == 'K'


def test_a_new_ha_release_still_generates_its_keys():
    stringdata = _docs(*HA)['Secret']['stringData']
    assert stringdata['KEY_ENCRYPTION_KEY'] and stringdata['UCM_DB_ENCRYPTION_KEY']


@pytest.mark.parametrize('extra', [[], HA])
def test_secret_checksum_does_not_change_from_install_to_first_upgrade(tmp_path, extra):
    installed = _docs(*extra)
    chart, values = _chart_with_existing_secret(tmp_path, installed['Secret']['stringData'])
    upgraded = _docs(*extra, *values, '--is-upgrade', chart=chart)
    assert _checksum(upgraded) == _checksum(installed)


def test_secret_checksum_follows_a_value_the_operator_sets():
    assert _checksum(_docs('--set', 'secrets.secretKey=a')) != _checksum(_docs('--set', 'secrets.secretKey=b'))
