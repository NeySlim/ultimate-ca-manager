"""The two restore routes start a job: 202 and a Location past the wait or with
`Prefer: respond-async`, the answer of today within it, 409 naming the active job, 503 during
a maintenance, and never an archive file left by a start that did not happen."""
import io
import os
import threading
import uuid

import pytest

from models import db
from services import jobs
from services.jobs import restore as restore_job
from services.jobs import runner, store
from tests.job_dispatch_support import DeferredDispatch
from tests.test_restore_job import GROUP, PASSWORD, _has_group, archive  # noqa: F401 (fixture)

ROUTES = ['/api/v2/system/restore', '/api/v2/settings/backup/restore']


def _post(client, route, blob, headers=None):
    return client.post(route, headers=headers or {}, data={
        'file': (io.BytesIO(blob), 'r.ucmbkp'), 'password': PASSWORD},
        content_type='multipart/form-data')


def _archives():
    directory = store.jobs_tmp_dir()
    if not os.path.isdir(directory):
        return []
    return [n for n in os.listdir(directory) if n.endswith(restore_job.ARCHIVE_SUFFIX)]


@pytest.fixture
def finished(app, monkeypatch):
    """Jobs start once the request has answered, and none is left active after the test.
    The tests' SQLite is one shared connection; production threads each have their own."""
    deferred = DeferredDispatch(app, monkeypatch)
    yield deferred
    deferred.conclude_leftovers()
    restore_job.remove_state()


@pytest.fixture
def no_restart(monkeypatch):
    asked = []
    monkeypatch.setattr('services.backup.restore_completion.request_restart',
                        lambda: asked.append(1) or (True, 'Service restart initiated'))
    return asked


@pytest.mark.parametrize('route', ROUTES)
def test_respond_async_answers_202_then_the_job_tells_the_end(app, auth_client, archive, finished,
                                                           no_restart, route):
    r = _post(auth_client, route, archive, {'Prefer': 'respond-async'})
    assert r.status_code == 202, r.data
    assert r.headers['Preference-Applied'] == 'respond-async'
    job = r.get_json()['data']['job']
    assert r.headers['Location'] == f"/api/v2/system/jobs/{job['id']}"
    assert job['kind'] == 'restore' and 'result' not in job
    assert runner.join_local(job['id'], 60)
    seen = auth_client.get(r.headers['Location'])
    assert seen.status_code == 200
    data = seen.get_json()['data']
    assert (data['state'], data['phase']) == ('succeeded', restore_job.CRLS)
    assert data['result']['data']['restart_requested'] is True
    assert data['result']['message'].startswith('Backup restored successfully')
    with app.app_context():
        assert _has_group()
    assert not _archives()


@pytest.mark.parametrize('route', ROUTES)
def test_a_restore_past_the_wait_answers_202(app, auth_client, archive, finished, no_restart,
                                             monkeypatch, route):
    reached, release = threading.Event(), threading.Event()
    real = restore_job._Run.checkpoint

    def held(run, step):
        if step == 'plan' and not reached.is_set():
            reached.set()
            assert release.wait(30)
        return real(run, step)
    monkeypatch.setattr(restore_job._Run, 'checkpoint', held)
    try:
        r = _post(auth_client, route, archive, {'Prefer': 'wait=1'})
        assert r.status_code == 202, r.data
        assert 'Preference-Applied' not in r.headers
        assert reached.is_set()
    finally:
        release.set()
    # Ended here, while the stubs hold: never the real restart after the test
    job_id = r.get_json()['data']['job']['id']
    assert runner.join_local(job_id, 60)
    with app.app_context():
        assert jobs.get_job(job_id)['state'] == 'succeeded'
    assert no_restart == [1]


