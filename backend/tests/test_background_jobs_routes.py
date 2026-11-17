"""The job routes and a starting route's answer: unchanged within the bounded wait, 202 and a
Location past it, Prefer (RFC 7240), 409 naming the active job, permissions by job kind."""
import json
import threading
import time

import pytest

from models import db
from services import jobs
from services.audit_service import AuditService
from services.jobs import audit_verify, runner, store

pytestmark = pytest.mark.usefixtures('drop_new_users')
VERIFY = '/api/v2/audit/verify'
T = store.T


@pytest.fixture
def held(monkeypatch):
    """The verification held at its first progress until released."""
    reached, release = threading.Event(), threading.Event()
    real = runner.JobContext.progress

    def progress(ctx, *args, **kwargs):
        if not reached.is_set():
            reached.set()
            assert release.wait(15)
        return real(ctx, *args, **kwargs)
    monkeypatch.setattr(runner.JobContext, 'progress', progress)
    yield reached, release
    release.set()


@pytest.fixture
def cleanup(app):
    yield
    with app.app_context():
        for row in store.active_jobs(db.session):
            runner.join_local(row['id'], 15)
        for row in store.active_jobs(db.session):
            store.cancel_or_flag(db.session, row['id'], jobs._now())
        db.session.rollback()


def _login(app, user):
    client = app.test_client()
    r = client.post('/api/v2/auth/login', json={'username': user['username'],
                                                'password': 'TestPass123!'})
    assert r.status_code == 200, r.data
    return client


def test_a_verification_within_the_wait_answers_as_before(app, auth_client, cleanup):
    r = auth_client.get(VERIFY)
    assert r.status_code == 200
    body = r.get_json()
    with app.app_context():
        expected = AuditService.verify_integrity()
    assert set(body) == {'data', 'message'}
    assert body['message'] == audit_verify.message_for(expected)
    for key in ('status', 'valid', 'first_error_id', 'protection'):
        assert body['data'][key] == expected[key]
    assert 'Prefer' in r.headers.get('Vary', '')


def test_post_starts_a_verification_with_its_range(app, auth_client, cleanup):
    with app.app_context():
        AuditService.log_action(action='test_job_routes', details='one')
        last = AuditService.verify_integrity()['checked']
    r = auth_client.post(VERIFY, json={'start_id': 1, 'end_id': 2})
    assert r.status_code == 200, r.data
    assert r.get_json()['data']['checked'] <= 2 < last + 3


def test_past_the_wait_a_202_points_at_the_job(app, auth_client, held, cleanup, monkeypatch):
    monkeypatch.setattr(jobs, 'JOB_WAIT_SECONDS', 0.3)
    reached, release = held
    r = auth_client.get(VERIFY)
    assert r.status_code == 202, r.data
    job = r.get_json()['data']['job']
    assert r.headers['Location'] == f"/api/v2/system/jobs/{job['id']}"
    assert job['kind'] == 'audit_verify' and job['state'] in ('pending', 'running')
    assert 'result' not in job and 'Preference-Applied' not in r.headers
    assert reached.wait(5)
    # A second GET of the same range joins the running job instead of failing
    again = auth_client.get(VERIFY)
    assert again.status_code == 202 and again.get_json()['data']['job']['id'] == job['id']
    # POST, or another range, is refused while it runs: 409 naming it
    for refused in (auth_client.post(VERIFY, json={}), auth_client.get(f'{VERIFY}?start_id=5')):
        assert refused.status_code == 409, refused.data
        named = refused.get_json()['details']['job']
        assert named['id'] == job['id'] and named['kind'] == 'audit_verify'
        assert named['requested_by']['username'] == 'admin' and named['created_at']
    release.set()
    assert runner.join_local(job['id'], 15)
    done = auth_client.get(r.headers['Location']).get_json()['data']
    assert done['state'] == 'succeeded'
    assert done['result']['code'] == 200 and done['result']['data']['status'] in (
        'intact', 'broken', 'unprotected')


