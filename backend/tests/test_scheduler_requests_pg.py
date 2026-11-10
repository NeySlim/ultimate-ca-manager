"""HA run-now through the database: a request asked on any node runs once on the leader,
never again on the next leader, and every node reads the task state the leader published."""
import json
import secrets
import threading
import time

import pytest
from sqlalchemy import text

from config.settings import Config
from services import scheduler_leader, scheduler_service
from services.scheduler_service import SchedulerService
from tests import pg_app_harness

pytestmark = pytest.mark.skipif(not pg_app_harness.ENABLED,
                                reason='needs UCM_TEST_APP_PG_URL (HA runs on PostgreSQL)')

RETRY = 0.3


def wait_for(predicate, timeout=5.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.02)
    return predicate()


def _clean(app):
    from models import ClusterNode, SchedulerRequest, SystemConfig, db
    with app.app_context():
        SchedulerRequest.query.delete()
        ClusterNode.query.delete()
        SystemConfig.query.filter_by(key=scheduler_service.STATE_KEY).delete()
        db.session.commit()


@pytest.fixture
def ha(app, monkeypatch, tmp_path):
    monkeypatch.setattr(Config, 'HA_MODE', True)
    monkeypatch.setattr('config.settings.DATA_DIR', tmp_path, raising=False)
    monkeypatch.setattr(scheduler_leader, 'LEADER_LOCK_KEY', secrets.randbits(62))
    monkeypatch.setattr(scheduler_service, 'LOCK_RETRY_SECONDS', RETRY)
    monkeypatch.setattr(scheduler_service, 'REQUEST_POLL_SECONDS', 0.05)
    _clean(app)
    made = []

    def make(node_id, task):
        # Only run-now starts a task here: the interval and grace period are far off
        s = SchedulerService(wake_interval=3600, node_id=node_id)
        s.register_task('t', task, interval=3600)
        made.append(s)
        return s
    yield make
    for s in made:
        s.stop(timeout=10)
    _clean(app)


def pending_requests(app):
    from models import SchedulerRequest, db
    with app.app_context():
        db.session.expire_all()
        return SchedulerRequest.query.count()


def test_run_now_on_a_follower_runs_once_on_the_leader(app, ha):
    ran_on = []
    leader = ha('leader', lambda: ran_on.append(threading.current_thread().name))
    follower = ha('follower', lambda: ran_on.append('follower'))
    leader.start(app=app)
    assert wait_for(lambda: leader._owns_lock)
    with app.app_context():
        status = follower.run_task_now('t')
    assert ran_on == ['SchedulerService']
    assert status['run_count'] == 1 and not status.get('queued')
    assert wait_for(lambda: pending_requests(app) == 0)


def test_the_follower_reads_the_state_the_leader_published(app, ha, monkeypatch):
    leader = ha('leader', lambda: {'status': 'skipped', 'reason': 'nothing to do'})
    follower = ha('follower', lambda: None)
    leader.start(app=app)
    assert wait_for(lambda: leader._owns_lock)
    with app.app_context():
        follower.run_task_now('t')
        status = follower.get_all_tasks_status()['t']
        assert status['last_status'] == 'skipped' and status['run_count'] == 1
        assert 'stale' not in status and not follower.state_is_stale()
        assert follower.tasks['t'].run_count == 0  # its own copy never ran
        from models import SystemConfig, db
        row = SystemConfig.query.filter_by(key=scheduler_service.STATE_KEY).first()
        state = json.loads(row.value)
        state['published_at'] -= 3 * 3600
        row.value = json.dumps(state)
        db.session.commit()
        assert follower.state_is_stale()
        assert follower.get_all_tasks_status()['t']['stale'] is True


def test_a_request_taken_by_a_leader_that_lost_the_lock_is_not_replayed(app, ha, monkeypatch):
    monkeypatch.setattr(scheduler_service, 'RUN_NOW_WAIT_SECONDS', 0.1)
    runs = []
    inside, gate = threading.Event(), threading.Event()

    def task_for(name):
        def run():
            runs.append(name)
            inside.set()
            assert gate.wait(10)
        return run
    first, second = ha('first', task_for('first')), ha('second', task_for('second'))
    first.start(app=app)
    assert wait_for(lambda: first._owns_lock)
    second.start(app=app)
    asker = ha('asker', task_for('asker'))
    with app.app_context():
        assert asker.run_task_now('t').get('queued')
    assert inside.wait(5)
    from models import db
    with app.app_context():
        with db.engine.connect() as conn:
            conn.execute(text('SELECT pg_terminate_backend(:p)'), {'p': first._leader_lock.backend_pid})
            conn.commit()
    assert wait_for(lambda: second._owns_lock, timeout=3)
    assert wait_for(lambda: pending_requests(app) == 0)  # dropped by the new leader, not run
    gate.set()
    time.sleep(1)
    assert runs == ['first']
    assert wait_for(lambda: pending_requests(app) == 0)


def test_chain_repair_run_now_goes_through_the_leader(app, auth_client, ha, monkeypatch):
    ran_on = []
    leader = ha('leader', lambda: None)
    leader.register_task('ski_aki_backfill', lambda: ran_on.append('leader'), interval=3600)
    follower = ha('follower', lambda: None)
    follower.register_task('ski_aki_backfill', lambda: ran_on.append('follower'), interval=3600)
    monkeypatch.setattr(scheduler_service, '_scheduler', follower)
    leader.start(app=app)
    assert wait_for(lambda: leader._owns_lock)
    r = auth_client.post('/api/v2/system/chain-repair/run')
    assert r.status_code == 200, r.get_data(as_text=True)
    assert ran_on == ['leader']


def test_a_request_is_claimed_by_one_scheduler_only(app, ha):
    one, two = ha('one', lambda: None), ha('two', lambda: None)
    with app.app_context():
        from models import SchedulerRequest, db
        from utils.datetime_utils import utc_now
        db.session.add(SchedulerRequest(task_name='t', requested_at=utc_now(), requested_by='x'))
        db.session.commit()
        assert [t.name for t in one._claim_db_requests()] == ['t']
        assert two._claim_db_requests() == []
