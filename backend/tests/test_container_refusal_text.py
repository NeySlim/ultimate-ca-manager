"""Every container refusal says container (Docker, Kubernetes): the Helm chart runs the same image."""
import pytest

from config.settings import Config
import services.updates as updates

CONTAINER = 'container (Docker, Kubernetes)'


def test_the_install_refusal_names_both_runtimes(app, auth_client, monkeypatch):
    monkeypatch.setattr(updates, 'is_container_install', lambda: True)
    monkeypatch.setattr(Config, 'HA_MODE', False)
    message = auth_client.post('/api/v2/system/updates/install', json={}).get_json()['message']
    assert CONTAINER in message
    assert 'in Docker.' not in message


def test_the_auto_install_setting_refusal_names_both_runtimes(app, auth_client, monkeypatch):
    monkeypatch.setattr(updates, 'is_container_install', lambda: True)
    r = auth_client.patch('/api/v2/system/updates/settings', json={'auto_install': True})
    assert r.status_code == 400
    assert CONTAINER in r.get_json()['message']


def test_the_restart_route_refusal_names_both_runtimes(app, auth_client, monkeypatch):
    monkeypatch.setattr(Config, 'HA_MODE', False)
    monkeypatch.setattr('api.v2.system.service.is_docker', lambda: True)
    r = auth_client.post('/api/v2/system/service/restart', json={})
    assert r.status_code == 400
    assert CONTAINER in r.get_json()['message']


def test_the_restart_helpers_say_the_same_thing(app, monkeypatch):
    import config.settings as settings
    from services.jobs import restore
    monkeypatch.setattr(Config, 'HA_MODE', False)
    monkeypatch.setattr(settings, 'is_docker', lambda: True)
    monkeypatch.setattr('config.settings.is_docker', lambda: True)
    ok, from_settings = settings.restart_ucm_service()
    ok2, from_restore = restore.predicted_restart()
    assert not ok and not ok2
    assert CONTAINER in from_settings
    assert from_settings == from_restore
