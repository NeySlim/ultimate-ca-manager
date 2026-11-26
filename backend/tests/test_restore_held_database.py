"""SQLite: while a restore's transaction holds the database, the web worker never waits on it.

A second sqlite3 connection really holds the database file (BEGIN EXCLUSIVE), as the restore's
transaction does once it has written enough: the job's read and its cancellation answer from
the local state for a caller checked during the restore, anything else answers 503 with
Retry-After at once, and no request waits in sqlite3's own busy handler. A job whose progress
or conclusion crosses another writer ends with its own outcome, never executor_lost.
"""
import contextlib
import json
import sqlite3
import threading
import time
import types
import uuid

import pytest
from flask import g
from sqlalchemy import update

from models import BackgroundJob, User, db
from services import cluster_maintenance, jobs
from services.jobs import JobOutcome, JobType, runner, store
from services.jobs import restore as restore_job
from tests.test_restore_job import archive, created, no_restart  # noqa: F401 (fixtures)

T = BackgroundJob.__table__
PASSWORD = 'Held-Database-Pass-9'
# A request the worker serves while the database is held answers well under this
FAST = 1.0


def _on_sqlite(app):
    with app.app_context():
        return db.engine.dialect.name == 'sqlite'


@contextlib.contextmanager
def file_database(app, path, **engine_options):
    """The session database copied to a file the app opens with the product's engine options
    (one connection per checkout, sqlite3's default 5 s busy timeout)."""
    from sqlalchemy import create_engine
    with app.app_context():
        db.session.commit()
        db.session.remove()
        engines = db._app_engines[app]
        memory = engines[None]
        raw = memory.raw_connection()
        try:
            target = sqlite3.connect(path)
            raw.driver_connection.backup(target)
            target.close()
        finally:
            raw.close()
        engines[None] = create_engine(f'sqlite:///{path}', hide_parameters=True,
                                      **engine_options)
        cluster_maintenance.install_engine_guard(app, engines[None])
    try:
        yield
    finally:
        with app.app_context():
            db.session.remove()
            engines[None].dispose()
            engines[None] = memory


@contextlib.contextmanager
def holding(path):
    """Another connection holds the database file exclusively: no reader, no writer."""
    holder = sqlite3.connect(path, timeout=0, isolation_level=None)
    holder.execute('BEGIN EXCLUSIVE')
    try:
        yield
    finally:
        holder.execute('ROLLBACK')
        holder.close()


@pytest.fixture
def held_app(app, tmp_path):
    if not _on_sqlite(app):
        pytest.skip('SQLite: the database file held by another connection')
    path = str(tmp_path / 'held.db')
    with file_database(app, path):
        yield app, path


def _admin_user(app):
    with app.app_context():
        user = User(username=f'held-{uuid.uuid4().hex[:8]}', role='admin',
                    email=f'{uuid.uuid4().hex[:8]}@example.test')
        user.set_password(PASSWORD)
        db.session.add(user)
        db.session.commit()
        info = {'id': user.id, 'username': user.username}
        db.session.remove()
    return info


def _client(app, username, password=PASSWORD):
    c = app.test_client()
    r = c.post('/api/v2/auth/login', data=json.dumps({'username': username, 'password': password}),
               content_type='application/json')
    assert r.status_code == 200, r.data
    return c


def _restore_job(app):
    """A running restore taken by an executor that is not this test."""
    with app.app_context():
        jt = jobs.job_type(restore_job.KIND)
        job_id = store.create_job(db.session, kind=restore_job.KIND, slot=jt.slot, exclusive=True,
                                  exclusive_slots=jobs.EXCLUSIVE_SLOTS, now=jobs._now())
        assert store.claim_job(db.session, job_id, 'elsewhere/1/x', jobs._now()) is not None
        db.session.remove()
    return job_id


def _gate(app, job_id):
    ctx = types.SimpleNamespace(job_id=job_id, node_id=None, requested_by='admin', app=app,
                                view={'id': job_id, 'kind': restore_job.KIND, 'state': 'running',
                                      'phase': restore_job.CHECKING})
    return restore_job.LocalGate(app, ctx)


@pytest.fixture
def restore_held(held_app):
    """A restore whose gate is up; ``hold()`` then marks its transaction as holding the file."""
    app, path = held_app
    job_id = _restore_job(app)
    admin = _client(app, 'admin', 'changeme123')  # a login is a write: before the gate
    gate = _gate(app, job_id).raise_gate()
    state = types.SimpleNamespace(app=app, path=path, job_id=job_id, gate=gate, admin=admin)

    @contextlib.contextmanager
    def hold():
        gate.set_view(phase=restore_job.APPLYING, held=True)
        with holding(path):
            yield
    state.hold = hold
    try:
        yield state
    finally:
        gate.lift()
        store.purge_file(store.file_name_for(job_id, restore_job.CANCEL_SUFFIX))
        with app.app_context():
            db.session.execute(T.delete().where(T.c.id == job_id))
            db.session.commit()
            db.session.remove()


