"""The two manual backup routes as a background job: the answer of before within the bounded
wait, a 202 past it, the password encrypted until the take and never stored once generated,
409 on a held slot or backup lock, 503 during a cluster maintenance, a stop between two rows."""
import json
import threading

import pytest
from sqlalchemy import func, select

from config.settings import Config
from models import AuditLog, db
from services import jobs
from services.jobs import backup as backup_job
from services.jobs import runner, store

pytestmark = pytest.mark.usefixtures('drop_new_users')
SYSTEM, SETTINGS = '/api/v2/system/backup', '/api/v2/settings/backup/create'
PASSWORD = 'Route-Backup-Password-42'
T = store.T


@pytest.fixture
def backup_dir(app, tmp_path, monkeypatch):
    monkeypatch.setattr(Config, 'BACKUP_DIR', tmp_path, raising=False)
    monkeypatch.setattr(Config, 'HA_MODE', False, raising=False)
    return tmp_path


@pytest.fixture
def jobs_made(app):
    """Every backup job a test made is ended and removed."""
    with app.app_context():
        before = {r[0] for r in db.session.execute(select(T.c.id).where(T.c.kind == backup_job.KIND))}
        db.session.rollback()
    yield
    with app.app_context():
        made = [r[0] for r in db.session.execute(select(T.c.id).where(T.c.kind == backup_job.KIND))
                if r[0] not in before]
        db.session.rollback()
        for job_id in made:
            runner.join_local(job_id, 30)
            store.cancel_or_flag(db.session, job_id, jobs._now())
        db.session.execute(T.delete().where(T.c.id.in_(made or [''])))
        db.session.commit()


@pytest.fixture
def held(monkeypatch):
    """The backup run held at its first progress until released."""
    reached, release = threading.Event(), threading.Event()
    real = runner.JobContext.progress

    def progress(ctx, *args, **kwargs):
        if not reached.is_set():
            reached.set()
            assert release.wait(20)
        return real(ctx, *args, **kwargs)
    monkeypatch.setattr(runner.JobContext, 'progress', progress)
    yield reached, release
    release.set()


def _lines(app, success=None):
    with app.app_context():
        query = select(AuditLog).where(AuditLog.action == backup_job.ACTION)
        if success is not None:
            query = query.where(AuditLog.success.is_(success))
        rows = db.session.execute(query.order_by(AuditLog.id)).scalars().all()
        found = [(r.resource_name, r.details, r.success, r.username) for r in rows]
        db.session.rollback()
    return found


def _row(app, job_id):
    with app.app_context():
        row = store.job_row(db.session, job_id)
        db.session.rollback()
    return row


def _post(client, url, body=None, headers=None):
    return client.post(url, data=json.dumps(body or {}), content_type='application/json',
                       headers=headers or {})


def _job_id_of(app):
    with app.app_context():
        found = db.session.execute(select(T.c.id).where(T.c.kind == backup_job.KIND)
                                   .order_by(T.c.created_at.desc()).limit(1)).scalar()
        db.session.rollback()
    return found


@pytest.mark.parametrize('url', [SYSTEM, SETTINGS])
def test_a_backup_within_the_wait_answers_as_before(app, auth_client, backup_dir, jobs_made, url):
    before = len(_lines(app))
    r = _post(auth_client, url, {'password': PASSWORD})
    assert r.status_code == 200, r.data
    body = r.get_json()
    assert set(body) == {'data', 'message'} and body['message'] == 'Backup created successfully'
    data = body['data']
    assert set(data) == {'filename', 'size', 'size_bytes', 'download_url', 'warning'}
    path = backup_dir / data['filename']
    assert data['size_bytes'] == path.stat().st_size
    if url == SYSTEM:
        assert data['size'].endswith((' B', ' KB', ' MB'))
        assert data['download_url'] == f"/api/v2/system/backup/{data['filename']}/download"
    else:
        assert data['size'] == data['size_bytes']
        assert data['download_url'] == f"/api/v2/settings/backup/{data['filename']}/download"
    lines = _lines(app)[before:]
    assert lines == [(data['filename'], f"Created backup: {data['filename']}", True, 'admin')]
    row = _row(app, _job_id_of(app))
    assert (row['state'], row['reason'], row['secret']) == ('succeeded', 'done', None)
    assert row['progress_done'] == row['progress_total'] and row['phase'] == 'publishing'


