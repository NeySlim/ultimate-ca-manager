"""GET /system/jobs/<id> shows a restore's local progress only while its transaction holds
SQLite and its row has not passed the commit; in every other case it shows the row's.

Each case below breaks exactly one of those conditions, so each one is pinned on its own.
"""
import pytest
from sqlalchemy import delete, update

from models import db
from services import jobs
from services.jobs import restore as restore_job
from services.jobs import store

ROW = {'phase': 'core', 'done': 3, 'total': 40}
LOCAL = {'phase': 'auth', 'progress': {'done': 17, 'total': 40}}


@pytest.fixture
def running_restore(app):
    with app.app_context():
        job_id = store.create_job(db.session, kind=restore_job.KIND, slot=jobs.SLOT_RESTORE,
                                  exclusive=True, exclusive_slots=jobs.EXCLUSIVE_SLOTS,
                                  now=jobs._now())
        store.claim_job(db.session, job_id, 'held-progress-test', jobs._now())
        db.session.execute(update(store.T).where(store.T.c.id == job_id).values(
            phase=ROW['phase'], progress_done=ROW['done'], progress_total=ROW['total']))
        db.session.commit()
    yield job_id
    with app.app_context():
        db.session.execute(delete(store.T).where(store.T.c.id == job_id))
        db.session.commit()


def _local_state(monkeypatch, state):
    monkeypatch.setattr(restore_job, 'read_state', lambda: state)


def _seen(auth_client, job_id):
    r = auth_client.get(f'/api/v2/system/jobs/{job_id}')
    assert r.status_code == 200, r.data
    data = r.get_json()['data']
    return data['phase'], data['progress']


def _row_view():
    return ROW['phase'], {'done': ROW['done'], 'total': ROW['total']}


def test_held_and_before_the_commit_shows_the_local_progress(auth_client, running_restore,
                                                             monkeypatch):
    _local_state(monkeypatch, {'job_id': running_restore, 'view': {**LOCAL, 'held': True}})
    assert _seen(auth_client, running_restore) == (LOCAL['phase'], LOCAL['progress'])


def test_gate_up_but_not_held_shows_the_row(auth_client, running_restore, monkeypatch):
    """The gate is written before the transaction opens: the row is still the newer."""
    _local_state(monkeypatch, {'job_id': running_restore, 'view': {**LOCAL, 'held': False}})
    assert _seen(auth_client, running_restore) == _row_view()


def test_another_jobs_local_state_shows_the_row(auth_client, running_restore, monkeypatch):
    _local_state(monkeypatch, {'job_id': 'another-job', 'view': {**LOCAL, 'held': True}})
    assert _seen(auth_client, running_restore) == _row_view()


def test_no_local_state_shows_the_row(auth_client, running_restore, monkeypatch):
    _local_state(monkeypatch, None)
    assert _seen(auth_client, running_restore) == _row_view()


def test_past_the_commit_shows_the_row(app, auth_client, running_restore, monkeypatch):
    with app.app_context():
        db.session.execute(update(store.T).where(store.T.c.id == running_restore).values(
            phase=restore_job.COMMITTED))
        db.session.commit()
    _local_state(monkeypatch, {'job_id': running_restore, 'view': {**LOCAL, 'held': True}})
    assert _seen(auth_client, running_restore)[0] == restore_job.COMMITTED


def test_a_row_no_longer_running_shows_the_row(app, auth_client, running_restore, monkeypatch):
    with app.app_context():
        db.session.execute(update(store.T).where(store.T.c.id == running_restore).values(
            state='failed'))
        db.session.commit()
    _local_state(monkeypatch, {'job_id': running_restore, 'view': {**LOCAL, 'held': True}})
    assert _seen(auth_client, running_restore) == _row_view()