def _timed(call, *args, **kwargs):
    started = time.monotonic()
    response = call(*args, **kwargs)
    return response, time.monotonic() - started


def test_the_job_is_read_and_cancelled_while_the_transaction_holds_the_database(restore_held):
    job_id, admin = restore_held.job_id, restore_held.admin
    url = f'/api/v2/system/jobs/{job_id}'
    # Checked against the database once the restore began
    assert admin.get(url).status_code == 200
    with restore_held.hold():
        seen, took = _timed(admin.get, url)
        assert seen.status_code == 200, seen.data
        assert took < FAST, f'the job read waited {took:.1f}s on the held database'
        data = seen.get_json()['data']
        assert data['id'] == job_id and data['phase'] == restore_job.APPLYING
        assert 'held' not in data
        cancelled, took = _timed(admin.post, f'{url}/cancel')
        assert cancelled.status_code == 200, cancelled.data
        assert took < FAST
        assert cancelled.get_json()['data']['cancel_requested'] is True
    assert restore_job.cancel_flagged(job_id), 'the cancellation was not taken'


def test_an_ordinary_request_answers_503_with_retry_after_at_once(restore_held):
    app, admin = restore_held.app, restore_held.admin
    assert admin.get('/api/v2/groups').status_code == 200
    with restore_held.hold():
        refused, took = _timed(admin.get, '/api/v2/groups')
        live, live_took = _timed(admin.get, '/health/live')
        anonymous, anonymous_took = _timed(app.test_client().get, '/api/v2/cas')
    assert refused.status_code == 503, refused.data
    assert refused.headers['Retry-After'] == str(cluster_maintenance.RETRY_AFTER_SECONDS)
    assert took < FAST, f'the refusal took {took:.1f}s'
    assert anonymous.status_code == 503 and anonymous_took < FAST
    assert live.status_code == 200 and live_took < FAST


def test_revocation_status_answers_try_later_or_503_at_once(restore_held):
    """OCSP says tryLater (RFC 6960 section 2.3); a CRL answers 503 with Retry-After."""
    from cryptography.x509 import ocsp
    client = restore_held.app.test_client()
    with restore_held.hold():
        status, took = _timed(client.post, '/ocsp', data=b'0', content_type='application/ocsp-request')
        crl, crl_took = _timed(client.get, '/cdp/held-test.crl')
    assert status.status_code == 200 and took < FAST
    assert status.headers['Content-Type'] == 'application/ocsp-response'
    assert ocsp.load_der_ocsp_response(status.data).response_status == \
        ocsp.OCSPResponseStatus.TRY_LATER
    assert crl.status_code == 503 and crl.headers['Retry-After'] and crl_took < FAST


def test_the_web_workers_own_threads_never_wait_in_sqlite(restore_held, monkeypatch):
    """A thread of the web worker outside any request (the WebSocket relay reader, a cache
    timer) fails at once on the held database instead of stopping the worker for 5 s."""
    from sqlalchemy import text
    from sqlalchemy.exc import OperationalError
    from utils import sqlite_wait
    app = restore_held.app
    monkeypatch.setattr(sqlite_wait, '_WEB_WORKER', [app])
    with app.app_context():
        engine = db.engine
    outcome = {}

    def read():
        started = time.monotonic()
        try:
            with engine.connect() as conn:
                conn.execute(text('SELECT COUNT(*) FROM users')).scalar()
            outcome['error'] = None
        except OperationalError as e:
            outcome['error'] = e
        outcome['took'] = time.monotonic() - started
    with restore_held.hold():
        thread = threading.Thread(target=read)
        thread.start()
        thread.join(30)
    assert outcome['error'] is not None and sqlite_wait.is_locked(outcome['error'])
    assert outcome['took'] < FAST, f"the thread waited {outcome['took']:.1f}s in sqlite3"


def test_a_request_in_the_window_never_waits_in_sqlite(restore_held):
    """Before the transaction is marked as holding the file, a request that meets the lock
    retries in Python, a yield between tries, and is refused 503 within a bound."""
    app, admin = restore_held.app, restore_held.admin
    assert admin.get('/api/v2/groups').status_code == 200
    with holding(restore_held.path):
        refused, took = _timed(admin.get, '/api/v2/groups')
    assert refused.status_code == 503, refused.data
    assert refused.headers['Retry-After']
    assert took < 2.0, f"the request waited {took:.1f}s"


@pytest.fixture
def busy_app(app, tmp_path):
    """The file database with a short busy timeout: a lock outlasts it at once."""
    if not _on_sqlite(app):
        pytest.skip('SQLite: the database file locked by another writer')
    path = str(tmp_path / 'busy.db')
    with file_database(app, path, connect_args={'timeout': 0.3}):
        yield app, path