@pytest.mark.parametrize('route', ROUTES)
def test_a_restore_while_a_job_runs_is_refused_naming_it_and_leaves_no_file(
        app, auth_client, archive, finished, monkeypatch, route):
    monkeypatch.setattr(runner, 'dispatch_job', lambda job_id: None)
    with app.app_context():
        jt = jobs.job_type('audit_verify')
        other = store.create_job(db.session, kind=jt.kind, slot=jt.slot, exclusive=False,
                                 exclusive_slots=jobs.EXCLUSIVE_SLOTS, now=jobs._now())
    try:
        r = _post(auth_client, route, archive)
        assert r.status_code == 409, r.data
        body = r.get_json()
        assert body['details']['job']['id'] == other
        assert not _archives(), 'the archive of a refused start stayed on disk'
    finally:
        with app.app_context():
            jobs.request_cancellation(other)


@pytest.mark.parametrize('route', ROUTES)
def test_a_maintenance_refuses_the_start_before_any_file(app, auth_client, archive, finished,
                                                         monkeypatch, route):
    from services import cluster_maintenance
    view = cluster_maintenance.view_of(app)
    with monkeypatch.context() as patch:
        patch.setattr(view, 'active', lambda: True)
        patch.setattr(cluster_maintenance, 'current', lambda refresh=True: view)
        r = _post(auth_client, route, archive)
    assert r.status_code == 503 and r.headers['Retry-After']
    assert not _archives()


def test_a_start_refused_after_the_file_removes_it(app, auth_client, archive, finished, monkeypatch):
    """JobsSuspended raised by start_job itself (a maintenance seen between the check and the
    insert): the file written just before goes."""
    def suspended(*args, **kwargs):
        raise jobs.JobsSuspended()
    monkeypatch.setattr(jobs, 'start_job', suspended)
    r = _post(auth_client, ROUTES[0], archive)
    assert r.status_code == 503
    assert not _archives()


def test_a_restore_job_is_read_only_with_admin_system(app, auth_client, viewer_client, finished,
                                                      monkeypatch):
    monkeypatch.setattr(runner, 'dispatch_job', lambda job_id: None)
    with app.app_context():
        job_id = store.create_job(db.session, kind=restore_job.KIND, slot=jobs.SLOT_RESTORE,
                                  exclusive=True, exclusive_slots=jobs.EXCLUSIVE_SLOTS,
                                  now=jobs._now())
        jobs.request_cancellation(job_id)
    assert auth_client.get(f'/api/v2/system/jobs/{job_id}').status_code == 200
    assert viewer_client.get(f'/api/v2/system/jobs/{job_id}').status_code == 404
    listed = viewer_client.get('/api/v2/system/jobs').get_json()['data']
    assert job_id not in [j['id'] for j in listed]


def test_the_cancel_route_says_a_committed_restore_is_too_late(app, auth_client, archive, finished,
                                                             no_restart, monkeypatch):
    reached, release = threading.Event(), threading.Event()
    real = restore_job._finish_steps

    def held(job_id):
        reached.set()
        assert release.wait(30)
        return real(job_id)
    monkeypatch.setattr(restore_job, '_finish_steps', held)
    assert auth_client.get('/api/v2/system/jobs').status_code == 200  # signed in before the gate
    r = _post(auth_client, ROUTES[0], archive, {'Prefer': 'respond-async'})
    job_id = r.get_json()['data']['job']['id']
    finished.release()
    try:
        assert reached.wait(30)
        cancel = auth_client.post(f'/api/v2/system/jobs/{job_id}/cancel')
        assert cancel.status_code == 409, cancel.data
        assert cancel.get_json()['message'] == restore_job.TOO_LATE
    finally:
        release.set()
    assert runner.join_local(job_id, 60)


@pytest.mark.parametrize('respond_async', [False, True])
def test_a_maintenance_refusal_keeps_its_code_and_nodes(app, auth_client, archive, finished,
                                                        monkeypatch, respond_async):
    """The 409 of a refused maintenance carries its text `code` and the silent `nodes`, as before
    jobs, whether the route answers it or the job read after a 202 does."""
    from contextlib import contextmanager
    from services import cluster_maintenance

    @contextmanager
    def refused(*args, **kwargs):
        raise cluster_maintenance.NodesNotAcknowledged({'node-b': ['web', 'scheduler']})
        yield
    monkeypatch.setattr(cluster_maintenance, 'restore_window', refused)
    r = _post(auth_client, ROUTES[0], archive, {'Prefer': 'respond-async'} if respond_async else None)
    if respond_async:
        assert r.status_code == 202
        job_id = r.get_json()['data']['job']['id']
        assert runner.join_local(job_id, 60)
        r = auth_client.get(f'/api/v2/system/jobs/{job_id}')
        body = r.get_json()['data']['result']
        assert body['code'] == 409 and body['problem'] == {
            'code': 'maintenance_not_acknowledged', 'nodes': {'node-b': ['web', 'scheduler']}}
        return
    assert r.status_code == 409, r.data
    body = r.get_json()
    assert body['code'] == 'maintenance_not_acknowledged'
    assert body['nodes'] == {'node-b': ['web', 'scheduler']}


