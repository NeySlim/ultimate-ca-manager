"""The HTTP protocol port is bound when a worker starts: saving a new one asks for the restart
(a rolling one in HA, queued with the setting), and saving the same one asks for nothing."""
import json

import pytest

from models import ClusterCommand, SystemConfig, db


@pytest.fixture
def stored_port(app, monkeypatch):
    monkeypatch.delenv('HTTP_PROTOCOL_PORT', raising=False)
    with app.app_context():
        row = SystemConfig.query.filter_by(key='http_protocol_port').first()
        previous = row.value if row else None
        if row is None:
            db.session.add(SystemConfig(key='http_protocol_port', value='8080'))
        else:
            row.value = '8080'
        db.session.commit()
    yield
    with app.app_context():
        row = SystemConfig.query.filter_by(key='http_protocol_port').first()
        if previous is None:
            db.session.delete(row)
        else:
            row.value = previous
        db.session.commit()


@pytest.fixture
def restarts(monkeypatch):
    asked = []
    monkeypatch.setattr('config.settings.restart_ucm_service',
                        lambda: asked.append(1) or (True, 'Service restart initiated'))
    monkeypatch.setattr('config.settings.is_docker', lambda: False)
    return asked


def _save(auth_client, port):
    return auth_client.patch('/api/v2/settings/general', content_type='application/json',
                             data=json.dumps({'http_protocol_port': port}))


def test_a_new_port_asks_for_the_restart(app, auth_client, stored_port, restarts):
    r = _save(auth_client, 8081)
    assert r.status_code == 200, r.get_json()
    body = r.get_json()
    assert restarts == [1]
    assert body['data']['needs_restart'] is True
    assert body['data']['restart_message']


def test_the_same_port_asks_for_nothing(app, auth_client, stored_port, restarts):
    r = _save(auth_client, 8080)
    assert r.status_code == 200, r.get_json()
    assert restarts == []
    assert not r.get_json()['data']['needs_restart']


def test_a_port_set_by_the_environment_is_not_restarted_for(app, auth_client, stored_port,
                                                            restarts, monkeypatch):
    monkeypatch.setenv('HTTP_PROTOCOL_PORT', '8080')
    r = _save(auth_client, 8082)
    assert r.status_code == 200, r.get_json()
    assert restarts == []


def test_in_ha_the_rolling_restart_is_committed_with_the_port(app, auth_client, stored_port,
                                                               restarts, monkeypatch):
    monkeypatch.setattr('utils.ha.ha_enabled', lambda: True)
    with app.app_context():
        last = db.session.query(db.func.max(ClusterCommand.id)).scalar() or 0
    try:
        r = _save(auth_client, 8083)
        assert r.status_code == 200, r.get_json()
        assert restarts == []  # no second, local restart
        from services.cluster_commands import ROLLING_RESTART_MESSAGE
        assert r.get_json()['data']['restart_message'] == ROLLING_RESTART_MESSAGE
        with app.app_context():
            kinds = [c.kind for c in ClusterCommand.query.filter(ClusterCommand.id > last)]
            assert kinds == ['restart']
    finally:
        with app.app_context():
            ClusterCommand.query.filter(ClusterCommand.id > last).delete()
            db.session.commit()