@contextlib.contextmanager
def writing(path):
    """Another connection in the middle of a write: readers read, no other writer writes."""
    writer = sqlite3.connect(path, timeout=0, isolation_level=None)
    writer.execute('BEGIN IMMEDIATE')
    writer.execute("UPDATE system_config SET value = value WHERE key = 'none'")
    try:
        yield
    finally:
        writer.execute('ROLLBACK')
        writer.close()


def test_a_login_that_meets_another_writer_answers_503_not_500(busy_app):
    """The route catches the lock itself ('Failed to record login attempt'): still a 503."""
    app, path = busy_app
    user = _admin_user(app)
    body = json.dumps({'username': user['username'], 'password': PASSWORD})
    with writing(path):
        refused = app.test_client().post('/api/v2/auth/login', data=body,
                                         content_type='application/json')
    assert refused.status_code == 503, refused.data
    assert refused.headers['Retry-After']
    assert refused.mimetype == 'application/problem+json'
    # The writer gone, the same login goes through
    again = app.test_client().post('/api/v2/auth/login', data=body,
                                   content_type='application/json')
    assert again.status_code == 200, again.data


def test_a_500_that_met_no_lock_stays_a_500(busy_app, monkeypatch):
    """Guard: only a request that met a lock is turned into a 503."""
    app, _ = busy_app
    user = _admin_user(app)
    body = json.dumps({'username': user['username'], 'password': PASSWORD})

    def broken(self, *a, **k):
        raise RuntimeError('not a lock')
    monkeypatch.setattr(User, 'reserve_login_attempt', broken)
    failed = app.test_client().post('/api/v2/auth/login', data=body,
                                    content_type='application/json')
    assert failed.status_code == 500, failed.data


def test_a_session_revoked_before_the_restore_reads_nothing(held_app):
    app, path = held_app
    job_id = _restore_job(app)
    url = f'/api/v2/system/jobs/{job_id}'
    user = _admin_user(app)
    revoked = _client(app, user['username'])
    assert revoked.get(url).status_code == 200
    # Its sessions closed before the restore: refused during it, held database or not
    with app.app_context():
        db.session.execute(update(User).where(User.id == user['id']).values(
            session_version=User.session_version + 1))
        db.session.commit()
        db.session.remove()
    gate = _gate(app, job_id).raise_gate()
    try:
        assert revoked.get('/api/v2/groups').status_code == 401
        gate.set_view(phase=restore_job.APPLYING, held=True)
        with holding(path):
            anonymous = app.test_client().get(url)
            stale = revoked.get(url)
            stale_cancel = revoked.post(f'{url}/cancel')
    finally:
        gate.lift()
        with app.app_context():
            db.session.execute(T.delete().where(T.c.id == job_id))
            db.session.commit()
    assert anonymous.status_code == 401, anonymous.data
    assert stale.status_code in (401, 503) and stale.status_code != 200, stale.data
    assert stale_cancel.status_code in (401, 503), stale_cancel.data
    assert not restore_job.cancel_flagged(job_id)


def test_a_session_checked_before_the_restore_only_is_not_trusted(held_app):
    """A check made before the gate went up may predate a revocation: refused, not answered."""
    app, path = held_app
    job_id = _restore_job(app)
    user = _admin_user(app)
    before = _client(app, user['username'])
    url = f'/api/v2/system/jobs/{job_id}'
    assert before.get(url).status_code == 200
    gate = _gate(app, job_id).raise_gate()
    try:
        gate.set_view(phase=restore_job.APPLYING, held=True)
        with holding(path):
            seen = before.get(url)
            cancel = before.post(f'{url}/cancel')
    finally:
        gate.lift()
        with app.app_context():
            db.session.execute(T.delete().where(T.c.id == job_id))
            db.session.commit()
    assert seen.status_code == 503, seen.data
    assert seen.headers['Retry-After']
    assert cancel.status_code == 503
    assert not restore_job.cancel_flagged(job_id)


def _api_key(app, user_id, lifetime):
    from datetime import timedelta
    from auth.unified import AuthManager
    from utils.datetime_utils import utc_now
    with app.app_context():
        made = AuthManager().create_api_key(user_id, f'held-{uuid.uuid4().hex[:6]}', ['*'],
                                            not_after=utc_now() + timedelta(seconds=lifetime))
        db.session.remove()
    return made['key']