def test_a_generated_password_is_answered_once_and_never_stored(app, auth_client, backup_dir,
                                                                jobs_made):
    r = _post(auth_client, SETTINGS, {})
    assert r.status_code == 200, r.data
    body = r.get_json()
    password = body['data']['password']
    assert body['data']['password_generated'] is True
    assert body['message'] == 'Backup created successfully - SAVE THE PASSWORD!'
    job_id = _job_id_of(app)
    row = _row(app, job_id)
    assert row['secret'] is None
    assert password not in json.dumps({k: str(v) for k, v in row.items()})
    shown = auth_client.get(f'/api/v2/system/jobs/{job_id}').get_json()['data']
    assert password not in json.dumps(shown) and 'password' not in shown['result']['data']
    from services.backup_service import BackupService
    blob = (backup_dir / body['data']['filename']).read_bytes()
    with app.app_context():
        assert 'metadata' in BackupService()._decrypt_framed(blob, password)[1]


@pytest.mark.parametrize('url', [SYSTEM, SETTINGS])
def test_past_the_wait_a_backup_answers_202_and_its_job_ends_with_the_answer(
        app, auth_client, backup_dir, jobs_made, held, url):
    reached, release = held
    r = _post(auth_client, url, {} if url == SETTINGS else {'password': PASSWORD},
              headers={'Prefer': 'respond-async'})
    assert r.status_code == 202, r.data
    job = r.get_json()['data']['job']
    assert r.headers['Location'] == f"/api/v2/system/jobs/{job['id']}"
    assert r.headers['Preference-Applied'] == 'respond-async'
    if url == SETTINGS:  # the generated password is in this answer, the only one
        assert r.get_json()['data']['password_generated'] is True
        assert len(r.get_json()['data']['password']) >= 16
    assert reached.wait(20)
    assert _row(app, job['id'])['secret'] is None  # cleared by the take
    release.set()
    assert runner.join_local(job['id'], 30)
    shown = auth_client.get(f"/api/v2/system/jobs/{job['id']}").get_json()['data']
    assert shown['state'] == 'succeeded'
    assert (backup_dir / shown['result']['data']['filename']).is_file()
    assert 'password' not in shown['result']['data']


def test_a_pending_backup_holds_its_password_encrypted(app, auth_client, backup_dir, jobs_made,
                                                       monkeypatch):
    from utils.encryption import decrypt_value
    monkeypatch.setattr(runner, 'dispatch_job', lambda job_id: None)  # no executor yet
    r = _post(auth_client, SYSTEM, {'password': PASSWORD}, headers={'Prefer': 'respond-async'})
    assert r.status_code == 202
    row = _row(app, r.get_json()['data']['job']['id'])
    assert row['secret'] not in (None, PASSWORD) and PASSWORD not in (row['params'] or '')
    with app.app_context():
        assert decrypt_value(row['secret']) == PASSWORD


def test_a_second_backup_is_refused_naming_the_first(app, auth_client, backup_dir, jobs_made,
                                                    monkeypatch):
    monkeypatch.setattr(runner, 'dispatch_job', lambda job_id: None)
    first = _post(auth_client, SYSTEM, {'password': PASSWORD}, headers={'Prefer': 'respond-async'})
    first_id = first.get_json()['data']['job']['id']
    before = len(_lines(app))
    for url in (SYSTEM, SETTINGS):
        r = _post(auth_client, url, {'password': PASSWORD})
        assert r.status_code == 409, r.data
        assert r.get_json()['details']['job']['id'] == first_id
    assert _lines(app)[before:] == [('manual', backup_job.BUSY, False, 'admin')] * 2


