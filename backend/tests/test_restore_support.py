"""tests.restore_support: a restore's answer never depends on the route's bounded wait."""
import io

import pytest

from tests.fresh_app import fresh_app_fixtures
from tests.restore_support import post_to_the_end

app, auth_client, create_ca, create_cert, create_user = fresh_app_fixtures()

URL = '/api/v2/system/restore'


def _form(name='r.ucmbkp'):
    return {'file': (io.BytesIO(b'x'), name), 'password': 'Correct-Horse-Battery-9'}


@pytest.fixture
def empty_restore(monkeypatch):
    from services.backup_service import BackupService
    monkeypatch.setattr(BackupService, 'restore_backup',
                        lambda self, blob, password, **kw: {'sections_carried': []})


def test_a_restore_past_the_routes_wait_answers_its_end(app, auth_client, empty_restore, monkeypatch):
    from models import db
    from services import jobs
    from services.jobs import store
    monkeypatch.setattr(jobs, 'JOB_WAIT_SECONDS', 0)  # a loaded host: the wait is always over
    response = post_to_the_end(auth_client, URL, data=_form(), content_type='multipart/form-data')
    assert response.status_code == 200, response.data
    assert 'carried no data' in response.get_json()['message']
    assert 'carried no data' in response.text
    with app.app_context():
        assert store.active_jobs(db.session) == []


def test_a_refusal_before_any_job_comes_back_as_answered(app, auth_client, empty_restore):
    from models import db
    from services.jobs import store
    response = post_to_the_end(auth_client, URL, data=_form('r.exe'), content_type='multipart/form-data')
    assert response.status_code == 400, response.data
    with app.app_context():
        assert store.active_jobs(db.session) == []