def test_an_api_key_that_expires_during_the_restore_reads_nothing(held_app):
    """Checked during the gate, then expired: the held window refuses it as the database would."""
    app, path = held_app
    job_id = _restore_job(app)
    url = f'/api/v2/system/jobs/{job_id}'
    user = _admin_user(app)
    lifetime = 2.0
    made_at = time.monotonic()
    key = _api_key(app, user['id'], lifetime)
    lasting = _api_key(app, user['id'], 3600)
    client = app.test_client()
    gate = _gate(app, job_id).raise_gate()
    try:
        assert client.get(url, headers={'X-API-Key': key}).status_code == 200
        assert client.get(url, headers={'X-API-Key': lasting}).status_code == 200
        time.sleep(max(0.0, lifetime + 0.5 - (time.monotonic() - made_at)))
        gate.set_view(phase=restore_job.APPLYING, held=True)
        with holding(path):
            expired = client.get(url, headers={'X-API-Key': key})
            expired_cancel = client.post(f'{url}/cancel', headers={'X-API-Key': key})
            still = client.get(url, headers={'X-API-Key': lasting})
    finally:
        gate.lift()
        with app.app_context():
            db.session.execute(T.delete().where(T.c.id == job_id))
            db.session.commit()
    assert still.status_code == 200, still.data
    assert expired.status_code == 401, expired.data
    assert expired_cancel.status_code == 401, expired_cancel.data
    assert not restore_job.cancel_flagged(job_id)


def test_a_credential_refused_during_the_gate_is_forgotten(held_app):
    """Checked, then refused by the database during the same gate: never answered from memory."""
    app, path = held_app
    job_id = _restore_job(app)
    url = f'/api/v2/system/jobs/{job_id}'
    user = _admin_user(app)
    key = _api_key(app, user['id'], 3600)
    client = app.test_client()
    gate = _gate(app, job_id).raise_gate()
    try:
        assert client.get(url, headers={'X-API-Key': key}).status_code == 200
        # Revoked by a writer the gate does not see (another process on the file)
        other = sqlite3.connect(path)
        other.execute('UPDATE api_keys SET is_active = 0 WHERE user_id = ?', (user['id'],))
        other.commit()
        other.close()
        assert client.get(url, headers={'X-API-Key': key}).status_code == 401
        gate.set_view(phase=restore_job.APPLYING, held=True)
        with holding(path):
            seen = client.get(url, headers={'X-API-Key': key})
            cancel = client.post(f'{url}/cancel', headers={'X-API-Key': key})
    finally:
        gate.lift()
        with app.app_context():
            db.session.execute(T.delete().where(T.c.id == job_id))
            db.session.commit()
    assert seen.status_code == 503, seen.data
    assert cancel.status_code == 503, cancel.data
    assert not restore_job.cancel_flagged(job_id)


def test_a_check_made_during_a_previous_restore_is_not_used(held_app):
    """Two restores one after the other: a check from the first one's gate never serves the
    second, whatever the memory kept between them."""
    app, path = held_app
    first, second = _restore_job(app), None
    user = _admin_user(app)
    client = _client(app, user['username'])
    gate = _gate(app, first).raise_gate()
    try:
        assert client.get(f'/api/v2/system/jobs/{first}').status_code == 200
    finally:
        gate.lift()
    with app.app_context():
        db.session.execute(T.delete().where(T.c.id == first))
        db.session.commit()
        db.session.remove()
    second = _restore_job(app)
    url = f'/api/v2/system/jobs/{second}'
    gate = _gate(app, second).raise_gate()
    try:
        gate.set_view(phase=restore_job.APPLYING, held=True)
        with holding(path):
            seen = client.get(url)
            cancel = client.post(f'{url}/cancel')
    finally:
        gate.lift()
        with app.app_context():
            db.session.execute(T.delete().where(T.c.id == second))
            db.session.commit()
    assert seen.status_code == 503, seen.data
    assert cancel.status_code == 503, cancel.data
    assert not restore_job.cancel_flagged(second)


def test_a_session_without_the_right_reads_nothing(restore_held, viewer_client):
    app, job_id = restore_held.app, restore_held.job_id
    url = f'/api/v2/system/jobs/{job_id}'
    assert viewer_client.get('/api/v2/system/jobs').status_code == 200  # checked during the gate
    assert viewer_client.get(url).status_code == 404
    with restore_held.hold():
        seen = viewer_client.get(url)
        cancel = viewer_client.post(f'{url}/cancel')
    assert seen.status_code == 404, seen.data
    assert cancel.status_code == 404, cancel.data
    assert not restore_job.cancel_flagged(job_id)


def test_a_held_cancellation_still_needs_its_csrf_token(restore_held, monkeypatch):
    job_id, admin = restore_held.job_id, restore_held.admin
    url = f'/api/v2/system/jobs/{job_id}'
    assert admin.get(url).status_code == 200
    monkeypatch.setenv('CSRF_DISABLED', 'false')
    with restore_held.hold():
        forged = admin.post(f'{url}/cancel')
    assert forged.status_code == 403, forged.data
    assert not restore_job.cancel_flagged(job_id)


