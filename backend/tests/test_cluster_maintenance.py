"""HA cluster maintenance on the node itself: what it refuses, what it still serves, and
nothing at all outside HA. The view is set by hand; test_cluster_maintenance_pg.py drives it
through the database between two applications."""
import time
from datetime import timedelta

import pytest

from config.settings import Config
from services import cluster_maintenance as cm
from utils.datetime_utils import utc_now


def _row(phase=cm.PHASE_MANUAL, reason=cm.REASON_MANUAL, minutes=5, restored_at=None):
    now = utc_now()
    return {'token': 'tok', 'reason': reason, 'phase': phase, 'started_at': now,
            'expires_at': now + timedelta(minutes=minutes), 'restored_at': restored_at,
            'node_id': 'node-x', 'actor': 'admin'}, now


@pytest.fixture
def held(app, monkeypatch):
    """HA on, this application's view in maintenance; never read again from the database."""
    monkeypatch.setattr(Config, 'HA_MODE', True)
    monkeypatch.setattr(cm, 'OBSERVE_TTL_SECONDS', 3600)
    view = cm.view_of(app)
    row, now = _row()
    view.set(row, now)
    yield view
    view.row, view.observed, view.process_started, view.deadline = None, None, None, 0.0


@pytest.mark.parametrize('statement, writes', [
    ('SELECT 1', False),
    ('  insert into t values (1)', True),
    ('UPDATE t SET a = 1', True),
    ('DELETE FROM t', True),
    ('WITH x AS (SELECT 1) SELECT * FROM x', False),
    ('WITH x AS (DELETE FROM t RETURNING id) SELECT * FROM x', True),
    ('SELECT pg_try_advisory_lock(1)', False),
    ('TRUNCATE t', True),
])
def test_write_statements(statement, writes):
    assert cm.is_write(statement) is writes


def test_a_node_in_maintenance_refuses_writes_and_protocols(app, auth_client, held):
    r = auth_client.post('/api/v2/certificates', json={})
    assert r.status_code == 503
    assert r.headers['Retry-After'] == str(cm.RETRY_AFTER_SECONDS)
    body = r.get_json()
    assert body['code'] == 'maintenance' and body['maintenance']['phase'] == cm.PHASE_MANUAL
    for path in ('/acme/directory', '/scep/pkiclient.exe?operation=GetCACaps',
                 '/.well-known/est/cacerts'):
        refused = auth_client.get(path)
        assert refused.status_code == 503, path
        assert (refused.get_json() or {}).get('code') == 'maintenance', path


def test_a_node_in_maintenance_still_serves_reads_health_ocsp_and_the_control_routes(
        app, auth_client, held):
    assert auth_client.get('/api/v2/cas').status_code == 200
    health = auth_client.get('/health')
    assert health.status_code == 200 and health.get_json()['maintenance']['reason'] == 'manual'
    ready = auth_client.get('/health/ready')
    assert ready.status_code == 503 and ready.get_json()['status'] == 'maintenance'
    assert auth_client.get('/health/live').status_code == 200
    assert auth_client.post('/ocsp', data=b'not der',
                            content_type='application/ocsp-request').status_code != 503
    assert auth_client.get('/api/v2/system/maintenance').status_code == 200


def test_the_write_guard_spares_only_the_exempt_writer(app, held):
    from models import SystemConfig, db
    key = 'hd1-guard-test'
    with app.app_context():
        db.session.add(SystemConfig(key=key, value='x'))
        with pytest.raises(cm.MaintenanceActive):
            db.session.flush()
        db.session.rollback()
        with cm.exempt():
            db.session.add(SystemConfig(key=key, value='x'))
            db.session.commit()
            SystemConfig.query.filter_by(key=key).delete()
            db.session.commit()


def test_a_cdp_without_a_stored_crl_signs_none_during_maintenance(app, auth_client, create_ca,
                                                                   monkeypatch):
    ca = create_ca()
    from models import CA, db
    from models.crl import CRLMetadata
    with app.app_context():
        CRLMetadata.query.filter_by(ca_id=ca['id']).delete()
        db.session.commit()
        refid = db.session.get(CA, ca['id']).refid
    from services.crl_service import CRLService

    def no_signing(*a, **k):
        raise AssertionError('no CRL is signed during the maintenance')
    monkeypatch.setattr(CRLService, 'generate_crl', staticmethod(no_signing))
    monkeypatch.setattr(Config, 'HA_MODE', True)
    monkeypatch.setattr(cm, 'OBSERVE_TTL_SECONDS', 3600)
    view = cm.view_of(app)
    view.set(*_row())
    try:
        r = auth_client.get(f'/cdp/{refid}.crl')
    finally:
        view.row, view.observed, view.deadline = None, None, 0.0
    assert r.status_code == 503 and r.headers['Retry-After'] == '30'


def test_a_restarted_process_serves_once_the_rolling_restart_is_asked(app, held):
    restored = utc_now()
    held.set(*_row(phase=cm.PHASE_RESTARTING, reason=cm.REASON_RESTORE, restored_at=restored))
    held.process_started = restored - timedelta(seconds=5)
    assert held.active()
    held.process_started = restored + timedelta(seconds=5)
    assert not held.active()


def test_a_lease_that_ended_frees_the_node_unless_the_restore_committed(app, held):
    row, now = _row(phase=cm.PHASE_RESTORING, reason=cm.REASON_RESTORE)
    held.set(row, now)
    held.deadline = time.monotonic() - 1
    assert not held.active()
    held.row = dict(row, phase=cm.PHASE_COMMITTED)
    assert held.active()