def test_a_held_backup_lock_fails_the_job_with_the_409_of_before(app, auth_client, backup_dir,
                                                                jobs_made, monkeypatch):
    """The scheduled backup's lock: the job waits a bounded time, then answers today's 409."""
    from services.backup.locking import BackupBusyError, backup_operation_lock
    monkeypatch.setattr(backup_job, 'LOCK_WAIT_SECONDS', 0.2)
    taken, release, refused = threading.Event(), threading.Event(), []

    def holder():
        with backup_operation_lock(timeout=0, purpose='a scheduled backup'):
            taken.set()
            release.wait(30)
    thread = threading.Thread(target=holder)
    thread.start()
    try:
        assert taken.wait(10)
        try:
            with backup_operation_lock(timeout=0.2, purpose='creating a backup'):
                pass
        except BackupBusyError as busy:
            refused.append(str(busy))
        before = len(_lines(app))
        r = _post(auth_client, SYSTEM, {'password': PASSWORD})
    finally:
        release.set()
        thread.join(10)
    assert r.status_code == 409, r.data
    assert r.get_json()['message'] == refused[0]
    assert _lines(app)[before:] == [('manual', backup_job.BUSY, False, 'admin')]
    row = _row(app, _job_id_of(app))
    assert (row['state'], row['reason']) == ('failed', 'refused')
    assert not list(backup_dir.glob('ucm_backup_*'))


def test_a_held_backup_lock_answers_409_within_the_route_wait(app, auth_client, backup_dir,
                                                              jobs_made):
    """Real constants: the job gives up on the lock before the route stops waiting for it."""
    from services.backup.locking import backup_operation_lock
    taken, release = threading.Event(), threading.Event()

    def holder():
        with backup_operation_lock(timeout=0, purpose='a scheduled backup'):
            taken.set()
            release.wait(60)
    thread = threading.Thread(target=holder)
    thread.start()
    try:
        assert taken.wait(10)
        r = _post(auth_client, SYSTEM, {'password': PASSWORD})
    finally:
        release.set()
        thread.join(10)
    assert r.status_code == 409, r.data
    row = _row(app, _job_id_of(app))
    assert (row['state'], row['reason']) == ('failed', 'refused')


def test_an_unexpected_failure_answers_as_before_and_is_an_error(app, auth_client, backup_dir,
                                                                jobs_made, monkeypatch):
    from services.backup_service import BackupService

    def fail(self, *args, **kwargs):
        raise RuntimeError('/internal/path on host-1')
    monkeypatch.setattr(BackupService, 'iter_backup', fail)
    r = _post(auth_client, SYSTEM, {'password': PASSWORD})
    assert r.status_code == 500
    assert r.get_json()['message'] == 'Backup failed' and 'details' not in r.get_json()
    row = _row(app, _job_id_of(app))
    assert (row['state'], row['reason']) == ('failed', 'error')
    assert b'/internal' not in r.data and b'host-1' not in r.data


@pytest.mark.parametrize('url,code,message,details', [
    (SYSTEM, 400, 'Invalid backup parameters', 'Backup refused: invalid parameters'),
    (SETTINGS, 500, 'Backup failed', 'Backup failed: unexpected error')])
def test_a_value_error_of_the_export_answers_each_route_as_before(
        app, auth_client, backup_dir, jobs_made, monkeypatch, url, code, message, details):
    from services.backup_service import BackupService

    def bad(self, *args, **kwargs):
        raise ValueError('bad parameter')
    monkeypatch.setattr(BackupService, 'iter_backup', bad)
    before = len(_lines(app))
    r = _post(auth_client, url, {'password': PASSWORD})
    assert r.status_code == code, r.data
    assert r.get_json()['message'] == message and 'details' not in r.get_json()
    assert _lines(app)[before:] == [('manual', details, False, 'admin')]


def test_a_cancellation_stops_the_export_between_two_rows(app, auth_client, backup_dir, jobs_made,
                                                          monkeypatch):
    """Asked inside a section, it is seen before the next section starts: nothing published."""
    monkeypatch.setattr(backup_job, 'CHECK_SECONDS', 0)
    steps, checks = [], []
    real_progress, real_check = runner.JobContext.progress, runner.JobContext.check

    def progress(ctx, done=None, total=None, phase=None):
        if done is not None or total is not None or phase is not None:
            steps.append(done)
        return real_progress(ctx, done=done, total=total, phase=phase)

    def check(ctx):
        if not checks:
            with app.app_context(), db.engine.begin() as conn:
                conn.execute(T.update().where(T.c.id == ctx.job_id).values(cancel_requested=True))
        checks.append(len(steps))
        return real_check(ctx)
    monkeypatch.setattr(runner.JobContext, 'progress', progress)
    monkeypatch.setattr(runner.JobContext, 'check', check)
    r = _post(auth_client, SYSTEM, {'password': PASSWORD})
    assert r.status_code == 409, r.data
    assert len(checks) == 1 and len(steps) == checks[0]  # no section step after the check
    row = _row(app, _job_id_of(app))
    assert (row['state'], row['reason']) == ('cancelled', 'cancelled')
    assert row['progress_done'] < row['progress_total']
    assert not list(backup_dir.glob('ucm_backup_*')) and not list(backup_dir.glob('.ucm_backup_*.tmp'))