def test_a_check_made_on_one_host_is_not_used_on_another(restore_held):
    """The public-host rules ran for the host of the check, not for this one."""
    job_id, admin = restore_held.job_id, restore_held.admin
    url = f'/api/v2/system/jobs/{job_id}'
    assert admin.get(url).status_code == 200
    other = restore_held.app.test_client()
    other.set_cookie('session', admin.get_cookie('session').value, domain='acme.elsewhere.test')
    with restore_held.hold():
        here = admin.get(url)
        elsewhere = other.get(url, base_url='http://acme.elsewhere.test')
    assert here.status_code == 200, here.data
    assert elsewhere.status_code == 503, elsewhere.data


@contextlib.contextmanager
def lock_waits(app, monkeypatch):
    """What each statement and request of the block did with a lock, as the product counts it:
    statements as (waited in Python, sqlite3 busy timeout in ms), requests as seconds on locks."""
    from flask import g, request_tearing_down
    from utils import sqlite_wait
    seen = types.SimpleNamespace(statements=[], requests=[])
    real = sqlite_wait._execute

    def recording(cursor, statement, parameters, context, many=False):
        info = context.root_connection.connection.info if context is not None else {}
        handled = True
        try:
            handled = real(cursor, statement, parameters, context, many) is not None
            return handled
        finally:
            seen.statements.append((handled, info.get(sqlite_wait._BUSY_INFO)))

    def ended(sender, **extra):
        seen.requests.append(g.get(sqlite_wait._WAITED, 0.0))
    monkeypatch.setattr(sqlite_wait, '_execute', recording)
    request_tearing_down.connect(ended, app)
    try:
        yield seen
    finally:
        request_tearing_down.disconnect(ended, app)


def test_a_cancellation_on_a_locked_database_before_the_mark_is_taken(restore_held, monkeypatch):
    """The gate is up, the transaction not yet marked as holding, and the database locked
    (the restore reading its archive writes): the flag file takes the cancellation, and no
    request waits in sqlite3's own busy handler, only the gate's short wait in Python."""
    from utils import sqlite_wait
    job_id, admin = restore_held.job_id, restore_held.admin
    url = f'/api/v2/system/jobs/{job_id}'
    assert admin.get(url).status_code == 200
    restore_held.gate.set_view(phase=restore_job.READING)
    with holding(restore_held.path), lock_waits(restore_held.app, monkeypatch) as waits:
        seen = admin.get(url)
        cancelled = admin.post(f'{url}/cancel')
    assert seen.status_code == 200, seen.data
    assert seen.get_json()['data']['phase'] == restore_job.READING
    assert cancelled.status_code == 200, cancelled.data
    assert restore_job.cancel_flagged(job_id), 'the cancellation was not taken'
    # Counted, not timed: a loaded host stretches the wall clock, never these
    assert waits.statements and all(handled and timeout == sqlite_wait.IN_C_MS
                                    for handled, timeout in waits.statements), waits.statements
    assert len(waits.requests) == 2 and all(w < sqlite_wait.WEB_LOCK_WAIT_SECONDS for w in waits.requests), waits.requests


def test_a_cancellation_at_the_commit_is_too_late(restore_held):
    job_id, admin = restore_held.job_id, restore_held.admin
    url = f'/api/v2/system/jobs/{job_id}'
    assert admin.get(url).status_code == 200
    with restore_held.hold():
        restore_held.gate.set_view(phase=restore_job.COMMITTING)
        late = admin.post(f'{url}/cancel')
    assert late.status_code == 409, late.data
    assert not restore_job.cancel_flagged(job_id)


def test_the_held_mark_drops_once_the_transaction_ends(app, archive, created, no_restart,
                                                       monkeypatch):
    """The worker reads the database again as soon as the restore's transaction is over."""
    from tests.test_restore_job import _assert_final, _lines_in, _start
    views, at_end_steps = [], []
    real_set, real_finish = restore_job.LocalGate.set_view, restore_job._finish_steps

    def set_view(gate, **view):
        if 'held' in view:
            views.append(view['held'])
        return real_set(gate, **view)

    def finish_steps(job_id):
        at_end_steps.append((restore_job.read_state() or {}).get('view', {}).get('held'))
        return real_finish(job_id)
    monkeypatch.setattr(restore_job.LocalGate, 'set_view', set_view)
    monkeypatch.setattr(restore_job, '_finish_steps', finish_steps)
    before = _lines_in(app)
    job_id, name = _start(app, archive, created)
    _assert_final(app, job_id, 'succeeded', 'done', before, name, True)
    if _on_sqlite(app):
        assert True in views, 'the transaction never said it holds the database'
    else:
        assert True not in views
    # The end steps run with the database free: the worker serves it again from the commit
    assert at_end_steps == [False], at_end_steps