def test_no_task_starts_during_maintenance_and_an_asked_run_waits(app, held):
    from services.scheduler_service import SchedulerService
    ran = []
    scheduler = SchedulerService()
    scheduler._app = app
    scheduler.register_task(name='hd1_probe', func=lambda: ran.append(1), interval=60)
    task = scheduler.tasks['hd1_probe']
    assert scheduler._try_run(task, requested=True) is False
    assert ran == [] and task in scheduler._deferred
    held.row = None
    assert scheduler._try_run(task, requested=True) is True
    assert ran == [1]


def test_no_session_row_is_written_during_maintenance(app, held, monkeypatch):
    from utils.session_store import IsolatedSqlSessionInterface

    def no_store(self):
        raise AssertionError('no session row during the maintenance')
    monkeypatch.setattr(IsolatedSqlSessionInterface, '_store', no_store)
    interface = IsolatedSqlSessionInterface.__new__(IsolatedSqlSessionInterface)
    with app.app_context():
        for call in (lambda: interface._upsert_session(timedelta(hours=1), {}, 'sid'),
                     lambda: interface._delete_session('sid'),
                     lambda: interface._delete_expired_sessions()):
            assert call() is None


def test_outside_ha_a_row_changes_nothing(app, auth_client, monkeypatch):
    """A single node never reads the maintenance, holds none and answers as before."""
    from models import db
    monkeypatch.setattr(Config, 'HA_MODE', False)
    with app.app_context():
        assert cm.current() is None
        with cm.restore_window('admin') as hold:
            assert hold is None
        assert db.session.execute(db.text("SELECT count(*) FROM cluster_maintenance")).scalar() == 0
    r = auth_client.get('/health')
    assert 'maintenance' not in r.get_json()
    assert auth_client.get('/health/ready').get_json()['status'] != 'maintenance'


def test_a_rollback_after_the_connection_dropped_mid_transaction_does_not_raise():
    """A connection invalidated inside its transaction (the database dropped it) rolls back
    cleanly: the guard's rollback hook never turns that into an error of its own."""
    from types import SimpleNamespace

    from sqlalchemy import create_engine, text
    engine = create_engine('sqlite://')
    cm.install_engine_guard(SimpleNamespace(extensions={}), engine)
    conn = engine.connect()
    conn.begin()
    conn.execute(text('SELECT 1'))
    conn.invalidate()
    conn.rollback()
    assert conn.invalidated
    conn.close()
    engine.dispose()


def test_a_node_that_loses_the_completion_leaves_the_epoch_alone(app):
    """Another node already completed the committed restore: this one's UPDATE touches
    no row, and it must not refuse the sessions opened since that completion."""
    from sqlalchemy import text
    from auth.session_epoch import advance_epoch, current_epoch
    from models import db
    row, now = _row(phase=cm.PHASE_COMMITTED, reason=cm.REASON_RESTORE, minutes=-1)
    with app.app_context(), cm.exempt():
        advance_epoch()
        db.session.execute(text(
            "INSERT INTO cluster_maintenance (id, token, reason, phase, started_at, expires_at, "
            "node_id) VALUES (:id, :t, :r, :p, :s, :e, 'node-x')"),
            {'id': cm.ROW_ID, 't': row['token'], 'r': row['reason'], 'p': cm.PHASE_RESTARTING,
             's': row['started_at'], 'e': row['expires_at']})
        db.session.commit()
        try:
            epoch = current_epoch()
            assert cm.complete_committed(row, now) is False
            assert current_epoch() == epoch
        finally:
            db.session.rollback()
            db.session.execute(text("DELETE FROM cluster_maintenance"))
            db.session.commit()


def test_a_completion_whose_session_cleanup_fails_says_so_and_stays_completed(app, monkeypatch, caplog):
    """The epoch, the phase and the restart are committed first: a cleanup that fails after
    them is reported once, and the restore is not completed a second time."""
    import logging
    from sqlalchemy import text
    from auth.session_epoch import current_epoch
    from models import db
    from services.backup.restore import invalidate
    row, now = _row(phase=cm.PHASE_COMMITTED, reason=cm.REASON_RESTORE, minutes=-1)

    def broken():
        raise RuntimeError('session store away')
    monkeypatch.setattr(invalidate, '_revoke_database_sessions', broken)
    with app.app_context(), cm.exempt():
        db.session.execute(text(
            "INSERT INTO cluster_maintenance (id, token, reason, phase, started_at, expires_at, "
            "node_id) VALUES (:id, :t, :r, :p, :s, :e, 'node-x')"),
            {'id': cm.ROW_ID, 't': row['token'], 'r': row['reason'], 'p': row['phase'],
             's': row['started_at'], 'e': row['expires_at']})
        db.session.commit()
        try:
            epoch = current_epoch()
            with caplog.at_level(logging.ERROR, logger=cm.logger.name):
                assert cm.complete_committed(row, now) is True
            assert current_epoch() != epoch
            assert cm.read_row(db.session)['phase'] == cm.PHASE_RESTARTING
            said = [r.getMessage() for r in caplog.records if r.levelno == logging.ERROR]
            assert len(said) == 1 and 'session store away' in said[0] and 'epoch' in said[0], said
        finally:
            db.session.rollback()
            db.session.execute(text("DELETE FROM cluster_maintenance"))
            db.session.execute(text("DELETE FROM cluster_commands"))
            db.session.commit()


def test_a_login_on_a_node_in_maintenance_is_refused_before_the_session_epoch_is_read(
        app, client, held, monkeypatch):
    from auth import session_epoch

    def unreadable():
        raise RuntimeError('the database is away')
    monkeypatch.setattr(session_epoch, 'current_epoch', unreadable)
    r = client.post('/api/v2/auth/login/password', json={'username': 'admin', 'password': 'x'})
    assert r.status_code == 503 and r.get_json()['code'] == 'maintenance'
