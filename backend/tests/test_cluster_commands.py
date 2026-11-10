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
    snap = RateLimitConfig.snapshot()
    try:
        r = auth_client.put('/api/v2/system/security/rate-limit', json={'enabled': snap['enabled']})
        assert r.status_code == 200, r.data
    finally:
        RateLimitConfig.apply_snapshot(snap)
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


def _ask_restart(monkeypatch):
    asked = []
    monkeypatch.setattr(cc, 'request_restart', lambda: asked.append(1) or (True, 'rolling'))
    monkeypatch.setattr(Config, 'HA_MODE', True)
    monkeypatch.setattr('config.settings.is_docker', lambda: True)
    return asked


def test_wstep_toggle_in_a_ha_container_asks_the_rolling_restart(app, auth_client, monkeypatch):
    from models import SystemConfig, db
    asked = _ask_restart(monkeypatch)
    with app.app_context():
        before = SystemConfig.query.filter_by(key='wstep_enabled').first()
        old = before.value if before else 'false'
    try:
        flipped = old != 'true'
        r = auth_client.patch('/api/v2/wstep/config', json={'enabled': flipped})
        assert r.status_code == 200, r.data
        assert asked == [1] and 'requires_container_restart' not in (r.get_json().get('data') or {})
    finally:
        with app.app_context():
            row = SystemConfig.query.filter_by(key='wstep_enabled').first()
            if row is not None:
                row.value = old
                db.session.commit()


def test_mtls_change_in_a_ha_container_asks_the_rolling_restart(app, auth_client, monkeypatch):
    asked = _ask_restart(monkeypatch)
    monkeypatch.setattr('api.v2.mtls.is_docker', lambda: True)
    r = auth_client.get('/api/v2/mtls/settings')
    current = (r.get_json() or {}).get('data', {}).get('required', False)
    r = auth_client.put('/api/v2/mtls/settings', json={'required': current})  # same value: nothing changes
    assert r.status_code == 200, r.data
    assert asked == [1]
