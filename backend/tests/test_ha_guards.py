"""Host-local operations answer 409 ha_mode when the node runs with UCM_HA=1."""
import pytest
from flask import Flask

from config.settings import Config
from utils.ha import reject_in_ha

ROUTES = [
    '/api/v2/database/switch',
    '/api/v2/database/migrate',
    '/api/v2/system/security/enable-encryption',
    '/api/v2/system/security/disable-encryption',
    '/api/v2/system/security/encrypt-all-keys',
    '/api/v2/system/security/rotate-secrets',
    '/api/v2/system/updates/install',
    '/api/v2/system/restore',
    '/api/v2/system/backup/restore',
    '/api/v2/settings/backup/restore',
]
RESTORE_ROUTES = [r for r in ROUTES if 'restore' in r]


@pytest.mark.parametrize('path', ROUTES)
def test_route_refused_in_ha(auth_client, monkeypatch, path):
    monkeypatch.setattr(Config, 'HA_MODE', True)
    r = auth_client.post(path, json={})
    assert r.status_code == 409, r.data
    body = r.get_json()
    assert body['code'] == 'ha_mode'
    assert body['status'] == 409


@pytest.mark.parametrize('path', RESTORE_ROUTES)
def test_restore_route_keeps_its_usual_answer_without_ha(auth_client, monkeypatch, path):
    monkeypatch.setattr(Config, 'HA_MODE', False)
    r = auth_client.post(path, data={})
    assert r.status_code == 400, r.data


def test_decorator_passes_through_without_ha(monkeypatch):
    app = Flask(__name__)

    @app.route('/x')
    @reject_in_ha()
    def x():
        return 'ok'

    c = app.test_client()
    monkeypatch.setattr(Config, 'HA_MODE', False)
    assert c.get('/x').data == b'ok'
    monkeypatch.setattr(Config, 'HA_MODE', True)
    assert c.get('/x').status_code == 409


def test_scheduled_auto_update_skipped_in_ha(monkeypatch):
    import services.updates as updates
    monkeypatch.setattr(Config, 'HA_MODE', True)
    monkeypatch.delenv('UCM_DOCKER', raising=False)

    def boom(*a, **k):
        raise AssertionError('auto-update must not proceed in HA mode')
    monkeypatch.setattr(updates, '_cfg_get', boom)
    monkeypatch.setattr(updates, 'install_update', boom)
    updates._auto_install({'latest_version': '99.0', 'download_url': 'http://x/p.deb'})