@pytest.mark.parametrize('route', ROUTES)
def test_a_refusal_concluded_by_the_runner_names_the_archive(app, auth_client, archive, finished,
                                                            monkeypatch, route):
    from sqlalchemy import select

    from models import AuditLog

    def unreadable(self, *a, **k):
        raise ValueError('broken')
    monkeypatch.setattr('services.backup_service.BackupService.restore_backup_from_stream',
                        unreadable)
    r = auth_client.post(route, headers={'Prefer': 'respond-async'}, data={
        'file': (io.BytesIO(archive), 'mine.ucmbkp'), 'password': PASSWORD},
        content_type='multipart/form-data')
    assert r.status_code == 202, r.data
    job_id = r.get_json()['data']['job']['id']
    assert runner.join_local(job_id, 60)
    with app.app_context():
        lines = db.session.execute(select(AuditLog.success, AuditLog.resource_name).where(
            AuditLog.action == restore_job.ACTION, AuditLog.resource_id == job_id)).all()
    assert [tuple(line) for line in lines] == [(False, 'mine.ucmbkp')]


@pytest.fixture
def maintenance_view(app, monkeypatch):
    """HA on; set(reason) puts this application's view in that maintenance, never read again."""
    from datetime import timedelta
    from config.settings import Config
    from services import cluster_maintenance as cm
    from utils.datetime_utils import utc_now
    monkeypatch.setattr(Config, 'HA_MODE', True)
    monkeypatch.setattr(cm, 'OBSERVE_TTL_SECONDS', 3600)
    view = cm.view_of(app)

    def put(reason):
        now = utc_now()
        view.set({'token': 'tok', 'reason': reason, 'phase': (
            cm.PHASE_MANUAL if reason == cm.REASON_MANUAL else cm.PHASE_RESTORING),
            'started_at': now, 'expires_at': now + timedelta(minutes=5), 'restored_at': None,
            'node_id': 'node-x', 'actor': 'admin'}, now)
    yield put
    view.row, view.observed, view.process_started, view.deadline = None, None, None, 0.0


def _job(app, kind, take=False):
    with app.app_context():
        jt = jobs.job_type(kind)
        job_id = store.create_job(db.session, kind=kind, slot=jt.slot,
                                  exclusive=jt.slot in jobs.EXCLUSIVE_SLOTS,
                                  exclusive_slots=jobs.EXCLUSIVE_SLOTS, now=jobs._now())
        if take:
            assert store.claim_job(db.session, job_id, 'elsewhere/1/x', jobs._now()) is not None
    return job_id


@pytest.mark.parametrize('kind', ['audit_verify', 'restore'])
def test_an_administrators_maintenance_refuses_every_cancellation(
        app, auth_client, finished, maintenance_view, monkeypatch, kind):
    """No job holds a manual maintenance: cancelling one would write its conclusion and its
    audit line while every write is refused. 503, nothing written."""
    from services import cluster_maintenance as cm
    monkeypatch.setattr(runner, 'dispatch_job', lambda job_id: None)
    assert auth_client.get('/api/v2/system/jobs').status_code == 200  # signed in before it
    job_id = _job(app, kind)
    maintenance_view(cm.REASON_MANUAL)
    r = auth_client.post(f'/api/v2/system/jobs/{job_id}/cancel')
    assert r.status_code == 503, r.data
    assert r.headers['Retry-After'] == str(cm.RETRY_AFTER_SECONDS)
    with app.app_context():
        assert jobs.get_job(job_id)['state'] == 'pending'
    # Refused at the gate, before the route reads anything
    assert auth_client.post(f'/api/v2/system/jobs/{uuid.uuid4()}/cancel').status_code == 503