# -- a job's own writes wait for another writer -------------------------------------------

HOLD_SECONDS = 7  # past sqlite3's 5 s busy timeout


def _holder_thread(path, seconds):
    taken = threading.Event()

    def hold():
        with holding(path):
            taken.set()
            time.sleep(seconds)
    thread = threading.Thread(target=hold, name='other-writer', daemon=True)
    thread.start()
    assert taken.wait(10)
    return thread


@pytest.fixture
def crossing_job(held_app):
    app, path = held_app
    kind = f'test_crossing_{uuid.uuid4().hex[:6]}'
    behaviour = {}

    def run(ctx):
        behaviour['run'](ctx, path)
        return JobOutcome(code=200, message='Crossing done', data={'ok': True},
                          audit_details='Crossing job finished')
    jobs.register(JobType(kind=kind, slot=jobs.SLOT_BACKUP, permission='admin:system', run=run,
                          label='Crossing', audit_action='test_crossing_job'))
    ids = []

    def start():
        with app.test_request_context():
            g.current_user = types.SimpleNamespace(id=4545, username='crossing-requester')
            g.user_id = 4545
            job_id = jobs.start_job(kind)
        ids.append(job_id)
        return job_id
    try:
        yield types.SimpleNamespace(app=app, behaviour=behaviour, start=start)
    finally:
        jobs.unregister(kind)
        with app.app_context():
            for job_id in ids:
                runner.join_local(job_id, 30)
            db.session.execute(T.delete().where(T.c.id.in_(ids)))
            db.session.commit()


def _final(app, job_id):
    assert runner.join_local(job_id, 60)
    with app.app_context():
        executor = store.job_row(db.session, job_id)['executor']
        # What the scheduler's next pass does with a job whose thread is gone
        store.recover_orphans(db.session, now=jobs._now(), all_running=False,
                              audit_for=jobs.audit_writer, mine={job_id: executor})
        row = store.job_row(db.session, job_id)
        db.session.remove()
    return row


def test_a_conclusion_that_crosses_another_writer_keeps_the_jobs_outcome(crossing_job):
    holders = []
    crossing_job.behaviour['run'] = lambda ctx, path: holders.append(
        _holder_thread(path, HOLD_SECONDS))
    job_id = crossing_job.start()
    row = _final(crossing_job.app, job_id)
    assert (row['state'], row['reason']) == ('succeeded', 'done'), row
    for thread in holders:
        thread.join(30)


def test_a_progress_that_crosses_another_writer_keeps_the_jobs_outcome(crossing_job):
    holders = []

    def run(ctx, path):
        holders.append(_holder_thread(path, HOLD_SECONDS))
        ctx.progress(done=1, total=2, phase='working')
        holders[-1].join(30)
    crossing_job.behaviour['run'] = run
    job_id = crossing_job.start()
    row = _final(crossing_job.app, job_id)
    assert (row['state'], row['reason']) == ('succeeded', 'done'), row
    assert row['progress_done'] == 1


def test_a_lock_held_past_the_jobs_wait_still_concludes_it_as_its_error(crossing_job, monkeypatch):
    """Guard on the bound: past the wait the write raises like any other database error.
    Without the wait it passes too (sqlite3's own timeout); it fails when the wait never ends."""
    monkeypatch.setattr(runner, 'JOB_LOCK_WAIT_SECONDS', 0.5)

    def run(ctx, path):
        thread = _holder_thread(path, 6)
        try:
            ctx.progress(done=1)
        finally:
            thread.join(30)
    crossing_job.behaviour['run'] = run
    job_id = crossing_job.start()
    row = _final(crossing_job.app, job_id)
    assert (row['state'], row['reason']) == ('failed', 'error'), row


def test_no_hsts_header_while_its_setting_cannot_be_read(restore_held, monkeypatch):
    """hsts_enabled=false in the database: a 503 of the held window sends no HSTS either."""
    for var in ('UCM_HSTS_ENABLED', 'ucm_hsts_enabled'):
        monkeypatch.delenv(var, raising=False)
    app, path = restore_held.app, restore_held.path
    other = sqlite3.connect(path)  # written outside the gate's guard, as before the restore
    other.execute("DELETE FROM system_config WHERE key = 'hsts_enabled'")
    other.execute("INSERT INTO system_config (key, value) VALUES ('hsts_enabled', 'false')")
    other.commit()
    other.close()
    try:
        with restore_held.hold():
            refused = restore_held.admin.get('/api/v2/groups')
        assert refused.status_code == 503, refused.data
        assert 'Strict-Transport-Security' not in refused.headers
    finally:
        other = sqlite3.connect(path)
        other.execute("DELETE FROM system_config WHERE key = 'hsts_enabled'")
        other.commit()
        other.close()


