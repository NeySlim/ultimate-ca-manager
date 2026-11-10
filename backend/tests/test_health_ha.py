"""Health probes identify the node and report HA state; readiness fails in safe mode."""
import pathlib
import shutil
import subprocess

import pytest
import yaml

from config.settings import Config

CHART = pathlib.Path(__file__).resolve().parents[2] / 'charts' / 'ucm'
LEGACY_HEALTH = {'status', 'service', 'version', 'started_at', 'websocket', 'fips_active'}


@pytest.mark.parametrize('path', ['/health', '/api/v2/health', '/health/ready'])
def test_probe_carries_ha_fields(client, monkeypatch, path):
    monkeypatch.setattr(Config, 'HA_MODE', True)
    monkeypatch.setattr(Config, 'NODE_ID', 'node-a')
    body = client.get(path).get_json()
    assert body['ha'] is True
    assert body['node_id'] == 'node-a'
    assert 'leader' in body and body['leader'] in (True, False, None)


def test_without_ha_flag_is_false_and_legacy_keys_kept(client, monkeypatch):
    monkeypatch.setattr(Config, 'HA_MODE', False)
    body = client.get('/health').get_json()
    assert body['ha'] is False
    assert LEGACY_HEALTH <= set(body)
    ready = client.get('/health/ready').get_json()
    assert {'status', 'checks'} <= set(ready) and ready['ha'] is False


def _ready_in_safe_mode(app, client):
    app.config['SAFE_MODE'] = True
    app.config['SAFE_MODE_REASON'] = 'encryption_key_missing'
    try:
        return client.get('/health/ready')
    finally:
        app.config['SAFE_MODE'] = False


def test_ready_is_503_in_safe_mode_when_ha(app, client, monkeypatch):
    monkeypatch.setattr(Config, 'HA_MODE', True)
    r = _ready_in_safe_mode(app, client)
    assert r.status_code == 503
    assert r.get_json()['status'] == 'safe_mode'
    assert r.get_json()['reason'] == 'encryption_key_missing'


def test_ready_stays_200_in_safe_mode_single_node(app, client, monkeypatch):
    monkeypatch.setattr(Config, 'HA_MODE', False)
    r = _ready_in_safe_mode(app, client)
    assert r.status_code == 200
    assert r.get_json()['status'] == 'safe_mode'
    assert r.get_json()['checks']['database']['status'] == 'ok'


@pytest.mark.parametrize('ha', [False, True])
def test_ready_is_503_in_safe_mode_when_a_check_fails(app, client, monkeypatch, ha):
    import api.health_routes as hr
    monkeypatch.setattr(Config, 'HA_MODE', ha)
    monkeypatch.setattr(hr, '_check_database', lambda: {'status': 'error', 'message': 'down'})
    r = _ready_in_safe_mode(app, client)
    assert r.status_code == 503
    body = r.get_json()
    assert body['status'] == 'safe_mode'
    assert body['checks']['database']['status'] == 'error'


def test_leader_follows_the_scheduler_state(monkeypatch):
    import services.scheduler_service as ss

    class Fake:
        def __init__(self, delegated, stale=False, owns=False):
            self._d, self._s, self._owns_lock = delegated, stale, owns
        def _delegated(self): return self._d
        def state_is_stale(self): return self._s

    monkeypatch.setattr(ss, '_scheduler', None)
    assert ss.is_leader() is None
    monkeypatch.setattr(ss, '_scheduler', Fake(True, stale=False))
    assert ss.is_leader() is True
    monkeypatch.setattr(ss, '_scheduler', Fake(True, stale=True))
    assert ss.is_leader() is False
    monkeypatch.setattr(ss, '_scheduler', Fake(False, owns=True))
    assert ss.is_leader() is True


@pytest.mark.skipif(shutil.which('helm') is None, reason='helm not installed')
def test_chart_probes_use_live_and_ready():
    rendered = subprocess.run(['helm', 'template', 't', str(CHART)],
                              capture_output=True, text=True, check=True).stdout
    deploy = next(d for d in yaml.safe_load_all(rendered) if d and d['kind'] == 'Deployment')
    c = deploy['spec']['template']['spec']['containers'][0]
    assert c['livenessProbe']['httpGet']['path'] == '/health/live'
    assert c['readinessProbe']['httpGet']['path'] == '/health/ready'
