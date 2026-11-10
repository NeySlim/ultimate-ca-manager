"""HA scheduler leadership on a PostgreSQL session advisory lock: one leader, and a lost
connection stops the tasks on that node before another one takes over."""
import secrets
import threading
import time
from datetime import timedelta

import pytest
from sqlalchemy import text

from config.settings import Config
from services import scheduler_leader, scheduler_service
from services.scheduler_service import SchedulerService
from tests import pg_app_harness

pytestmark = pytest.mark.skipif(not pg_app_harness.ENABLED,
                                reason='needs UCM_TEST_APP_PG_URL (HA runs on PostgreSQL)')

RETRY = 0.5


def wait_for(predicate, timeout=5.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.01)
    return predicate()


@pytest.fixture
def ha(app, monkeypatch, tmp_path):
    """HA mode, a lock key of this test's own, and schedulers stopped afterwards."""
    monkeypatch.setattr(Config, 'HA_MODE', True)
    monkeypatch.setattr('config.settings.DATA_DIR', tmp_path, raising=False)
    monkeypatch.setattr(scheduler_leader, 'LEADER_LOCK_KEY', secrets.randbits(62))
    monkeypatch.setattr(scheduler_service, 'LOCK_RETRY_SECONDS', RETRY)
    made = []

    def make(node_id, task):
        s = SchedulerService(wake_interval=0.05, node_id=node_id)
        s.register_task('tick', task, interval=0)
        s.tasks['tick']._created_at -= timedelta(seconds=60)
        made.append(s)
        return s
    yield make
    for s in made:
        s.stop(timeout=10)
    from models import ClusterNode, db
    with app.app_context():
        ClusterNode.query.delete()  # their heartbeats, out of the shared test schema
        db.session.commit()


def kill_backend(app, pid):
    from models import db
    with app.app_context():
        with db.engine.connect() as conn:
            assert conn.execute(text('SELECT pg_terminate_backend(:p)'), {'p': pid}).scalar()
            conn.commit()


def backend_alive(app, pid):
    from models import db
    with app.app_context():
        with db.engine.connect() as conn:
            return bool(conn.execute(text('SELECT count(*) FROM pg_stat_activity WHERE pid = :p'),
                                     {'p': pid}).scalar())


def test_one_leader_and_takeover_after_the_lock_connection_dies(app, ha):
    starts = {'a': 0, 'b': 0}
    inside, gate = threading.Event(), threading.Event()
    blocked = []

    def task_for(name):
        def run():
            starts[name] += 1
            if not blocked:  # the first run anywhere waits for the kill
                blocked.append(name)
                inside.set()
                assert gate.wait(10)
        return run
    a, b = ha('node-a', task_for('a')), ha('node-b', task_for('b'))
    a.start(app=app)
    b.start(app=app)

    assert inside.wait(5)
    leader, follower = (a, b) if blocked == ['a'] else (b, a)
    old = blocked[0]
    new = 'b' if old == 'a' else 'a'
    assert leader._owns_lock and not follower._owns_lock
    assert starts[new] == 0

    lost_at = time.monotonic()
    kill_backend(app, leader._leader_lock.backend_pid)
    gate.set()  # the task running when the lock went away finishes

    assert wait_for(lambda: follower._owns_lock, timeout=2 * RETRY + 1)
    assert time.monotonic() - lost_at < 2 * RETRY
    assert wait_for(lambda: starts[new] > 0)
    assert wait_for(lambda: not leader._owns_lock or starts[old] > 1, timeout=2)
    time.sleep(3 * 0.05 + 0.2)
    assert starts[old] == 1, 'a task started on the node that lost the lock'
    assert not (leader._owns_lock and follower._owns_lock)


def test_still_held_asks_the_server(app, ha, monkeypatch):
    from models import db
    with app.app_context():
        url = db.engine.url
    lock = scheduler_leader.PgAdvisoryLock(url)
    other = scheduler_leader.PgAdvisoryLock(url)
    try:
        assert lock.acquire() and lock.still_held()
        assert not other.acquire()
        kill_backend(app, lock.backend_pid)
        assert not lock.still_held()
        assert other.acquire()
    finally:
        lock.dispose()
        other.dispose()


def test_a_follower_keeps_one_session_across_its_attempts(app, ha):
    """A non-leader retries every few seconds on the same connection, not a new one each time."""
    from models import db
    with app.app_context():
        url = db.engine.url
    lock = scheduler_leader.PgAdvisoryLock(url)
    other = scheduler_leader.PgAdvisoryLock(url)
    try:
        assert lock.acquire()
        pids = set()
        for _ in range(4):
            assert not other.acquire()
            pids.add(other._conn.execute(text('SELECT pg_backend_pid()')).scalar())
        assert len(pids) == 1
        pid = pids.pop()
        kill_backend(app, pid)  # a dropped session is opened again
        assert wait_for(lambda: not backend_alive(app, pid))
        lock.release()
        assert other.acquire() and other.still_held()
    finally:
        lock.dispose()
        other.dispose()


def test_the_lock_session_has_server_side_dead_peer_timeouts(app, ha):
    """The server, not only the client, must drop the session of a leader whose host vanished."""
    from models import db
    with app.app_context():
        url = db.engine.url
    lock = scheduler_leader.PgAdvisoryLock(url)
    try:
        assert lock.acquire()
        shown = {name: lock._conn.execute(text(f'SHOW {name}')).scalar()
                 for name in ('tcp_keepalives_idle', 'tcp_keepalives_interval',
                              'tcp_keepalives_count', 'tcp_user_timeout')}
        search_path = lock._conn.execute(text('SHOW search_path')).scalar()
    finally:
        lock.dispose()
    assert shown == {'tcp_keepalives_idle': '30', 'tcp_keepalives_interval': '10',
                     'tcp_keepalives_count': '3', 'tcp_user_timeout': '60000'}
    assert pg_app_harness.SCHEMA in search_path  # the URL's own options are kept


def test_without_ha_the_host_lock_is_used(app, monkeypatch, tmp_path):
    monkeypatch.setattr(Config, 'HA_MODE', False)
    monkeypatch.setattr('config.settings.DATA_DIR', tmp_path, raising=False)
    s = SchedulerService(wake_interval=3600)
    try:
        assert s._singleton_lock().acquire()
        assert s._leader_lock is None and s._lock_fd is not None
    finally:
        s._release_lock()


def test_a_lock_lost_mid_pass_stops_the_tasks_left_in_that_pass(app, ha, monkeypatch):
    # A long retry: the node cannot take the lock back before the assertions run
    monkeypatch.setattr(scheduler_service, 'LOCK_RETRY_SECONDS', 30)
    runs = []
    s = ha('node-a', lambda: None)
    del s.tasks['tick']

    def first():
        runs.append('first')
        pid = s._leader_lock.backend_pid
        kill_backend(app, pid)
        assert wait_for(lambda: not backend_alive(app, pid))  # termination is asynchronous

    for name, func in (('first', first), ('second', lambda: runs.append('second'))):
        s.register_task(name, func, interval=3600)
        s.tasks[name]._created_at -= timedelta(seconds=7200)
    s.start(app=app)

    assert wait_for(lambda: runs and not s._owns_lock)
    time.sleep(0.3)
    assert runs == ['first'], 'a task started after the lock was lost'