def test_an_untrusted_forwarded_host_is_refused_while_held(restore_held, monkeypatch):
    """The direct client's X-Forwarded-Host gets the same 403 as when the database answers."""
    monkeypatch.delenv('UCM_TRUSTED_PROXIES', raising=False)
    app, job_id, admin = restore_held.app, restore_held.job_id, restore_held.admin
    url = f'/api/v2/system/jobs/{job_id}'
    assert admin.get(url).status_code == 200
    monkeypatch.setitem(app.config, 'TRUSTED_PROXY_HOPS', 1)
    spoofed = {'headers': {'X-Forwarded-Host': 'localhost'},
               'environ_overrides': {'REMOTE_ADDR': '203.0.113.1'}}
    assert admin.get(url, **spoofed).status_code == 403
    with restore_held.hold():
        seen = admin.get(url, **spoofed)
        cancel = admin.post(f'{url}/cancel', **spoofed)
        plain = admin.get(url)
    assert seen.status_code == 403, seen.data
    assert cancel.status_code == 403, cancel.data
    assert plain.status_code == 200, plain.data
    assert not restore_job.cancel_flagged(job_id)



@pytest.mark.parametrize('per_user', [2, 100], ids=['own-share', 'memory-full'])
def test_one_account_cannot_evict_another_from_the_held_memory(held_app, monkeypatch, per_user):
    """The memory is bounded; what one account brings in pushes out its own checks first."""
    from auth import restore_hold
    app, path = held_app
    monkeypatch.setattr(restore_hold, 'MAX_ENTRIES', 4)
    monkeypatch.setattr(restore_hold, 'MAX_PER_USER', per_user)
    job_id = _restore_job(app)
    url = f'/api/v2/system/jobs/{job_id}'
    victim, crowd = _admin_user(app), _admin_user(app)
    victim_key = _api_key(app, victim['id'], 3600)
    keys = [_api_key(app, crowd['id'], 3600) for _ in range(6)]
    client = app.test_client()
    gate = _gate(app, job_id).raise_gate()
    try:
        assert client.get(url, headers={'X-API-Key': victim_key}).status_code == 200
        for key in keys:
            assert client.get(url, headers={'X-API-Key': key}).status_code == 200
        gate.set_view(phase=restore_job.APPLYING, held=True)
        with holding(path):
            victim_seen = client.get(url, headers={'X-API-Key': victim_key})
            latest = client.get(url, headers={'X-API-Key': keys[-1]})
            first = client.get(url, headers={'X-API-Key': keys[0]})
    finally:
        gate.lift()
        with app.app_context():
            db.session.execute(T.delete().where(T.c.id == job_id))
            db.session.commit()
    assert victim_seen.status_code == 200, victim_seen.data
    assert latest.status_code == 200, latest.data
    assert first.status_code == 503, first.data


# -- the session that starts the restore follows it through the held database -------------

RESTORE_PASSWORD = 'Restore-Job-Password-9'  # the archive fixture's


class StartedElsewhere:
    """The restore the route starts is run by a script: its gate goes up ``gate_at`` seconds
    after the start, its transaction holds the file from ``held_at`` until released."""

    def __init__(self, app, path, monkeypatch, gate_at, held_at, before_gate=None):
        self.app, self.path = app, path
        self.gate_at, self.held_at, self.before_gate = gate_at, held_at, before_gate
        self.held, self.release, self.done = (threading.Event(), threading.Event(),
                                              threading.Event())
        self.job_id, self.thread = None, None
        monkeypatch.setattr(runner, 'dispatch_job', self._dispatch)

    def _dispatch(self, job_id):
        self.job_id = job_id
        assert store.claim_job(db.session, job_id, 'elsewhere/1/x', jobs._now()) is not None
        db.session.commit()
        self.thread = threading.Thread(target=self._run, daemon=True)
        self.thread.start()

    def _run(self):
        started = time.monotonic()
        try:
            time.sleep(self.gate_at)
            if self.before_gate:
                self.before_gate()
            gate = _gate(self.app, self.job_id).raise_gate()
            try:
                time.sleep(max(0.0, self.held_at - (time.monotonic() - started)))
                gate.set_view(phase=restore_job.APPLYING, held=True)
                with holding(self.path):
                    self.held.set()
                    self.release.wait(60)
            finally:
                gate.lift()
        finally:
            self.done.set()

    def finish(self):
        self.release.set()
        assert self.done.wait(60)
        if self.job_id:
            for suffix in (restore_job.CANCEL_SUFFIX, restore_job.ARCHIVE_SUFFIX):
                store.purge_file(store.file_name_for(self.job_id, suffix))
            with self.app.app_context():
                db.session.execute(T.delete().where(T.c.id == self.job_id))
                db.session.commit()
                db.session.remove()
            restore_job.remove_state()