def test_a_job_that_does_not_hold_a_restore_maintenance_is_not_cancelled_through_it(
        app, auth_client, finished, maintenance_view, monkeypatch):
    """A restore's maintenance lets the cancel route through: the route writes for its job only."""
    from services import cluster_maintenance as cm
    monkeypatch.setattr(runner, 'dispatch_job', lambda job_id: None)
    assert auth_client.get('/api/v2/system/jobs').status_code == 200
    job_id = _job(app, 'audit_verify')
    maintenance_view(cm.REASON_RESTORE)
    r = auth_client.post(f'/api/v2/system/jobs/{job_id}/cancel')
    assert r.status_code == 503, r.data
    with app.app_context():
        assert jobs.get_job(job_id)['state'] == 'pending'


@pytest.mark.parametrize('kind', ['audit_verify', 'restore'])
def test_a_job_that_does_not_hold_a_single_nodes_restore_gate_is_not_cancelled_through_it(
        app, auth_client, finished, monkeypatch, kind):
    """One node: the gate of a restore lets the cancel route through, for the job holding it
    only; another restore (a gate left by one that died) is no more its holder than a verification."""
    import types
    monkeypatch.setattr(runner, 'dispatch_job', lambda job_id: None)
    assert auth_client.get('/api/v2/system/jobs').status_code == 200  # signed in before the gate
    job_id = _job(app, kind)
    holder = types.SimpleNamespace(job_id=str(uuid.uuid4()), node_id=None, requested_by='admin',
                                   view={'id': 'x', 'kind': 'restore'}, app=app)
    gate = restore_job.LocalGate(app, holder).raise_gate()
    try:
        r = auth_client.post(f'/api/v2/system/jobs/{job_id}/cancel')
    finally:
        gate.lift()
    assert r.status_code == 503, r.data
    with app.app_context():
        assert jobs.get_job(job_id)['state'] == 'pending'


def test_only_the_restore_holding_the_maintenance_is_cancelled_through_it(
        app, auth_client, finished, maintenance_view, monkeypatch):
    from services import cluster_maintenance as cm
    monkeypatch.setattr(runner, 'dispatch_job', lambda job_id: None)
    assert auth_client.get('/api/v2/system/jobs').status_code == 200
    job_id = _job(app, 'restore', take=True)
    maintenance_view(cm.REASON_RESTORE)
    r = auth_client.post(f'/api/v2/system/jobs/{job_id}/cancel')
    assert r.status_code == 200, r.data
    assert r.get_json()['data']['cancel_requested'] is True
    with app.app_context():
        assert jobs.get_job(job_id)['cancel_requested']


def test_the_end_steps_show_the_rows_phase_and_progress(app, auth_client, archive, finished,
                                                        no_restart, monkeypatch):
    """Past the commit the local state is older than the row: the route shows the row
    (paused before the end steps, as the sessions they revoke include the caller's)."""
    reached, release = threading.Event(), threading.Event()
    real = restore_job._finish_steps

    def paused(job_id):
        reached.set()
        assert release.wait(30)
        return real(job_id)
    monkeypatch.setattr(restore_job, '_finish_steps', paused)
    assert auth_client.get('/api/v2/system/jobs').status_code == 200
    r = _post(auth_client, ROUTES[0], archive, {'Prefer': 'respond-async'})
    job_id = r.get_json()['data']['job']['id']
    finished.release()
    try:
        assert reached.wait(30)
        seen = auth_client.get(f'/api/v2/system/jobs/{job_id}')
        with app.app_context():
            row = store.job_row(db.session, job_id)
            db.session.remove()
    finally:
        release.set()
    assert runner.join_local(job_id, 60)
    assert seen.status_code == 200, seen.data
    data = seen.get_json()['data']
    assert row['state'] == 'running' and row['phase'] == restore_job.COMMITTED
    assert data['phase'] == row['phase']
    assert data['progress'] == {'done': row['progress_done'], 'total': row['progress_total']}