def test_prefer_respond_async_answers_202_at_once(app, auth_client, held, cleanup):
    reached, release = held
    started = time.monotonic()
    r = auth_client.get(VERIFY, headers={'Prefer': 'respond-async'})
    assert time.monotonic() - started < 3
    assert r.status_code == 202 and r.headers['Preference-Applied'] == 'respond-async'
    release.set()
    assert runner.join_local(r.get_json()['data']['job']['id'], 15)


def test_prefer_respond_async_answers_202_even_for_a_job_already_done(app, auth_client, cleanup,
                                                                     monkeypatch):
    def at_once(job_id):
        row = store.claim_job(db.session, job_id, 'test/1/x', jobs._now())
        runner.run_job(app, row, 'test/1/x')
    monkeypatch.setattr(runner, 'dispatch_job', at_once)
    r = auth_client.get(VERIFY, headers={'Prefer': 'respond-async'})
    assert r.status_code == 202 and r.headers['Preference-Applied'] == 'respond-async'
    assert r.get_json()['data']['job']['state'] == 'succeeded'
    assert auth_client.get(VERIFY).status_code == 200  # without the preference: as before


def test_prefer_wait_shortens_the_wait(app, auth_client, held, cleanup):
    reached, release = held
    started = time.monotonic()
    r = auth_client.get(VERIFY, headers={'Prefer': 'wait=1'})
    elapsed = time.monotonic() - started
    assert r.status_code == 202 and 0.9 <= elapsed < jobs.JOB_WAIT_SECONDS
    release.set()
    assert runner.join_local(r.get_json()['data']['job']['id'], 15)


def test_prefer_wait_never_exceeds_the_bound(monkeypatch):
    from api.v2.system import jobs as routes
    assert routes.parse_prefer(['respond-async, wait=600', 'handling=lenient']) == {
        'respond-async': True, 'wait': '600', 'handling': 'lenient'}
    assert routes.parse_prefer(['Respond-Async; foo=bar']) == {'respond-async': True}


def test_cancel_route_and_list(app, auth_client, held, cleanup, monkeypatch):
    monkeypatch.setattr(jobs, 'JOB_WAIT_SECONDS', 0.2)
    reached, release = held
    job_id = auth_client.get(VERIFY).get_json()['data']['job']['id']
    listed = auth_client.get('/api/v2/system/jobs?kind=audit_verify&state=active').get_json()['data']
    assert [j['id'] for j in listed] == [job_id]
    r = auth_client.post(f'/api/v2/system/jobs/{job_id}/cancel')
    assert r.status_code == 200 and r.get_json()['data']['cancel_requested']
    release.set()
    assert runner.join_local(job_id, 15)
    job = auth_client.get(f'/api/v2/system/jobs/{job_id}').get_json()['data']
    assert (job['state'], job['reason']) == ('cancelled', 'cancelled')
    assert auth_client.post(f'/api/v2/system/jobs/{job_id}/cancel').status_code == 409
    assert auth_client.get('/api/v2/system/jobs?state=nope').status_code == 400


def test_a_job_shows_no_secret_path_or_host(app, auth_client, cleanup):
    auth_client.get(VERIFY)
    job = auth_client.get('/api/v2/system/jobs?kind=audit_verify').get_json()['data'][0]
    full = auth_client.get(f"/api/v2/system/jobs/{job['id']}").get_json()['data']
    assert not {'secret', 'executor', 'node_id', 'file_name', 'requested_ip'} & set(full)