@pytest.fixture
def maintenance(app, monkeypatch):
    """HA on, this application's view in a manual maintenance."""
    from datetime import timedelta
    from services import cluster_maintenance as cm
    from utils.datetime_utils import utc_now
    monkeypatch.setattr(Config, 'HA_MODE', True)
    monkeypatch.setattr(cm, 'OBSERVE_TTL_SECONDS', 3600)
    view = cm.view_of(app)
    now = utc_now()
    view.set({'token': 'tok', 'reason': cm.REASON_MANUAL, 'phase': cm.PHASE_MANUAL,
              'started_at': now, 'expires_at': now + timedelta(minutes=5), 'restored_at': None,
              'node_id': 'node-x', 'actor': 'admin'}, now)
    yield view
    view.row, view.observed, view.process_started, view.deadline = None, None, None, 0.0


@pytest.mark.parametrize('url', [SYSTEM, SETTINGS])
def test_no_backup_starts_during_a_cluster_maintenance(app, auth_client, jobs_made, maintenance, url):
    from services import cluster_maintenance as cm
    with app.app_context():
        count = select(func.count()).select_from(T)
        before = db.session.execute(count).scalar()
        db.session.rollback()
    lines = len(_lines(app))
    r = _post(auth_client, url, {'password': PASSWORD})
    assert r.status_code == 503, r.data
    assert r.headers['Retry-After'] == str(cm.RETRY_AFTER_SECONDS)
    assert r.get_json()['message'] == jobs.JobsSuspended.MESSAGE
    with app.app_context():
        assert db.session.execute(count).scalar() == before
        db.session.rollback()
    assert len(_lines(app)) == lines


@pytest.mark.parametrize('url,body', [(SYSTEM, {}), (SYSTEM, {'password': 'short'}),
                                      (SYSTEM, {'password': PASSWORD, 'kdf': 'bogus'}),
                                      (SETTINGS, {'password': 'short'}),
                                      (SETTINGS, {'password': PASSWORD, 'kdf': 'bogus'})])
def test_an_invalid_backup_request_during_a_maintenance_is_refused_first(
        app, auth_client, jobs_made, maintenance, url, body, caplog):
    from services import cluster_maintenance as cm
    lines = len(_lines(app))
    r = _post(auth_client, url, body)
    assert r.status_code == 503, r.data
    assert r.headers['Retry-After'] == str(cm.RETRY_AFTER_SECONDS)
    assert r.get_json()['message'] == jobs.JobsSuspended.MESSAGE
    assert 'lost entry' not in caplog.text
    assert len(_lines(app)) == lines


def test_a_backup_job_is_read_with_admin_system_only(app, auth_client, create_user, backup_dir,
                                                    jobs_made):
    r = _post(auth_client, SYSTEM, {'password': PASSWORD})
    assert r.status_code == 200
    job_id = _job_id_of(app)
    user = create_user(role='operator')
    client = app.test_client()
    assert client.post('/api/v2/auth/login', json={'username': user['username'],
                                                   'password': 'TestPass123!'}).status_code == 200
    assert client.get(f'/api/v2/system/jobs/{job_id}').status_code == 404
    assert client.post(f'/api/v2/system/jobs/{job_id}/cancel').status_code == 404
    kinds = {j['kind'] for j in client.get('/api/v2/system/jobs').get_json()['data']}
    assert backup_job.KIND not in kinds
    assert auth_client.get(f'/api/v2/system/jobs/{job_id}').status_code == 200
