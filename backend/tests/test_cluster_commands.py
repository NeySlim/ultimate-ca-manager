"""HA cluster commands outside PostgreSQL: nothing runs or is written without UCM_HA,
and the rolling-restart turn only waits for live nodes still on their old process."""
import threading
from datetime import timedelta

import pytest

from config.settings import Config
from services import cluster_commands as cc
from utils.datetime_utils import utc_now


def _rows(app):
    from models import ClusterCommand, db
    with app.app_context():
        db.session.expire_all()
        return ClusterCommand.query.count()


def test_without_ha_no_thread_and_no_row(app, auth_client, monkeypatch):
    monkeypatch.setattr(Config, 'HA_MODE', False)
    assert cc.start_applier(app) is None
    assert not any(t.name == 'ClusterCommandApplier' for t in threading.enumerate())
    with app.app_context():
        assert cc.emit(cc.RELOAD_SYSLOG) is None
    before = _rows(app)
    from security.rate_limiter import RateLimitConfig
    r = auth_client.put('/api/v2/system/security/rate-limit', json={'enabled': RateLimitConfig.is_enabled()})
    assert r.status_code == 200, r.data
    r = auth_client.put('/api/v2/system/audit/syslog', json={'enabled': False, 'host': '', 'port': 514})
    assert r.status_code == 200, r.data
    assert _rows(app) == before == 0


def test_unknown_kind_is_refused(app):
    with app.app_context(), pytest.raises(ValueError):
        cc.emit('reload_everything')


NOW = utc_now()
ISSUED = NOW - timedelta(seconds=10)
OLD = NOW - timedelta(minutes=5)


@pytest.mark.parametrize('nodes, expected', [
    ([('a', OLD, NOW), ('b', OLD, NOW), ('c', OLD, NOW)], ['a', 'b']),
    ([('a', NOW, NOW), ('b', OLD, NOW)], ['b']),                     # a is back
    ([('a', OLD, NOW - timedelta(seconds=200)), ('b', OLD, NOW)], ['b']),  # a went stale
    ([('d', OLD, NOW)], []),                                         # after c: not ahead
    ([], []),                                                        # single node
])
def test_only_live_nodes_ahead_on_their_old_process_are_waited_for(nodes, expected):
    assert cc.pending_predecessors('c', nodes, ISSUED, NOW, stale_seconds=180) == expected


@pytest.fixture
def ha_commands(app, monkeypatch):
    """HA on this backend; yields the kinds of the commands the test emitted, removed afterwards."""
    from models import ClusterCommand, db
    monkeypatch.setattr(Config, 'HA_MODE', True)
    monkeypatch.setattr('config.settings.is_docker', lambda: True)
    with app.app_context():
        floor = db.session.query(db.func.max(ClusterCommand.id)).scalar() or 0

    def kinds():
        with app.app_context():
            db.session.expire_all()
            return [c.kind for c in ClusterCommand.query.filter(ClusterCommand.id > floor)
                    .order_by(ClusterCommand.id)]
    yield kinds
    with app.app_context():
        ClusterCommand.query.filter(ClusterCommand.id > floor).delete()
        db.session.commit()


def _config(app, key):
    from models import SystemConfig, db
    with app.app_context():
        db.session.expire_all()
        row = SystemConfig.query.filter_by(key=key).first()
        return row.value if row else None


def _put_config(app, key, value):
    from models import SystemConfig, db
    with app.app_context():
        row = SystemConfig.query.filter_by(key=key).first()
        if row is None and value is not None:
            db.session.add(SystemConfig(key=key, value=value))
        elif row is not None and value is None:
            db.session.delete(row)
        elif row is not None:
            row.value = value
        db.session.commit()


def test_wstep_toggle_in_a_ha_container_queues_the_restart_with_the_setting(app, auth_client, ha_commands):
    old = _config(app, 'wstep_enabled')
    try:
        r = auth_client.patch('/api/v2/wstep/config', json={'enabled': old != 'true'})
        assert r.status_code == 200, r.data
        assert ha_commands() == [cc.RESTART]
        assert 'requires_container_restart' not in (r.get_json().get('data') or {})
    finally:
        _put_config(app, 'wstep_enabled', old)


def test_mtls_change_in_a_ha_container_queues_the_restart_with_the_setting(app, auth_client, ha_commands,
                                                                          monkeypatch):
    monkeypatch.setattr('api.v2.mtls.is_docker', lambda: True)
    r = auth_client.get('/api/v2/mtls/settings')
    current = (r.get_json() or {}).get('data', {}).get('required', False)
    r = auth_client.put('/api/v2/mtls/settings', json={'required': current})  # same value: nothing changes
    assert r.status_code == 200, r.data
    assert ha_commands() == [cc.RESTART]


@pytest.fixture
def broken_emit(app, ha_commands, monkeypatch):
    """Every command the routes emit is invalid (NOT NULL kind): their commit fails."""
    from models import ClusterCommand, db

    def emit(kind, payload=None, target=None):
        command = ClusterCommand(kind=None, created_at=utc_now())
        db.session.add(command)
        return command
    monkeypatch.setattr(cc, 'emit', emit)
    return ha_commands


def test_rate_limits_not_saved_when_the_command_is_not(app, auth_client, broken_emit):
    from security.rate_limiter import STORED_KEY, RateLimitConfig
    r = auth_client.put('/api/v2/system/security/rate-limit',
                        json={'custom_limits': {'/api/v2/cc-broken': {'rpm': 9, 'burst': 3}}})
    assert r.status_code != 200
    assert '/api/v2/cc-broken' not in RateLimitConfig.get_config()['custom_limits']
    assert _config(app, STORED_KEY) is None and broken_emit() == []


def test_syslog_not_saved_when_the_command_is_not(app, auth_client, broken_emit):
    old = _config(app, 'syslog_port')
    r = auth_client.put('/api/v2/system/audit/syslog', json={'enabled': False, 'host': '', 'port': 5599})
    assert r.status_code != 200
    assert _config(app, 'syslog_port') == old and broken_emit() == []


def test_admin_allowlist_not_saved_when_the_command_is_not(app, auth_client, broken_emit):
    old = _config(app, 'admin_allowed_networks')
    r = auth_client.patch('/api/v2/settings/general', json={'admin_allowed_networks': '127.0.0.0/8'})
    assert r.status_code != 200
    assert _config(app, 'admin_allowed_networks') == old and broken_emit() == []


def test_wstep_toggle_not_saved_when_its_restart_is_not(app, auth_client, broken_emit):
    old = _config(app, 'wstep_enabled')
    try:
        r = auth_client.patch('/api/v2/wstep/config', json={'enabled': old != 'true'})
        assert r.status_code != 200, r.data
        assert _config(app, 'wstep_enabled') == old and broken_emit() == []
    finally:
        _put_config(app, 'wstep_enabled', old)


def test_mtls_change_not_saved_when_its_restart_is_not(app, auth_client, broken_emit):
    r = auth_client.get('/api/v2/mtls/settings')
    current = (r.get_json() or {}).get('data', {}).get('required', False)
    r = auth_client.put('/api/v2/mtls/settings', json={'required': current})
    assert r.status_code != 200, r.data
    assert broken_emit() == []


def test_service_restart_route_fails_when_its_command_is_not_queued(auth_client, broken_emit):
    r = auth_client.post('/api/v2/system/service/restart', json={})
    assert r.status_code == 500 and broken_emit() == []