@pytest.mark.parametrize('role, verify, reads_verify, reads_backup', [
    ('auditor', 200, True, False),
    ('operator', 200, True, False),
    ('viewer', 403, False, False),
])
def test_permissions_follow_the_job_kind(app, auth_client, create_user, cleanup, monkeypatch,
                                         role, verify, reads_verify, reads_backup):
    fake = jobs.register(jobs.JobType(kind='test_route_backup', slot=jobs.SLOT_BACKUP,
                                      permission='admin:system', label='Fake backup',
                                      run=lambda ctx: jobs.JobOutcome(message='ok')))
    try:
        auth_client.get(VERIFY)
        verify_id = auth_client.get('/api/v2/system/jobs?kind=audit_verify').get_json()['data'][0]['id']
        with app.app_context():
            backup_id = jobs.start_job(fake.kind)
        assert runner.join_local(backup_id, 15)
        client = _login(app, create_user(role=role))
        assert client.get(VERIFY).status_code == verify
        for job_id, readable in ((verify_id, reads_verify), (backup_id, reads_backup)):
            assert client.get(f'/api/v2/system/jobs/{job_id}').status_code == (200 if readable else 404)
            assert client.post(f'/api/v2/system/jobs/{job_id}/cancel').status_code == (
                409 if readable else 404)
        kinds = {j['kind'] for j in client.get('/api/v2/system/jobs').get_json()['data']}
        assert ('audit_verify' in kinds) is reads_verify and fake.kind not in kinds
        admin_kinds = {j['kind'] for j in auth_client.get('/api/v2/system/jobs').get_json()['data']}
        assert fake.kind in admin_kinds
        with app.app_context():
            db.session.execute(T.delete().where(T.c.id == backup_id))
            db.session.commit()
    finally:
        jobs.unregister(fake.kind)


def test_a_failed_job_answers_a_fixed_message(app, auth_client, cleanup, monkeypatch):
    def boom(*a, **k):
        raise RuntimeError('/secret/path on host-1')
    monkeypatch.setattr(AuditService, 'verify_integrity', staticmethod(boom))
    r = auth_client.get(VERIFY)
    assert r.status_code == 500
    body = r.get_json()
    assert body['message'] == 'Audit chain verification failed'
    assert '/secret' not in json.dumps(body) and 'host-1' not in json.dumps(body)
    assert body['details']['job']['reason'] == 'error'


@pytest.fixture
def maintenance(app, monkeypatch):
    """HA on, this application's view in a manual maintenance, never read again."""
    from datetime import timedelta
    from config.settings import Config
    from services import cluster_maintenance as cm
    monkeypatch.setattr(Config, 'HA_MODE', True)
    monkeypatch.setattr(cm, 'OBSERVE_TTL_SECONDS', 3600)
    view = cm.view_of(app)
    from utils.datetime_utils import utc_now
    now = utc_now()
    view.set({'token': 'tok', 'reason': cm.REASON_MANUAL, 'phase': cm.PHASE_MANUAL,
              'started_at': now, 'expires_at': now + timedelta(minutes=5), 'restored_at': None,
              'node_id': 'node-x', 'actor': 'admin'}, now)
    yield view
    view.row, view.observed, view.process_started, view.deadline = None, None, None, 0.0


def _job_count(app):
    from sqlalchemy import func, select
    with app.app_context():
        found = db.session.execute(select(func.count()).select_from(T)).scalar()
        db.session.rollback()
    return found


@pytest.mark.parametrize('method', ['GET', 'POST'])
def test_no_job_starts_during_a_cluster_maintenance(app, auth_client, maintenance, cleanup, method):
    """GET and POST answer the same 503: no row written, a Retry-After, the reason said."""
    from services import cluster_maintenance as cm
    before = _job_count(app)
    r = auth_client.open(VERIFY, method=method, json={} if method == 'POST' else None)
    assert r.status_code == 503, r.data
    assert r.headers['Retry-After'] == str(cm.RETRY_AFTER_SECONDS)
    body = r.get_json()
    assert body['message'] == jobs.JobsSuspended.MESSAGE
    assert body['code'] == 'maintenance' and body['maintenance']['phase'] == cm.PHASE_MANUAL
    assert _job_count(app) == before


def test_start_job_refuses_before_any_write_during_a_maintenance(app, maintenance, cleanup):
    from services import cluster_maintenance as cm
    before = _job_count(app)
    with app.app_context():
        with pytest.raises(jobs.JobsSuspended):
            jobs.start_job(audit_verify.KIND)
        db.session.rollback()
    assert _job_count(app) == before
    # The maintenance's own writer still starts one; it concludes once the maintenance ends
    with app.app_context(), cm.exempt():
        job_id = jobs.start_job(audit_verify.KIND)
    maintenance.row = None
    assert runner.join_local(job_id, 15)
