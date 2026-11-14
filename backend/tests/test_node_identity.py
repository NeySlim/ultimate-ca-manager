"""Node identifier claims: none outside HA, and the conditional heartbeat runs on SQLite too."""
from datetime import timedelta

from config.settings import Config
from services import scheduler_leader
from services.scheduler_service import SchedulerService
from utils.datetime_utils import utc_now


def test_outside_ha_no_claim_and_no_heartbeat(monkeypatch):
    from tests.fresh_app import fresh_app
    monkeypatch.setattr(Config, 'HA_MODE', False)
    calls = []
    monkeypatch.setattr(scheduler_leader, 'claim_node_at_start', lambda *a, **k: calls.append(a))
    monkeypatch.setattr(scheduler_leader, 'write_heartbeat', lambda *a, **k: calls.append(a))
    with fresh_app():
        pass
    SchedulerService(node_id='single')._heartbeat(force=True)
    assert calls == []


def test_the_conditional_heartbeat_on_sqlite(app, monkeypatch):
    from models import ClusterNode, db
    monkeypatch.setattr(Config, 'HA_MODE', True)
    node = 'sqlite-nid'
    with app.app_context():
        try:
            assert scheduler_leader.write_heartbeat(node, False, utc_now(), 'a', 60) is True
            assert scheduler_leader.write_heartbeat(node, True, utc_now(), 'b', 60) is False
            row = db.session.get(ClusterNode, node)
            assert (row.instance_token, row.is_leader) == ('a', False)
            row.heartbeat_at = utc_now() - timedelta(seconds=181)
            db.session.commit()
            assert scheduler_leader.write_heartbeat(node, False, utc_now(), 'b', 60) is True
            db.session.expire_all()
            assert db.session.get(ClusterNode, node).instance_token == 'b'
        finally:
            ClusterNode.query.filter_by(node_id=node).delete()
            db.session.commit()