def _post_restore(client, blob):
    import io
    return client.post('/api/v2/system/restore', data={
        'file': (io.BytesIO(blob), 'r.ucmbkp'), 'password': RESTORE_PASSWORD},
        content_type='multipart/form-data')


@pytest.fixture
def started_elsewhere(archive, held_app, monkeypatch):
    app, path = held_app
    monkeypatch.setattr(jobs, 'JOB_WAIT_SECONDS', 3)
    made = []

    def make(**kwargs):
        made.append(StartedElsewhere(app, path, monkeypatch, **kwargs))
        return made[-1]
    yield types.SimpleNamespace(app=app, path=path, archive=archive, make=make)
    for script in made:
        script.finish()


def test_a_restore_held_before_its_wait_ends_answers_202_and_its_session_follows(
        started_elsewhere):
    """No Prefer: the POST waits; the transaction holds the database before the wait ends."""
    app = started_elsewhere.app
    admin = _client(app, 'admin', 'changeme123')
    script = started_elsewhere.make(gate_at=0.3, held_at=1.5)
    started, took = _timed(_post_restore, admin, started_elsewhere.archive)
    assert script.held.is_set()
    assert started.status_code == 202, started.data
    assert took < 5, took
    job = started.get_json()['data']['job']
    assert job['id'] == script.job_id and job['phase'] == restore_job.APPLYING
    url = started.headers['Location']
    seen = admin.get(url)
    assert seen.status_code == 200, seen.data
    cancelled = admin.post(f'{url}/cancel')
    assert cancelled.status_code == 200, cancelled.data
    assert restore_job.cancel_flagged(script.job_id)


def test_a_session_revoked_between_the_start_and_the_gate_reads_nothing(started_elsewhere):
    app, path = started_elsewhere.app, started_elsewhere.path
    user = _admin_user(app)
    client = _client(app, user['username'])

    def revoke():
        other = sqlite3.connect(path)
        other.execute('UPDATE users SET session_version = session_version + 1 WHERE id = ?',
                      (user['id'],))
        other.commit()
        other.close()
    script = started_elsewhere.make(gate_at=0.3, held_at=1.5, before_gate=revoke)
    started = _post_restore(client, started_elsewhere.archive)
    assert script.held.is_set()
    assert started.status_code == 202, started.data
    url = started.headers['Location']
    seen = client.get(url)
    cancel = client.post(f'{url}/cancel')
    assert seen.status_code in (401, 503), seen.data
    assert cancel.status_code in (401, 503), cancel.data
    assert not restore_job.cancel_flagged(script.job_id)


def test_the_dialogs_first_poll_after_the_wait_reads_the_held_job(started_elsewhere):
    """The interface's case: 202 at the end of the wait, then the database held, then the
    dialog's first poll."""
    app = started_elsewhere.app
    admin = _client(app, 'admin', 'changeme123')
    script = started_elsewhere.make(gate_at=0.3, held_at=3.5)
    started = _post_restore(admin, started_elsewhere.archive)
    assert started.status_code == 202, started.data
    assert not script.held.is_set()
    assert script.held.wait(10)
    seen = admin.get(started.headers['Location'])
    assert seen.status_code == 200, seen.data
    assert seen.get_json()['data']['phase'] == restore_job.APPLYING


def test_a_restore_that_ends_within_the_wait_answers_its_report_though_it_held_the_database(
        started_elsewhere, monkeypatch):
    """The start request sees the held database first; the restore then commits and ends
    before the wait does: the POST answers the report, never a 202 its revoked session follows."""
    app = started_elsewhere.app
    seen_held = threading.Event()
    real_view = restore_job.local_view

    def spy(job_id):
        view = real_view(job_id)
        if view is not None:
            seen_held.set()
        return view
    monkeypatch.setattr(restore_job, 'local_view', spy)
    admin = _client(app, 'admin', 'changeme123')
    script = started_elsewhere.make(gate_at=0.1, held_at=0.2)

    def conclude():
        # Released only once the start request has read the held state: the order is forced
        assert seen_held.wait(10)
        script.release.set()
        assert script.done.wait(10)
        with app.app_context():
            assert store.conclude_job(db.session, script.job_id, state=store.SUCCEEDED,
                                      reason=None, from_states=(store.RUNNING,), now=jobs._now(),
                                      result={'code': 200, 'message': 'Restored',
                                              'data': {'restored': {'users': 1}}})
            db.session.remove()
    ender = threading.Thread(target=conclude, daemon=True)
    ender.start()
    started = _post_restore(admin, started_elsewhere.archive)
    ender.join(15)
    assert seen_held.is_set()
    assert started.status_code == 200, started.data
    assert started.get_json()['data'] == {'restored': {'users': 1}}
